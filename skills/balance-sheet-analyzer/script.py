import os
import json
import httpx
from datetime import datetime

BASE_AV = "https://www.alphavantage.co/query"


# ─────────────────────────────────────────────
# HTTP helpers
# ─────────────────────────────────────────────

def av_get(key, params, timeout=30):
    params["apikey"] = key
    with httpx.Client(timeout=timeout) as c:
        r = c.get(BASE_AV, params=params)
    if r.status_code >= 400:
        raise Exception(f"Alpha Vantage HTTP {r.status_code}: {r.text[:400]}")
    data = r.json()
    if "Note" in data:
        raise Exception("Alpha Vantage rate limit reached. Please wait 60 seconds and retry.")
    if "Information" in data:
        raise Exception(f"Alpha Vantage: {data['Information']}")
    if "Error Message" in data:
        raise Exception(f"Alpha Vantage error: {data['Error Message']}")
    return data


def safe_float(val, default=0.0):
    try:
        if val in (None, "None", "", "N/A"):
            return default
        return float(val)
    except (ValueError, TypeError):
        return default


# ─────────────────────────────────────────────
# Data fetchers
# ─────────────────────────────────────────────

def fetch_balance_sheet_data(key, symbol, period="annual"):
    data = av_get(key, {"function": "BALANCE_SHEET", "symbol": symbol.upper()})
    reports_key = "annualReports" if period == "annual" else "quarterlyReports"
    reports = data.get(reports_key, [])
    if not reports:
        raise Exception(f"No {period} balance sheet data found for {symbol}. Check the ticker symbol.")
    return reports


def fetch_income_data(key, symbol, period="annual"):
    data = av_get(key, {"function": "INCOME_STATEMENT", "symbol": symbol.upper()})
    reports_key = "annualReports" if period == "annual" else "quarterlyReports"
    return data.get(reports_key, [])


def fetch_overview(key, symbol):
    data = av_get(key, {"function": "OVERVIEW", "symbol": symbol.upper()})
    return data


# ─────────────────────────────────────────────
# Ratio calculators
# ─────────────────────────────────────────────

def calc_ratios(bs):
    """Calculate all key ratios from a single balance sheet report dict."""
    total_assets = safe_float(bs.get("totalAssets"))
    total_liabilities = safe_float(bs.get("totalLiabilities"))
    current_assets = safe_float(bs.get("totalCurrentAssets"))
    current_liabilities = safe_float(bs.get("totalCurrentLiabilities"))
    inventory = safe_float(bs.get("inventory"))
    cash = safe_float(bs.get("cashAndCashEquivalentsAtCarryingValue"))
    short_inv = safe_float(bs.get("shortTermInvestments"))
    long_term_debt = safe_float(bs.get("longTermDebt"))
    short_term_debt = safe_float(bs.get("shortTermDebt") or bs.get("currentDebt", 0))
    total_equity = safe_float(bs.get("totalShareholderEquity"))
    retained_earnings = safe_float(bs.get("retainedEarnings"))
    goodwill = safe_float(bs.get("goodwill"))
    intangibles = safe_float(bs.get("intangibleAssets"))

    total_debt = long_term_debt + short_term_debt
    tangible_assets = total_assets - goodwill - intangibles

    ratios = {}
    # Liquidity
    ratios["current_ratio"] = round(current_assets / current_liabilities, 3) if current_liabilities else None
    ratios["quick_ratio"] = round((current_assets - inventory) / current_liabilities, 3) if current_liabilities else None
    ratios["cash_ratio"] = round((cash + short_inv) / current_liabilities, 3) if current_liabilities else None

    # Leverage / Solvency
    ratios["debt_to_equity"] = round(total_debt / total_equity, 3) if total_equity and total_equity > 0 else None
    ratios["debt_to_assets"] = round(total_debt / total_assets, 3) if total_assets else None
    ratios["total_liabilities_to_equity"] = round(total_liabilities / total_equity, 3) if total_equity and total_equity > 0 else None
    ratios["equity_multiplier"] = round(total_assets / total_equity, 3) if total_equity and total_equity > 0 else None

    # Asset quality
    ratios["tangible_asset_ratio"] = round(tangible_assets / total_assets, 3) if total_assets else None
    ratios["retained_earnings_to_assets"] = round(retained_earnings / total_assets, 3) if total_assets else None

    # Raw values (in millions for readability)
    def m(v): return round(v / 1_000_000, 2)
    ratios["total_assets_M"] = m(total_assets)
    ratios["total_liabilities_M"] = m(total_liabilities)
    ratios["total_equity_M"] = m(total_equity)
    ratios["total_debt_M"] = m(total_debt)
    ratios["cash_M"] = m(cash + short_inv)
    ratios["current_assets_M"] = m(current_assets)
    ratios["current_liabilities_M"] = m(current_liabilities)
    ratios["long_term_debt_M"] = m(long_term_debt)
    ratios["retained_earnings_M"] = m(retained_earnings)
    ratios["negative_equity"] = total_equity < 0

    return ratios


