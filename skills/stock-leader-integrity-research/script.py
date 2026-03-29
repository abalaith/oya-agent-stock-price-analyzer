import os
import json
import httpx
import time

BASE = "https://serpapi.com/search"

RED_FLAG_KEYWORDS = [
    "fraud", "fraudulent", "ponzi", "scam", "convicted", "conviction", "indicted",
    "indictment", "arrested", "arrest", "prison", "jail", "felony", "misdemeanor",
    "sec violation", "sec charges", "sec enforcement", "sec fine", "sec penalty",
    "cease and desist", "securities fraud", "insider trading", "market manipulation",
    "pump and dump", "short seller", "short report", "hindenburg", "citron", "muddy waters",
    "class action", "shareholder lawsuit", "securities lawsuit", "doj investigation",
    "fbi investigation", "whistleblower", "misleading", "false statement",
    "material misrepresentation", "accounting fraud", "restatement", "inflated",
    "fabricated", "forged", "money laundering", "bribery", "corruption",
    "banned", "barred", "suspended", "disgorgement", "settlement", "plea deal",
]


def serpapi_search(key, query, num=10, timeout=25):
    params = {
        "q": query,
        "api_key": key,
        "num": min(num, 20),
        "hl": "en",
        "gl": "us",
        "engine": "google",
    }
    with httpx.Client(timeout=timeout) as c:
        r = c.get(BASE, params=params)
        if r.status_code >= 400:
            try:
                err = r.json()
                raise Exception(f"SerpApi {r.status_code}: {err.get('error', r.text[:300])}")
            except Exception as e:
                if "SerpApi" in str(e):
                    raise
                raise Exception(f"SerpApi {r.status_code}: {r.text[:300]}")
        return r.json()


def extract_results(data, query_label):
    results = []
    for item in data.get("organic_results", []):
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        link = item.get("link", "")
        combined = (title + " " + snippet).lower()
        flags = [kw for kw in RED_FLAG_KEYWORDS if kw in combined]
        results.append({
            "title": title,
            "snippet": snippet,
            "link": link,
            "source": item.get("source", ""),
            "date": item.get("date", ""),
            "red_flags_found": flags,
            "category": query_label,
        })
    return results


def build_queries(category, person_name, company_name, ticker):
    person = person_name.strip()
    company = company_name.strip()
    tk = ticker.strip().upper()
    label = " ".join(filter(None, [person, company, tk]))

    queries = {
        "fraud_history": [
            f'"{person}" fraud OR "financial fraud" OR "ponzi scheme" OR convicted' if person else None,
            f'"{company}" fraud OR "accounting fraud" OR "securities fraud" OR misrepresentation' if company else None,
            f'"{person}" "{company}" fraud allegations' if person and company else None,
        ],
        "sec_violations": [
            f'"{person}" SEC charges OR "SEC enforcement" OR "insider trading" OR "SEC fine"' if person else None,
            f'"{company}" SEC enforcement action OR "SEC violation" OR FINRA penalty' if company else None,
            f'site:sec.gov "{person}" OR "{company}"' if (person or company) else None,
            f'"{tk}" SEC investigation OR "securities fraud"' if tk else None,
        ],
        "lawsuits": [
            f'"{person}" lawsuit OR "class action" OR "DOJ investigation" OR "shareholder suit"' if person else None,
            f'"{company}" "class action lawsuit" OR "securities lawsuit" OR "DOJ" OR "FBI investigation"' if company else None,
            f'"{tk}" shareholder lawsuit OR securities class action' if tk else None,
        ],
        "short_selling": [
            f'"{company}" "short report" OR "Hindenburg Research" OR "Citron Research" OR "Muddy Waters"' if company else None,
            f'"{tk}" short seller OR "short report" OR "pump and dump" OR "short squeeze"' if tk else None,
            f'"{person}" short selling OR "activist short" OR stock manipulation' if person else None,
        ],
        "misleading_news": [
            f'"{person}" "misleading statements" OR "false statements" OR "pump and dump" OR "stock promotion"' if person else None,
            f'"{company}" "misleading press release" OR "inflated guidance" OR "false forward-looking"' if company else None,
            f'"{tk}" misleading OR "stock promotion fraud" OR "inflated claims"' if tk else None,
        ],
        "leadership_background": [
            f'"{person}" CEO background OR controversy OR fired OR resigned OR "prior company"' if person else None,
            f'"{person}" track record OR "past companies" OR "failed company" OR reputation' if person else None,
            f'"{person}" "{company}" controversy OR scandal OR criticism' if person and company else None,
        ],
    }
    return {k: [q for q in v if q] for k, v in queries.items()}


