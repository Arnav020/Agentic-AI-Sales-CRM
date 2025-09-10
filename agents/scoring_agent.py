# agents/scoring_agent.py
import json
import os

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

        # 1. Industry
        if s.get("industry") in r["industry"]:
            score += 25
            reasons.append("Industry match")

        # 2. Keywords
        kw_matches = set(company.get("industry_keywords", [])) & set(r["preferred_keywords"])
        if kw_matches:
            score += 20
            reasons.append(f"Keywords matched: {', '.join(kw_matches)}")

        # 3. HQ
        if s.get("headquarters") in r["headquarters"]:
            score += 10
            reasons.append("HQ match")

        # 4. Funding & expansion
        if company.get("funding_signal", 0) >= r["min_funding_signal"]:
            score += 10
            reasons.append("Strong funding signal")
        if company.get("expansion_signal", 0) > 0.3:
            score += 5
            reasons.append("Expansion activity detected")

        # 5. Negative signal
        if company.get("negative_signal", 0) > r["max_negative_signal"]:
            score -= 15
            reasons.append("High negative signals")

        # 6. Hiring
        if r["hiring_required"] and company.get("hiring"):
            score += 10
            reasons.append("Actively hiring")
        elif r["hiring_required"] and not company.get("hiring"):
            score -= 5
            reasons.append("Not hiring")

        # 7. Founded year
        try:
            year = int(s.get("founded_year", 0))
            if year >= r["founded_after"]:
                score += 8
                reasons.append("Founded recently")
        except:
            pass

        # 8. Employees
        try:
            emp = int(s.get("employees_count", "0").replace(",", ""))
            if r["employee_range"][0] <= emp <= r["employee_range"][1]:
                score += 7
                reasons.append("Employee size within target")
        except:
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