def calc_income_metrics(income_reports, bs_report):
    """Calculate ROA, ROE, interest coverage from income statement."""
    if not income_reports:
        return {}
    inc = income_reports[0]
    total_assets = safe_float(bs_report.get("totalAssets"))
    total_equity = safe_float(bs_report.get("totalShareholderEquity"))
    net_income = safe_float(inc.get("netIncome"))
    ebit = safe_float(inc.get("ebit") or inc.get("operatingIncome", 0))
    interest_expense = safe_float(inc.get("interestExpense"))
    revenue = safe_float(inc.get("totalRevenue"))

    metrics = {}
    metrics["roa"] = round(net_income / total_assets * 100, 2) if total_assets else None
    metrics["roe"] = round(net_income / total_equity * 100, 2) if total_equity and total_equity > 0 else None
    metrics["asset_turnover"] = round(revenue / total_assets, 3) if total_assets else None
    metrics["interest_coverage"] = round(ebit / abs(interest_expense), 2) if interest_expense and interest_expense != 0 else None
    metrics["net_profit_margin"] = round(net_income / revenue * 100, 2) if revenue else None
    metrics["revenue_M"] = round(revenue / 1_000_000, 2)
    metrics["net_income_M"] = round(net_income / 1_000_000, 2)
    return metrics


# ─────────────────────────────────────────────
# Scoring engine
# ─────────────────────────────────────────────

