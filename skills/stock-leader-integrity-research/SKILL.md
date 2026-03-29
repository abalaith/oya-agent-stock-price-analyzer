---
name: stock-leader-integrity-research
display_name: "Stock Leader Integrity Research"
description: "Deep internet research on company/stock leaders to uncover fraud history, short-selling activity, misleading disclosures, critical lawsuits, SEC violations, and unethical price manipulation behaviors"
category: finance
icon: search
skill_type: sandbox
catalog_type: addon
requirements: "httpx>=0.25"
resource_requirements:
  - env_var: SERPAPI_KEY
    name: "SerpApi API Key"
    description: "API key from SerpApi (https://serpapi.com/dashboard) — used to perform deep Google search queries"
tool_schema:
  name: stock-leader-integrity-research
  description: "Research company executives and stock leaders for fraud history, SEC violations, lawsuits, short-selling schemes, misleading disclosures, and unethical market manipulation"
  parameters:
    type: object
    properties:
      action:
        type: "string"
        description: "Which research operation to perform"
        enum: ["full_report", "fraud_history", "sec_violations", "lawsuits", "short_selling", "misleading_news", "leadership_background"]
      person_name:
        type: "string"
        description: "Full name of the executive/leader to research (e.g. 'Elon Musk')"
        default: ""
      company_name:
        type: "string"
        description: "Company or stock name/ticker (e.g. 'Tesla' or 'TSLA')"
        default: ""
      ticker:
        type: "string"
        description: "Stock ticker symbol (e.g. 'TSLA', 'AAPL')"
        default: ""
      limit:
        type: "integer"
        description: "Max search results per query (1-20)"
        default: 10
    required: [action]
---
# Stock Leader Integrity Research

Perform deep internet research on executives, CEOs, CFOs, and other leaders of publicly traded companies to identify potential fraud, SEC violations, short-selling schemes, misleading disclosures, critical lawsuits, or any unethical market manipulation activity.

## Actions

### full_report
Run a comprehensive multi-angle investigation across all categories for a person and/or company.
- action: full_report, person_name: "Adam Neumann", company_name: "WeWork"
- action: full_report, ticker: "TSLA", person_name: "Elon Musk"
Returns: Aggregated findings across fraud, SEC violations, lawsuits, short-selling, and misleading news categories. Includes risk_summary with flagged red-flag keywords.

### fraud_history
Search specifically for documented fraud allegations, Ponzi schemes, financial misrepresentation, or conviction history.
- action: fraud_history, person_name: "Elizabeth Holmes", company_name: "Theranos"
Returns: News and legal results referencing fraud, misrepresentation, conviction, or deceptive practices.

### sec_violations
Search SEC enforcement actions, EDGAR filings, cease-and-desist orders, and regulatory penalties.
- action: sec_violations, person_name: "Sam Bankman-Fried", company_name: "FTX"
Returns: SEC and FINRA enforcement actions, fines, suspensions, and regulatory findings.

### lawsuits
Find critical lawsuits including securities class actions, shareholder suits, and DOJ/FBI investigations.
- action: lawsuits, person_name: "Trevor Milton", company_name: "Nikola", ticker: "NKLA"
Returns: Major lawsuits, settlements, class action filings, and DOJ/FBI investigation details.

### short_selling
Identify short-selling campaigns, short reports from activist firms, and coordinated price depression tactics.
- action: short_selling, company_name: "Herbalife", ticker: "HLF"
Returns: Short reports (Hindenburg, Citron, etc.), short interest data mentions, and short-squeeze events.

### misleading_news
Find instances of misleading press releases, pump-and-dump schemes, false forward-looking statements, and stock promotion fraud.
- action: misleading_news, person_name: "Elon Musk", company_name: "Tesla", ticker: "TSLA"
Returns: Reports on misleading announcements, SEC Twitter violations, inflated guidance, and stock promotion incidents.

### leadership_background
General background research: prior companies, controversies, reputation, and track record.
- action: leadership_background, person_name: "Do Kwon", company_name: "Terraform Labs"
Returns: Professional history, past company failures, controversies, and credibility indicators.

## Usage Tips

- **Be Proactive**: When a user mentions a stock or company, automatically identify the CEO/CFO/key leaders and run a `full_report` on them without being asked.
- **Flag Red Signals**: Summarize the most critical findings at the top of your response with a risk level: LOW / MEDIUM / HIGH / CRITICAL.
- **Cross-reference**: Use `ticker` + `person_name` + `company_name` together for best coverage.
- **Investment Context**: Always remind users that research findings are informational and should not be treated as investment advice.
- **Follow-up**: After a `full_report`, offer to deep-dive into any specific category that showed concerning results.
- **Combine with filings**: Pair this skill with SEC EDGAR searches when `sec_violations` returns hits.