def run_category(key, category, person_name, company_name, ticker, limit):
    all_queries = build_queries(category, person_name, company_name, ticker)
    queries = all_queries.get(category, [])
    if not queries:
        return []
    all_results = []
    seen_links = set()
    for q in queries[:3]:
        try:
            data = serpapi_search(key, q, num=limit)
            for r in extract_results(data, category):
                if r["link"] not in seen_links:
                    seen_links.add(r["link"])
                    all_results.append(r)
            time.sleep(0.5)
        except Exception as e:
            all_results.append({"error": str(e), "query": q, "category": category})
    return all_results


def score_risk(all_results):
    total_flags = sum(len(r.get("red_flags_found", [])) for r in all_results)
    flagged_results = [r for r in all_results if r.get("red_flags_found")]
    all_found_flags = list(set(f for r in all_results for f in r.get("red_flags_found", [])))

    critical_terms = {"convicted", "conviction", "indicted", "prison", "jail", "felony", "securities fraud", "ponzi", "arrested"}
    high_terms = {"fraud", "sec violation", "sec charges", "sec enforcement", "insider trading", "class action", "doj investigation", "fbi investigation"}

    if any(f in all_found_flags for f in critical_terms):
        risk_level = "CRITICAL"
    elif total_flags >= 10 or any(f in all_found_flags for f in high_terms):
        risk_level = "HIGH"
    elif total_flags >= 4:
        risk_level = "MEDIUM"
    elif total_flags > 0:
        risk_level = "LOW"
    else:
        risk_level = "CLEAN"

    return {
        "risk_level": risk_level,
        "total_red_flag_hits": total_flags,
        "flagged_result_count": len(flagged_results),
        "unique_red_flags_found": sorted(all_found_flags),
    }


def do_full_report(key, inp):
    person_name = inp.get("person_name", "")
    company_name = inp.get("company_name", "")
    ticker = inp.get("ticker", "")
    limit = min(int(inp.get("limit", 10)), 20)

    if not person_name and not company_name and not ticker:
        return {"error": "Provide at least one of: person_name, company_name, or ticker"}

    categories = ["fraud_history", "sec_violations", "lawsuits", "short_selling", "misleading_news", "leadership_background"]
    report = {}
    all_results = []

    for cat in categories:
        results = run_category(key, cat, person_name, company_name, ticker, limit)
        report[cat] = results
        all_results.extend([r for r in results if "error" not in r])

    risk_summary = score_risk(all_results)

    top_findings = sorted(
        [r for r in all_results if r.get("red_flags_found")],
        key=lambda x: len(x["red_flags_found"]),
        reverse=True
    )[:10]

    return {
        "subject": {
            "person": person_name,
            "company": company_name,
            "ticker": ticker,
        },
        "risk_summary": risk_summary,
        "top_red_flag_findings": top_findings,
        "detailed_results": report,
        "disclaimer": "This research is for informational purposes only and does not constitute investment advice.",
    }


def do_single_category(key, inp, category):
    person_name = inp.get("person_name", "")
    company_name = inp.get("company_name", "")
    ticker = inp.get("ticker", "")
    limit = min(int(inp.get("limit", 10)), 20)

    if not person_name and not company_name and not ticker:
        return {"error": "Provide at least one of: person_name, company_name, or ticker"}

    results = run_category(key, category, person_name, company_name, ticker, limit)
    valid = [r for r in results if "error" not in r]
    errors = [r for r in results if "error" in r]
    risk_summary = score_risk(valid)

    return {
        "subject": {"person": person_name, "company": company_name, "ticker": ticker},
        "category": category,
        "risk_summary": risk_summary,
        "results": valid,
        "errors": errors,
        "total_results": len(valid),
        "disclaimer": "This research is for informational purposes only and does not constitute investment advice.",
    }


try:
    key = os.environ.get("SERPAPI_KEY", "")
    if not key:
        raise Exception("SERPAPI_KEY environment variable is not set")

    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    action = inp.get("action", "")

    if action == "full_report":
        result = do_full_report(key, inp)
    elif action == "fraud_history":
        result = do_single_category(key, inp, "fraud_history")
    elif action == "sec_violations":
        result = do_single_category(key, inp, "sec_violations")
    elif action == "lawsuits":
        result = do_single_category(key, inp, "lawsuits")
    elif action == "short_selling":
        result = do_single_category(key, inp, "short_selling")
    elif action == "misleading_news":
        result = do_single_category(key, inp, "misleading_news")
    elif action == "leadership_background":
        result = do_single_category(key, inp, "leadership_background")
    else:
        result = {
            "error": f"Unknown action: '{action}'",
            "available_actions": [
                "full_report", "fraud_history", "sec_violations",
                "lawsuits", "short_selling", "misleading_news", "leadership_background"
            ]
        }

    print(json.dumps(result))

except Exception as e:
    print(json.dumps({"error": str(e)}))