def score_company(ratios_list, income_metrics, overview):
    """
    Multi-factor scoring: 0-100. Returns score, breakdown, flags, recommendation.
    ratios_list: list of ratio dicts ordered newest-first.
    """
    latest = ratios_list[0]
    flags = []
    scores = {}

    # ── Liquidity (25 pts) ──────────────────
    liq_score = 0
    cr = latest.get("current_ratio")
    qr = latest.get("quick_ratio")
    if cr is not None:
        if cr >= 2.0:
            liq_score += 12
        elif cr >= 1.5:
            liq_score += 10
        elif cr >= 1.0:
            liq_score += 7
        else:
            liq_score += 2
            flags.append(f"⚠️ Current ratio {cr} < 1.0 — potential short-term liquidity risk")
    if qr is not None:
        if qr >= 1.5:
            liq_score += 13
        elif qr >= 1.0:
            liq_score += 10
        elif qr >= 0.7:
            liq_score += 6
        else:
            liq_score += 2
            flags.append(f"⚠️ Quick ratio {qr} < 0.7 — limited liquid assets relative to current obligations")
    scores["liquidity"] = {"score": liq_score, "max": 25}

    # ── Leverage / Solvency (25 pts) ────────
    lev_score = 0
    de = latest.get("debt_to_equity")
    da = latest.get("debt_to_assets")
    neg_eq = latest.get("negative_equity", False)
    if neg_eq:
        lev_score = 0
        flags.append("🚨 NEGATIVE EQUITY detected — liabilities exceed assets (high insolvency risk)")
    else:
        if de is not None:
            if de < 0.5:
                lev_score += 13
            elif de < 1.0:
                lev_score += 10
            elif de < 2.0:
                lev_score += 6
            else:
                lev_score += 2
                flags.append(f"⚠️ High Debt-to-Equity ratio: {de} — company is heavily leveraged")
        if da is not None:
            if da < 0.3:
                lev_score += 12
            elif da < 0.5:
                lev_score += 9
            elif da < 0.7:
                lev_score += 5
            else:
                lev_score += 1
                flags.append(f"⚠️ Debt-to-Assets {da} > 0.7 — over 70% of assets financed by debt")
    scores["leverage"] = {"score": lev_score, "max": 25}

    # ── Profitability (25 pts) ───────────────
    prof_score = 0
    roa = income_metrics.get("roa")
    roe = income_metrics.get("roe")
    npm = income_metrics.get("net_profit_margin")
    if roa is not None:
        if roa > 15:
            prof_score += 9
        elif roa > 8:
            prof_score += 7
        elif roa > 3:
            prof_score += 4
        elif roa > 0:
            prof_score += 2
        else:
            flags.append(f"🚨 Negative ROA ({roa}%) — company is destroying asset value")
    if roe is not None:
        if roe > 20:
            prof_score += 9
        elif roe > 12:
            prof_score += 7
        elif roe > 5:
            prof_score += 4
        elif roe > 0:
            prof_score += 2
        else:
            if not latest.get("negative_equity"):
                flags.append(f"⚠️ Negative ROE ({roe}%) — equity holders are losing value")
    if npm is not None:
        if npm > 20:
            prof_score += 7
        elif npm > 10:
            prof_score += 5
        elif npm > 3:
            prof_score += 3
        elif npm > 0:
            prof_score += 1
        else:
            flags.append(f"⚠️ Negative net profit margin ({npm}%)")
    scores["profitability"] = {"score": prof_score, "max": 25}

    # ── Trend / Growth (15 pts) ─────────────
    trend_score = 0
    if len(ratios_list) >= 2:
        prev = ratios_list[1]
        eq_now = latest.get("total_equity_M", 0)
        eq_prev = prev.get("total_equity_M", 1)
        debt_now = latest.get("total_debt_M", 0)
        debt_prev = prev.get("total_debt_M", 1) or 1

        eq_growth = (eq_now - eq_prev) / abs(eq_prev) * 100 if eq_prev else 0
        debt_growth = (debt_now - debt_prev) / abs(debt_prev) * 100 if debt_prev else 0

        if eq_growth > 10:
            trend_score += 8
        elif eq_growth > 0:
            trend_score += 5
        else:
            trend_score += 0
            flags.append(f"⚠️ Equity declining YoY ({eq_growth:.1f}%) — equity base eroding")

        if debt_growth < 0:
            trend_score += 7
        elif debt_growth < 10:
            trend_score += 5
        elif debt_growth < 25:
            trend_score += 3
        else:
            trend_score += 0
            flags.append(f"⚠️ Debt growing rapidly ({debt_growth:.1f}% YoY)")
    else:
        trend_score = 8  # neutral if only one period
    scores["trend"] = {"score": trend_score, "max": 15}

    # ── Interest Coverage bonus (10 pts) ────
    cov_score = 0
    ic = income_metrics.get("interest_coverage")
    if ic is not None:
        if ic > 10:
            cov_score = 10
        elif ic > 5:
            cov_score = 8
        elif ic > 3:
            cov_score = 5
        elif ic > 1.5:
            cov_score = 3
        else:
            cov_score = 0
            flags.append(f"🚨 Interest coverage ratio {ic} < 1.5 — earnings may not cover interest payments")
    else:
        cov_score = 5  # neutral if no debt
    scores["interest_coverage"] = {"score": cov_score, "max": 10}

    total = sum(s["score"] for s in scores.values())
    max_total = sum(s["max"] for s in scores.values())
    pct = round(total / max_total * 100, 1)

    if pct >= 72:
        recommendation = "BUY"
        confidence = "High" if pct >= 82 else "Medium"
        reasoning = "Strong balance sheet fundamentals with healthy liquidity, manageable debt, and solid profitability."
    elif pct >= 50:
        recommendation = "HOLD"
        confidence = "Medium"
        reasoning = "Mixed fundamentals — some strengths offset by areas of concern. Monitor for improvement."
    else:
        recommendation = "SELL"
        confidence = "High" if pct <= 35 else "Medium"
        reasoning = "Weak balance sheet fundamentals indicating elevated financial risk."

    if latest.get("negative_equity"):
        recommendation = "SELL"
        confidence = "High"
        reasoning = "Negative shareholder equity is a critical red flag indicating the company owes more than it owns."

    return {
        "recommendation": recommendation,
        "confidence": confidence,
        "score": total,
        "max_score": max_total,
        "score_pct": pct,
        "reasoning": reasoning,
        "category_scores": scores,
        "risk_flags": flags,
    }


