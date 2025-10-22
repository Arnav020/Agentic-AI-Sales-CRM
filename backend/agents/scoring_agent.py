# agents/scoring_agent.py
"""
Multi-user compatible Scoring Agent with MongoDB integration
------------------------------------------------------------
- Reads inputs/outputs per user under /users/<user_id>/.
- Keeps the original scoring logic unchanged.
- Saves top-N scored companies to MongoDB (collection: lead_scores).
- Writes JSON backups under /users/<user_id>/outputs/.
- Loads backend/.env automatically for MongoDB connection.
"""

import json
import os
import re
import math
import logging
import uuid
from typing import List, Dict
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer, util
import numpy as np
from difflib import SequenceMatcher
from backend.db.mongo import save_user_output

# -----------------------------
# Constants
# -----------------------------
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# -----------------------------
# Mongo setup
# -----------------------------
# Ensure .env loaded from backend
project_root = Path(__file__).resolve().parents[1]  # backend/
load_dotenv(project_root / ".env")

# Safe import of Mongo helper
try:
    from backend.db.mongo import save_result as mongo_save_result
except Exception as e:
    mongo_save_result = None
    logging.warning(f"⚠️ Could not import backend.db.mongo.save_result: {e}")

# -----------------------------
# Helpers
# -----------------------------
def normalize(text) -> str:
    """Normalize text safely (handle strings, lists, None)."""
    if not text:
        return ""
    if isinstance(text, list):
        text = next((str(t) for t in text if isinstance(t, str) and t.strip()), "")
    text = str(text).lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = text.replace("gurgaon", "gurugram").replace("delhi ncr", "new delhi")
    text = text.replace("&", " and ")
    return text.strip()


def parse_employees(emp_raw) -> int:
    if not emp_raw:
        return 0
    s = str(emp_raw).lower().strip().replace(",", "").replace(" ", "")

    def conv(x):
        try:
            mult = 1
            tx = x.lower().strip()
            if tx.endswith("+"):
                tx = tx[:-1]
            if tx.endswith("k"):
                mult = 1000
                tx = tx[:-1]
            elif tx.endswith("m"):
                mult = 1000000
                tx = tx[:-1]
            return int(float(tx) * mult)
        except Exception:
            return None

    if "-" in s:
        lo, hi = s.split("-", 1)
        lo_v, hi_v = conv(lo), conv(hi)
        if lo_v and hi_v:
            return (lo_v + hi_v) // 2

    val = conv(s)
    if val:
        return val

    m = re.search(r"\d+", s)
    if m:
        try:
            return int(m.group(0))
        except:
            return 0
    return 0


def logistic(x, k=5, x0=0.5):
    """Smooth logistic weighting (boosts values >0.5)."""
    try:
        return 1.0 / (1.0 + math.exp(-k * (x - x0)))
    except Exception:
        return 0.0


def cos_sim(a, b):
    """Compute cosine similarity between two vectors or tensors."""
    if a is None or b is None:
        return 0.0
    try:
        sim = util.cos_sim(a, b)
        if hasattr(sim, "item"):
            return float(sim.item())
        arr = np.array(sim)
        if arr.size:
            return float(arr.flat[0])
        return 0.0
    except Exception:
        try:
            a_arr = np.array(a, dtype=float)
            b_arr = np.array(b, dtype=float)
            denom = np.linalg.norm(a_arr) * np.linalg.norm(b_arr)
            if denom == 0:
                return 0.0
            return float(np.dot(a_arr, b_arr) / denom)
        except Exception:
            return 0.0


