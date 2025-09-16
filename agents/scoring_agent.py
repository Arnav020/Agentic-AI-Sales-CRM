# agents/scoring_agent.py
import json
import os
import re

def normalize(text: str) -> str:
    """Normalize text for comparison (case-insensitive, strip, singularize common variants)."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    # Normalize common Indian city variants
    text = text.replace("gurgaon", "gurugram")
    text = text.replace("delhi ncr", "new delhi")
    return text


class ScoringAgent:
    def __init__(self, requirements_file, companies_file):
        with open(requirements_file, "r", encoding="utf-8") as f:
            self.requirements = json.load(f)
        with open(companies_file, "r", encoding="utf-8") as f:
            self.companies = json.load(f)

    def score_company(self, company):
        r = self.requirements
        s = company.get("structured_info", {})
        score = 0
        reasons = []

        # 1. Industry (strong boost for exact or partial match)
        industry = normalize(s.get("industry"))
        req_industries = [normalize(x) for x in r.get("industry", [])]
        if industry in req_industries:
            score += 30
            reasons.append("Industry match")
        elif any(industry in x or x in industry for x in req_industries if industry):
            score += 20
            reasons.append("Partial industry match")

        # 2. Keywords (each match weighted higher)
        kw_matches = set(map(normalize, company.get("industry_keywords", []))) & set(
            map(normalize, r.get("preferred_keywords", []))
        )
        if kw_matches:
            score += 7 * len(kw_matches)
            reasons.append(f"Keywords matched: {', '.join(kw_matches)}")

        # 3. HQ (looser matching for Delhi/Gurgaon variants)
        hq = normalize(s.get("headquarters"))
        req_hqs = [normalize(x) for x in r.get("headquarters", [])]
        if hq in req_hqs:
            score += 10
            reasons.append("HQ match")
        elif any(hq in x or x in hq for x in req_hqs if hq):
            score += 7
            reasons.append("Partial HQ match")

        # 4. Funding & expansion
        if company.get("funding_signal", 0) >= r.get("min_funding_signal", 0):
            score += 10
            reasons.append("Strong funding signal")
        if company.get("expansion_signal", 0) > 0.3:
            score += 5
            reasons.append("Expansion activity detected")

        # 5. Negative signal
        if company.get("negative_signal", 0) > r.get("max_negative_signal", 1):
            score -= 15
            reasons.append("High negative signals")

        # 6. Hiring requirement
        if r.get("hiring_required") and company.get("hiring"):
            score += 10
            reasons.append("Actively hiring")
        elif r.get("hiring_required") and not company.get("hiring"):
            score -= 5
            reasons.append("Not hiring")

        # 7. Founded year
        try:
            year = int(s.get("founded_year", 0))
            if year >= r.get("founded_after", 0):
                score += 8
                reasons.append("Founded recently")
        except Exception:
            pass

        # 8. Employees (full points if in range, partial if near range)
        try:
            emp_raw = s.get("employees_count", "0")
            emp_str = str(emp_raw).replace(",", "").split()[0]
            if "+" in emp_str:
                emp = int(emp_str.replace("+", ""))
            else:
                emp = int(emp_str)
            emp_min, emp_max = r.get("employee_range", [0, 9999999])
            if emp_min <= emp <= emp_max:
                score += 10
                reasons.append("Employee size within target")
            elif emp > 0 and (0.8 * emp_min <= emp <= 1.2 * emp_max):
                score += 5
                reasons.append("Employee size near target")
        except Exception:
            pass

        return {"company": company["company"], "score": score, "reasons": reasons}

    def rank_companies(self, top_n=15):
        results = [self.score_company(c) for c in self.companies]
        ranked = sorted(results, key=lambda x: x["score"], reverse=True)
        return ranked[:top_n]


if __name__ == "__main__":
    inputs_dir = "inputs"
    outputs_dir = "outputs"

    requirements_file = os.path.join(inputs_dir, "customer_requirements.json")
    companies_file = os.path.join(outputs_dir, "enriched_companies.json")
    output_file = os.path.join(outputs_dir, "scored_companies.json")

    agent = ScoringAgent(requirements_file, companies_file)
    top_companies = agent.rank_companies()

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(top_companies, f, indent=2, ensure_ascii=False)

    print(f"✅ Scoring complete! Top companies saved to {output_file}")