# ─────────────────────────────────────────────
# Action handlers
# ─────────────────────────────────────────────

def do_fetch_balance_sheet(key, inp):
    symbol = inp.get("symbol", "").strip().upper()
    if not symbol:
        return {"error": "Provide a stock ticker symbol (e.g. 'AAPL')"}
    period = inp.get("period", "annual")
    years = min(int(inp.get("years", 3)), 5)
    reports = fetch_balance_sheet_data(key, symbol, period)[:years]
    cleaned = []
    for r in reports:
        ratios = calc_ratios(r)
        cleaned.append({
            "fiscal_date": r.get("fiscalDateEnding", ""),
            "reported_currency": r.get("reportedCurrency", "USD"),
            "ratios": ratios,
            "raw_highlights": {
                "totalAssets": r.get("totalAssets"),
                "totalLiabilities": r.get("totalLiabilities"),
                "totalShareholderEquity": r.get("totalShareholderEquity"),
                "totalCurrentAssets": r.get("totalCurrentAssets"),
                "totalCurrentLiabilities": r.get("totalCurrentLiabilities"),
                "longTermDebt": r.get("longTermDebt"),
                "shortTermDebt": r.get("shortTermDebt") or r.get("currentDebt"),
                "cashAndCashEquivalents": r.get("cashAndCashEquivalentsAtCarryingValue"),
                "retainedEarnings": r.get("retainedEarnings"),
                "inventory": r.get("inventory"),
            }
        })
    return {"symbol": symbol, "period": period, "periods_returned": len(cleaned), "balance_sheets": cleaned}