# -----------------------------
# Scoring Agent
# -----------------------------
class ScoringAgent:
    GENERIC_INDUSTRY_TERMS = {
        "technology", "tech", "information technology", "it", "software", "digital", "platform",
        "internet", "online", "saas", "cloud", "it services"
    }

    DOMAIN_KEYWORD_HINTS = {
        "food": {"food", "restaurant", "cafe", "tea", "coffee", "beverage", "snack", "dine"},
        "finance": {"finance", "financial", "fintech", "payment", "payments", "loan", "credit", "wallet"},
        "education": {"education", "edtech", "learning", "school", "tutor"},
        "health": {"health", "healthcare", "med", "telehealth"},
    }

    def __init__(self, user_root: str = None):
        """
        user_root: Path to user's folder (e.g., users/user_demo).
        If None, defaults to backend/ for backward compatibility.
        """
        self.project_root = Path(__file__).resolve().parents[1]
        if user_root:
            self.user_root = Path(user_root)
        else:
            self.user_root = self.project_root

        # Normalize and ensure per-user directories
        if "users" in str(self.user_root):
            self.user_id = self.user_root.name
        else:
            self.user_id = "default_user"
        self.inputs_dir = self.user_root / "inputs"
        self.outputs_dir = self.user_root / "outputs"
        self.logs_dir = self.user_root / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

        # Configure logging
        self.log_file = self.logs_dir / "scoring_agent.log"
        self._setup_logging()

        # File paths
        self.requirements_file = self.inputs_dir / "customer_requirements.json"
        self.companies_file = self.outputs_dir / "enriched_companies.json"
        self.output_file = self.outputs_dir / "scored_companies.json"

        # Load inputs
        if not self.requirements_file.exists() or not self.companies_file.exists():
            logging.error("❌ Missing input files for scoring agent.")
            raise FileNotFoundError("Inputs not found for ScoringAgent")

        with open(self.requirements_file, "r", encoding="utf-8") as f:
            self.requirements = json.load(f)
        with open(self.companies_file, "r", encoding="utf-8") as f:
            self.companies = json.load(f)

        # Weights (kept same)
        self.weights = {
            "industry": 38, "keywords": 32, "hq": 10,
            "funding": 7, "expansion": 6, "negative": -8,
            "momentum": 4, "hiring": 6, "founded_year": 3, "employees": 3,
        }

        # Sentence-transformers model
        self.model = SentenceTransformer(MODEL_NAME)

        # Prepare embeddings
        self.req_industries = [normalize(x) for x in self.requirements.get("industry", [])]
        self.req_kw_list = self._expand_keywords(self.requirements.get("preferred_keywords", []))
        self.req_hq_text = " ".join(self.requirements.get("headquarters", []))

        self.req_ind_embs = (
            self.model.encode(self.req_industries, convert_to_tensor=True)
            if self.req_industries else None
        )
        self.req_kw_emb = (
            self.model.encode(" ".join(self.req_kw_list), convert_to_tensor=True)
            if self.req_kw_list else None
        )
        self.req_hq_emb = (
            self.model.encode(self.req_hq_text, convert_to_tensor=True)
            if self.req_hq_text else None
        )

        self._req_domain_tokens = set()
        for ind in self.req_industries:
            toks = re.findall(r"\b[a-z]{3,30}\b", ind)
            self._req_domain_tokens.update(toks)

    # -----------------------------
    def _setup_logging(self):
        """Initialize per-user log file."""
        logging.getLogger().handlers = []
        logging.basicConfig(
            filename=str(self.log_file),
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(console)
        logging.info(f"Logging initialized for ScoringAgent → {self.log_file}")

    # -----------------------------
    def _expand_keywords(self, keywords: List[str]) -> List[str]:
        expansion_map = {
            "payment": ["payments", "transaction", "gateway", "upi", "wallet", "billing", "checkout"],
            "digital": ["online", "virtual", "cloud", "internet", "mobile", "web"],
            "loan": ["credit", "financing", "borrow", "microloan", "debt", "lending"],
            "credit": ["card", "debit", "score", "lending", "creditcard"],
            "finance": ["financial", "fintech", "payments"],
            "food": ["restaurant", "snack", "cafe", "tea", "beverage", "coffee", "delivery"],
            "technology": ["tech", "software", "digital", "platform", "saas"],
            "delivery": ["logistics", "shipping", "lastmile"],
        }
        kws = set()
        for k in keywords or []:
            nk = normalize(k)
            kws.add(nk)
            for ex in expansion_map.get(nk, []):
                kws.add(normalize(ex))
        return sorted(kws)

# -----------------------------
    # Rest of logic stays EXACTLY the same (scoring logic untouched)
    # -----------------------------
    def extract_keywords(self, company: Dict) -> List[str]:
        s = company.get("structured_info", {}) or {}
        parts = [
            s.get("description", "") or "",
            " ".join(map(str, s.get("products", []) or [])),
            " ".join(map(str, s.get("services", []) or [])),
            company.get("description", "") or "",
        ]
        text = " ".join(parts).lower()
        tokens = re.findall(r"\b[a-z]{3,30}\b", text)
        return sorted({normalize(t) for t in tokens if len(t) >= 3})

    def _detect_domain_hint(self, industry_text: str) -> str:
        it = industry_text.lower()
        for domain, hintset in self.DOMAIN_KEYWORD_HINTS.items():
            if any(h in it for h in hintset):
                return domain
        for token in self._req_domain_tokens:
            for domain, hintset in self.DOMAIN_KEYWORD_HINTS.items():
                if token in hintset and token in it:
                    return domain
        return ""

    # -----------------------------
    # Full scoring logic unchanged
    # -----------------------------
    def score_company(self, company: Dict) -> Dict:
        s = company.get("structured_info", {}) or {}
        breakdown = {}
        reasons = []
        total = 0.0

        # normalize industry text
        ind_text = (s.get("industry") or "")
        ind_text_norm = normalize(ind_text)

        # --- Industry similarity (support multiple requested industries)
        ind_sim = 0.0
        if ind_text_norm and self.req_ind_embs is not None:
            try:
                ind_emb = self.model.encode(ind_text_norm, convert_to_tensor=True)
                sims = [cos_sim(ind_emb, req_emb) for req_emb in self.req_ind_embs]
                ind_sim = max(sims) if sims else 0.0
            except Exception:
                # fallback to fuzzy sequence match against req industries strings
                ratios = [SequenceMatcher(None, ind_text_norm, req).ratio() for req in self.req_industries] if self.req_industries else [0.0]
                ind_sim = max(ratios)
        else:
            # fallback fuzzy
            ratios = [SequenceMatcher(None, ind_text_norm, req).ratio() for req in self.req_industries] if self.req_industries else [0.0]
            ind_sim = max(ratios) if ratios else 0.0

        # Apply generic-technology downweight and domain+tech boost
        low_generic_penalty = 0.75  # multiply ind_sim by this if industry is generic-tech only
        hybrid_boost = 1.2        # multiply if we detect domain + tech hybrid (e.g., Food + Tech)
        # detect if company industry contains generic tech terms
        industry_tokens = set(re.findall(r"\b[a-z]{3,30}\b", ind_text_norm))
        has_generic_term = bool(industry_tokens & self.GENERIC_INDUSTRY_TERMS)
        # detect domain hint
        domain_hint = self._detect_domain_hint(ind_text_norm)
        # check if requirements contain a specific domain (not only "technology")
        req_domains_non_generic = [r for r in self.req_industries if not any(g in r for g in self.GENERIC_INDUSTRY_TERMS)]
        is_hybrid = False
        if has_generic_term:
            # if also contains a clear domain token (like 'food' or 'restaurant'), consider hybrid
            if domain_hint:
                is_hybrid = True

        # apply transformations
        adj_ind_sim = ind_sim
        if has_generic_term and not is_hybrid:
            adj_ind_sim = adj_ind_sim * low_generic_penalty
        if is_hybrid:
            adj_ind_sim = min(1.0, adj_ind_sim * hybrid_boost)

        industry_score = self.weights["industry"] * adj_ind_sim
        breakdown["industry"] = round(industry_score, 3)
        if adj_ind_sim > 0.8:
            reasons.append(f"Strong industry alignment ({ind_text})")
        elif adj_ind_sim > 0.5:
            reasons.append(f"Partial industry similarity ({ind_text})")
        total += industry_score

        # --- Keywords (expanded + semantic)
        company_kw = self.extract_keywords(company)
        company_kw_text = " ".join(company_kw)
        company_kw_emb = self.model.encode(company_kw_text, convert_to_tensor=True) if company_kw_text else None
        req_kw_text = " ".join(self.req_kw_list)
        req_kw_emb = self.req_kw_emb

        kw_sem_sim = cos_sim(company_kw_emb, req_kw_emb) if company_kw_emb is not None and req_kw_emb is not None else 0.0
        exact_overlap = sorted(list(set(company_kw) & set(self.req_kw_list)))
        # combined score: semantic + exact overlap fraction
        overlap_frac = (len(exact_overlap) / max(1, len(self.req_kw_list)))
        kw_score = self.weights["keywords"] * (0.65 * kw_sem_sim + 0.35 * overlap_frac)
        breakdown["keywords"] = round(kw_score, 3)
        if exact_overlap:
            reasons.append(f"Keywords matched: {', '.join(exact_overlap)}")
        elif kw_sem_sim > 0.45:
            reasons.append("Semantic keyword similarity detected")
        total += kw_score

        # --- HQ matching (robust to list or mixed types)
        raw_hq = s.get("headquarters", "")
        hq = normalize(raw_hq)
        req_hq_text_norm = normalize(self.req_hq_text or "")
        hq_sim = SequenceMatcher(None, hq, req_hq_text_norm).ratio() if hq and req_hq_text_norm else 0.0
        hq_score = self.weights["hq"] * hq_sim
        breakdown["hq"] = round(hq_score, 3)
        if hq_sim > 0.8:
            reasons.append("HQ region matches")
        elif hq_sim > 0.5:
            reasons.append("HQ region partially matches")
        total += hq_score


        # --- Signals: funding, expansion, negative (contextualized by industry relevance)
        f = float(company.get("funding_signal", 0) or 0)
        e = float(company.get("expansion_signal", 0) or 0)
        n = float(company.get("negative_signal", 0) or 0)

        # domain_factor reduces signal impact when industry relevance is low
        domain_factor = 0.5 + 0.5 * adj_ind_sim
        funding_score = self.weights["funding"] * logistic(f) * domain_factor
        expansion_score = self.weights["expansion"] * logistic(e) * domain_factor
        negative_score = self.weights["negative"] * n  # negative weight already negative value
        breakdown["funding"] = round(funding_score, 3)
        breakdown["expansion"] = round(expansion_score, 3)
        breakdown["negative"] = round(negative_score, 3)
        if f >= self.requirements.get("min_funding_signal", 0.0):
            # treat meeting threshold as positive
            reasons.append("Meets funding threshold")
        if f >= 0.7:
            reasons.append("Strong funding momentum")
        if e >= 0.5:
            reasons.append("Active expansion observed")
        if n >= self.requirements.get("max_negative_signal", 1.0):
            reasons.append("High negative sentiment detected")
        total += funding_score + expansion_score + negative_score

        # --- Momentum (derived)
        momentum = max(0.0, (f + e - n) / 2.0) * domain_factor
        momentum_score = self.weights["momentum"] * momentum
        breakdown["momentum"] = round(momentum_score, 3)
        if momentum >= 0.6:
            reasons.append("High momentum (growth health)")
        total += momentum_score

        # --- Hiring requirement
        hiring_req = self.requirements.get("hiring_required", False)
        if hiring_req:
            if company.get("hiring"):
                hiring_score = self.weights["hiring"]
                reasons.append("Actively hiring")
            else:
                hiring_score = -abs(self.weights["hiring"]) * 0.5
                reasons.append("Not hiring (requirement unmet)")
        else:
            hiring_score = 0.0
        breakdown["hiring"] = round(hiring_score, 3)
        total += hiring_score

        # --- Founded year freshness
        fy_score = 0.0
        try:
            fy_raw = s.get("founded_year", None)
            if fy_raw:
                fy = int(str(fy_raw)[:4])
                after = int(self.requirements.get("founded_after", 0) or 0)
                if after and fy >= after:
                    # map (fy-after) into [0..1] then logistic
                    val = (fy - after) / max(1.0, (2025 - after))  # normalized horizon (2025 as rough cap)
                    freshness = logistic(val, k=6, x0=0.2)
                    fy_score = self.weights["founded_year"] * freshness
                    reasons.append(f"Founded recently ({fy})")
        except Exception:
            fy_score = 0.0
        breakdown["founded_year"] = round(fy_score, 3)
        total += fy_score

        # --- Employees
        emp_score = 0.0
        emp_val = parse_employees(s.get("employees_count", "") or "")
        if emp_val > 0:
            low, high = self.requirements.get("employee_range", [0, 99999999])
            if low <= emp_val <= high:
                emp_score = self.weights["employees"]
                reasons.append(f"Employee size within target ({emp_val})")
            elif (low * 0.8) <= emp_val <= (high * 1.2):
                emp_score = self.weights["employees"] * 0.6
                reasons.append(f"Employee size near target ({emp_val})")
        breakdown["employees"] = round(emp_score, 3)
        total += emp_score

        # --- Industry irrelevance gate: cap final score if industry similarity is very low
        if adj_ind_sim < 0.35:
            total = min(total, 40.0)

        # --- final score & label
        final_score = max(0.0, min(100.0, round(total, 2)))
        if final_score >= 75:
            fit_label = "Excellent Match"
        elif final_score >= 45:
            fit_label = "Moderate Match"
        else:
            fit_label = "Low Match"

        # Ensure consistent ordering in breakdown
        ordered_breakdown = {
            "industry": breakdown.get("industry", 0.0),
            "keywords": breakdown.get("keywords", 0.0),
            "hq": breakdown.get("hq", 0.0),
            "funding": breakdown.get("funding", 0.0),
            "expansion": breakdown.get("expansion", 0.0),
            "negative": breakdown.get("negative", 0.0),
            "momentum": breakdown.get("momentum", 0.0),
            "hiring": breakdown.get("hiring", 0.0),
            "founded_year": breakdown.get("founded_year", 0.0),
            "employees": breakdown.get("employees", 0.0),
            "total": final_score,
        }

        return {
            "company": company.get("company"),
            "score": final_score,
            "fit_label": fit_label,
            "breakdown": ordered_breakdown,
            "reasons": reasons,
        }

    # -----------------------------
    def rank_companies(self, top_n=15):
        results = [self.score_company(c) for c in self.companies]
        return sorted(results, key=lambda x: x["score"], reverse=True)[:top_n]

    def run(self, top_n=50):
        """Run scoring, persist results to JSON + MongoDB."""
        logging.info("🚀 Starting scoring process...")
        from copy import deepcopy

        # reuse original rank_companies logic
        results = [self.score_company(c) for c in self.companies]
        results_sorted = sorted(results, key=lambda x: x["score"], reverse=True)[:top_n]

        # canonical JSON save
        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(results_sorted, f, indent=2, ensure_ascii=False)
        logging.info(f"✅ Scoring complete. Saved {len(results_sorted)} results → {self.output_file}")

        # MongoDB persistence
        correlation_id = str(uuid.uuid4())
        doc = {
            "user_id": self.user_id,
            "correlation_id": correlation_id,
            "created_at": datetime.utcnow(),
            "count": len(results_sorted),
            "results": deepcopy(results_sorted),
        }
        if mongo_save_result:
            try:
                mongo_save_result("lead_scores", doc)
                logging.info(f"Saved lead scores to MongoDB (user={self.user_id}, count={len(results_sorted)})")
            except Exception as e:
                logging.exception(f"Mongo save failed: {e}")
        else:
            logging.warning("Mongo helper unavailable; skipping Mongo persistence.")

        # Timestamped JSON backup for traceability
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_path = self.outputs_dir / f"lead_scores_{ts}.json"
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(doc, f, indent=2, ensure_ascii=False, default=str)
            logging.info(f"Backup JSON saved → {backup_path}")
        except Exception as e:
            logging.exception(f"Failed to write backup JSON: {e}")

        # after saving JSON
        try:
            user_id = self.user_root.name if self.user_root else "unknown"
            save_user_output(user_id=user_id, agent="scoring_agent", output_type="scored_companies", data={"results": results})
            logging.info("Saved scored_companies to user_outputs (mongo)")
        except Exception:
            logging.exception("Failed to save scored companies to user_outputs")

        print(f"✅ Scoring complete. Saved {len(results_sorted)} results to {self.output_file}")
        return results_sorted

# -----------------------------
# Runner / Entrypoint
# -----------------------------
def main(user_folder: str | None = None):
    """
    Main entrypoint for ScoringAgent.
    Works both:
      - From orchestrator (via import + main())
      - As standalone CLI (python agents/scoring_agent.py user_demo)
    """
    if user_folder:
        user_path = Path(user_folder)
    else:
        env_user = os.getenv("USER_FOLDER")
        user_path = Path(env_user) if env_user else None

    agent = ScoringAgent(user_root=user_path)
    agent.run(top_n=50)


if __name__ == "__main__":
    import sys
    user_arg = sys.argv[1] if len(sys.argv) >= 2 else None
    if user_arg:
        user_folder = str(Path("users") / user_arg)
    else:
        user_folder = None
    main(user_folder)
