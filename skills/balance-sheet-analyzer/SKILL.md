---
name: balance-sheet-analyzer
display_name: "Balance Sheet Analyzer"
description: "Fetch, parse, and analyze company balance sheets from the internet to generate buy/sell/hold investment recommendations using fundamental accounting analysis including assets, liabilities, equity, debt ratios, liquidity, and profitability metrics."
category: finance
icon: bar-chart
skill_type: sandbox
catalog_type: addon
requirements: "httpx>=0.25,beautifulsoup4>=4.12,lxml>=4.9"
resource_requirements:
  - env_var: ALPHA_VANTAGE_API_KEY
    name: "Alpha Vantage API Key"
    description: "Free API key from alphavantage.co (supports balance sheet, income statement, cash flow data)"
tool_schema:
  name: balance-sheet-analyzer
  description: "Fetch and analyze company balance sheets to produce buy/sell/hold recommendations using fundamental accounting metrics like debt ratios, liquidity, leverage, and equity analysis."
  parameters:
    type: object
    properties:
      action:
        type: "string"
        description: "Which operation to perform"
        enum: ["fetch_balance_sheet", "analyze_company", "compare_companies", "full_report"]
      symbol:
        type: "string"
        description: "Stock ticker symbol (e.g. 'AAPL', 'MSFT', 'TSLA')"
        default: ""
      symbols:
        type: "array"
        items:
          type: "string"
        description: "List of ticker symbols for comparison (e.g. ['AAPL','MSFT'])"
        default: []
      period:
        type: "string"
        description: "Reporting period: 'annual' or 'quarterly'"
        enum: ["annual", "quarterly"]
        default: "annual"
      years:
        type: "integer"
        description: "Number of years/periods of data to analyze (1-5)"
        default: 3
    required: ["action"]
---
# Balance Sheet Analyzer

Fetch real-time company balance sheet data and apply institutional-grade fundamental analysis to generate investment recommendations. Uses accounting ratios, trend analysis, and multi-factor scoring to produce BUY / SELL / HOLD signals with detailed reasoning.

## Actions

### fetch_balance_sheet
Retrieve raw balance sheet data for a company.

**Example:** `action: fetch_balance_sheet, symbol: "AAPL", period: "annual"`

Returns: Assets (current/non-current), Liabilities (current/long-term), Shareholders' Equity, key line items across multiple periods.

---

### analyze_company
Run full fundamental analysis on a company's balance sheet and financials to generate a recommendation.

**Example:** `action: analyze_company, symbol: "TSLA", period: "annual", years: 3`

Returns:
- **Recommendation**: BUY / HOLD / SELL with confidence score
- **Liquidity Ratios**: Current Ratio, Quick Ratio, Cash Ratio
- **Leverage Ratios**: Debt-to-Equity, Debt-to-Assets, Interest Coverage
- **Efficiency**: Asset Turnover, Return on Assets (ROA), Return on Equity (ROE)
- **Growth Trends**: YoY changes in equity, assets, liabilities
- **Risk Flags**: Insolvency risk, overleveraged, negative equity warnings
- **Scoring Breakdown**: Per-category scores explaining the final recommendation

---

### compare_companies
Compare multiple companies side-by-side on key balance sheet metrics and rank them.

**Example:** `action: compare_companies, symbols: ["AAPL", "MSFT", "GOOGL"]`

Returns: Ranked table of companies by financial health score with individual metric comparisons.

---

### full_report
Generate a detailed HTML investment report with full analysis, ratios, and recommendation saved to file.

**Example:** `action: full_report, symbol: "NVDA", period: "annual", years: 3`

Returns: HTML report file path with complete analysis, charts description, and recommendation.

---

## Usage Tips

- **Be Proactive**: When a user mentions a company name, look up the ticker symbol automatically and run `analyze_company` without waiting for confirmation.
- **Combine actions**: Run `analyze_company` first, then offer `full_report` for a downloadable version.
- **Interpret results**: Always explain the recommendation in plain English — don't just return numbers. Explain what a high debt-to-equity ratio means for that specific company.
- **Flag risks**: If negative equity, declining current ratio below 1.0, or rapidly growing long-term debt is detected, proactively warn the user.
- **Context matters**: Consider the industry when interpreting ratios (e.g., banks naturally have high leverage; tech companies should have low debt).
- **Trend analysis**: A single period is less meaningful — always try to analyze at least 3 years to spot trends.