def do_analyze_company(key, inp):
    symbol = inp.get("symbol", "").strip().upper()
    if not symbol:
        return {"error": "Provide a stock ticker symbol (e.g. 'MSFT')"}
    period = inp.get("period", "annual")
    years = min(int(inp.get("years", 3)), 5)

    bs_reports = fetch_balance_sheet_data(key, symbol, period)[:years]
    inc_reports = fetch_income_data(key, symbol, period)[:years]
    try:
        overview = fetch_overview(key, symbol)
    except Exception:
        overview = {}

    ratios_list = [calc_ratios(r) for r in bs_reports]
    income_metrics = calc_income_metrics(inc_reports, bs_reports[0]) if bs_reports else {}
    scoring = score_company(ratios_list, income_metrics, overview)

    periods = [r.get("fiscalDateEnding", "") for r in bs_reports]

    return {
        "symbol": symbol,
        "company_name": overview.get("Name", symbol),
        "sector": overview.get("Sector", "N/A"),
        "industry": overview.get("Industry", "N/A"),
        "period": period,
        "periods_analyzed": periods,
        "recommendation": scoring["recommendation"],
        "confidence": scoring["confidence"],
        "financial_health_score": f"{scoring['score_pct']}%",
        "reasoning": scoring["reasoning"],
        "risk_flags": scoring["risk_flags"],
        "category_scores": scoring["category_scores"],
        "latest_ratios": {
            "liquidity": {
                "current_ratio": ratios_list[0].get("current_ratio"),
                "quick_ratio": ratios_list[0].get("quick_ratio"),
                "cash_ratio": ratios_list[0].get("cash_ratio"),
            },
            "leverage": {
                "debt_to_equity": ratios_list[0].get("debt_to_equity"),
                "debt_to_assets": ratios_list[0].get("debt_to_assets"),
                "total_liabilities_to_equity": ratios_list[0].get("total_liabilities_to_equity"),
                "equity_multiplier": ratios_list[0].get("equity_multiplier"),
                "negative_equity": ratios_list[0].get("negative_equity"),
            },
            "profitability": {
                "roa_pct": income_metrics.get("roa"),
                "roe_pct": income_metrics.get("roe"),
                "net_profit_margin_pct": income_metrics.get("net_profit_margin"),
                "asset_turnover": income_metrics.get("asset_turnover"),
                "interest_coverage": income_metrics.get("interest_coverage"),
            },
            "size_USD_millions": {
                "total_assets": ratios_list[0].get("total_assets_M"),
                "total_liabilities": ratios_list[0].get("total_liabilities_M"),
                "total_equity": ratios_list[0].get("total_equity_M"),
                "total_debt": ratios_list[0].get("total_debt_M"),
                "cash_and_investments": ratios_list[0].get("cash_M"),
                "revenue": income_metrics.get("revenue_M"),
                "net_income": income_metrics.get("net_income_M"),
            }
        },
        "historical_trends": [
            {"period": bs_reports[i].get("fiscalDateEnding", ""), "equity_M": ratios_list[i].get("total_equity_M"), "debt_M": ratios_list[i].get("total_debt_M"), "current_ratio": ratios_list[i].get("current_ratio")}
            for i in range(len(ratios_list))
        ]
    }


def do_compare_companies(key, inp):
    symbols = inp.get("symbols", [])
    if not symbols or len(symbols) < 2:
        return {"error": "Provide at least 2 symbols in the 'symbols' array (e.g. ['AAPL', 'MSFT'])"}
    period = inp.get("period", "annual")
    results = []
    errors = []

    for sym in symbols[:5]:
        try:
            sym = sym.strip().upper()
            bs_reports = fetch_balance_sheet_data(key, sym, period)[:3]
            inc_reports = fetch_income_data(key, sym, period)[:3]
            try:
                overview = fetch_overview(key, sym)
            except Exception:
                overview = {}
            ratios_list = [calc_ratios(r) for r in bs_reports]
            income_metrics = calc_income_metrics(inc_reports, bs_reports[0]) if bs_reports else {}
            scoring = score_company(ratios_list, income_metrics, overview)
            latest = ratios_list[0]
            results.append({
                "symbol": sym,
                "company_name": overview.get("Name", sym),
                "sector": overview.get("Sector", "N/A"),
                "recommendation": scoring["recommendation"],
                "health_score_pct": scoring["score_pct"],
                "current_ratio": latest.get("current_ratio"),
                "debt_to_equity": latest.get("debt_to_equity"),
                "roa_pct": income_metrics.get("roa"),
                "roe_pct": income_metrics.get("roe"),
                "net_profit_margin_pct": income_metrics.get("net_profit_margin"),
                "negative_equity": latest.get("negative_equity"),
                "top_risks": scoring["risk_flags"][:2],
            })
        except Exception as e:
            errors.append({"symbol": sym, "error": str(e)})

    results.sort(key=lambda x: x["health_score_pct"], reverse=True)
    for i, r in enumerate(results):
        r["rank"] = i + 1

    return {"comparison": results, "errors": errors, "winner": results[0]["symbol"] if results else None}


def do_full_report(key, inp):
    symbol = inp.get("symbol", "").strip().upper()
    if not symbol:
        return {"error": "Provide a stock ticker symbol"}
    period = inp.get("period", "annual")
    years = min(int(inp.get("years", 3)), 5)

    bs_reports = fetch_balance_sheet_data(key, symbol, period)[:years]
    inc_reports = fetch_income_data(key, symbol, period)[:years]
    try:
        overview = fetch_overview(key, symbol)
    except Exception:
        overview = {}

    ratios_list = [calc_ratios(r) for r in bs_reports]
    income_metrics = calc_income_metrics(inc_reports, bs_reports[0]) if bs_reports else {}
    scoring = score_company(ratios_list, income_metrics, overview)
    latest = ratios_list[0]

    rec_color = {"BUY": "#16a34a", "HOLD": "#d97706", "SELL": "#dc2626"}.get(scoring["recommendation"], "#6b7280")
    flags_html = "".join(f"<li style='margin:4px 0;color:#b45309;'>{f}</li>" for f in scoring["risk_flags"]) or "<li style='color:#16a34a;'>No major risk flags detected.</li>"

    historical_rows = ""
    for i, r in enumerate(bs_reports):
        rat = ratios_list[i]
        historical_rows += f"""
        <tr>
          <td>{r.get('fiscalDateEnding','')}</td>
          <td>${rat.get('total_assets_M','N/A')}M</td>
          <td>${rat.get('total_liabilities_M','N/A')}M</td>
          <td>${rat.get('total_equity_M','N/A')}M</td>
          <td>${rat.get('total_debt_M','N/A')}M</td>
          <td>{rat.get('current_ratio','N/A')}</td>
          <td>{rat.get('debt_to_equity','N/A')}</td>
        </tr>"""

    cat_rows = ""
    for cat, s in scoring["category_scores"].items():
        pct = round(s["score"] / s["max"] * 100)
        bar_color = "#16a34a" if pct >= 70 else ("#d97706" if pct >= 45 else "#dc2626")
        cat_rows += f"""
        <tr>
          <td style='text-transform:capitalize;'>{cat.replace('_',' ')}</td>
          <td>{s['score']}/{s['max']}</td>
          <td><div style='background:#e5e7eb;border-radius:4px;height:16px;width:200px;'>
            <div style='background:{bar_color};width:{pct * 2}px;height:16px;border-radius:4px;'></div>
          </div></td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{symbol} Balance Sheet Analysis</title>
<style>
  body {{font-family:Arial,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;color:#1f2937;}}
  h1{{color:#111827;}} h2{{color:#374151;border-bottom:2px solid #e5e7eb;padding-bottom:8px;}}
  .rec-box{{background:{rec_color};color:white;padding:24px;border-radius:12px;text-align:center;margin:24px 0;}}
  .rec-box h2{{color:white;border:none;font-size:2em;}} .rec-box p{{font-size:1.1em;opacity:0.9;}}
  table{{width:100%;border-collapse:collapse;margin:16px 0;}}
  th{{background:#f3f4f6;padding:10px;text-align:left;font-weight:600;}}
  td{{padding:10px;border-bottom:1px solid #e5e7eb;}}
  tr:hover{{background:#f9fafb;}} .metric{{display:inline-block;margin:8px;padding:12px 20px;background:#f3f4f6;border-radius:8px;min-width:140px;text-align:center;}}
  .metric .value{{font-size:1.4em;font-weight:700;color:#1d4ed8;}} .metric .label{{font-size:0.8em;color:#6b7280;margin-top:4px;}}
  ul{{padding-left:20px;}} .footer{{color:#9ca3af;font-size:0.8em;margin-top:40px;text-align:center;border-top:1px solid #e5e7eb;padding-top:16px;}}
</style>
</head>
<body>
<h1>📊 Balance Sheet Analysis: {overview.get('Name', symbol)} ({symbol})</h1>
<p><strong>Sector:</strong> {overview.get('Sector','N/A')} &nbsp;|&nbsp; <strong>Industry:</strong> {overview.get('Industry','N/A')} &nbsp;|&nbsp; <strong>Period:</strong> {period.capitalize()}</p>
<p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}</p>

<div class="rec-box">
  <h2>{scoring['recommendation']}</h2>
  <p><strong>Financial Health Score: {scoring['score_pct']}%</strong> | Confidence: {scoring['confidence']}</p>
  <p>{scoring['reasoning']}</p>
</div>

<h2>📈 Key Metrics (Most Recent Period)</h2>
<div>
  <div class="metric"><div class="value">{latest.get('current_ratio','N/A')}</div><div class="label">Current Ratio</div></div>
  <div class="metric"><div class="value">{latest.get('quick_ratio','N/A')}</div><div class="label">Quick Ratio</div></div>
  <div class="metric"><div class="value">{latest.get('debt_to_equity','N/A')}</div><div class="label">Debt/Equity</div></div>
  <div class="metric"><div class="value">{income_metrics.get('roa','N/A')}%</div><div class="label">ROA</div></div>
  <div class="metric"><div class="value">{income_metrics.get('roe','N/A')}%</div><div class="label">ROE</div></div>
  <div class="metric"><div class="value">{income_metrics.get('net_profit_margin','N/A')}%</div><div class="label">Net Margin</div></div>
  <div class="metric"><div class="value">{income_metrics.get('interest_coverage','N/A')}</div><div class="label">Interest Coverage</div></div>
</div>

<h2>🎯 Scoring Breakdown</h2>
<table><thead><tr><th>Category</th><th>Score</th><th>Performance</th></tr></thead><tbody>{cat_rows}</tbody></table>

<h2>⚠️ Risk Flags</h2>
<ul>{flags_html}</ul>

<h2>📅 Historical Balance Sheet Summary</h2>
<table>
<thead><tr><th>Period</th><th>Total Assets</th><th>Total Liabilities</th><th>Equity</th><th>Total Debt</th><th>Current Ratio</th><th>D/E Ratio</th></tr></thead>
<tbody>{historical_rows}</tbody>
</table>

<div class="footer">
  <p>⚠️ This report is for informational purposes only and does not constitute financial advice. Always consult a qualified financial advisor before making investment decisions.</p>
  <p>Data sourced from Alpha Vantage. Report generated by Balance Sheet Analyzer.</p>
</div>
</body>
</html>"""

    filepath = f"{symbol}_balance_sheet_report.html"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"A2ABASEAI_FILE: {filepath}")
    return {
        "status": "ok",
        "filename": filepath,
        "symbol": symbol,
        "recommendation": scoring["recommendation"],
        "health_score_pct": scoring["score_pct"],
        "confidence": scoring["confidence"],
        "risk_flag_count": len(scoring["risk_flags"]),
    }


# ─────────────────────────────────────────────
# Main dispatch
# ─────────────────────────────────────────────

try:
    api_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
    if not api_key:
        raise Exception("ALPHA_VANTAGE_API_KEY environment variable is not set. Get a free key at alphavantage.co")

    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    action = inp.get("action", "").strip()

    if action == "fetch_balance_sheet":
        result = do_fetch_balance_sheet(api_key, inp)
    elif action == "analyze_company":
        result = do_analyze_company(api_key, inp)
    elif action == "compare_companies":
        result = do_compare_companies(api_key, inp)
    elif action == "full_report":
        result = do_full_report(api_key, inp)
    else:
        result = {"error": f"Unknown action: '{action}'. Available: fetch_balance_sheet, analyze_company, compare_companies, full_report"}

    print(json.dumps(result))

except Exception as e:
    print(json.dumps({"error": str(e)}))