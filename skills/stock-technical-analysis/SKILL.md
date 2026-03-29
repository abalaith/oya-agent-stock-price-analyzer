---
name: stock-technical-analysis
display_name: "Stock Technical Analysis"
description: "Analyze stocks using RSI, MACD, VWAP, Moving Average, and EMA technical indicators to provide trading signals and insights"
category: finance
icon: bar-chart
skill_type: sandbox
catalog_type: addon
requirements: "httpx>=0.25,pandas>=2.0,numpy>=1.24,yfinance>=0.2"
tool_schema:
  name: stock-technical-analysis
  description: "Analyze stocks using RSI, MACD, VWAP, Moving Average, and EMA technical indicators to provide trading signals and insights"
  parameters:
    type: object
    properties:
      action:
        type: "string"
        description: "Which analysis to perform"
        enum: ["full_analysis", "rsi", "macd", "vwap", "moving_averages", "summary"]
      symbol:
        type: "string"
        description: "Stock ticker symbol (e.g. 'AAPL', 'TSLA', 'MSFT')"
        default: ""
      period:
        type: "string"
        description: "Historical data period: '1mo', '3mo', '6mo', '1y', '2y'"
        default: "6mo"
      interval:
        type: "string"
        description: "Data interval: '1d' (daily), '1h' (hourly), '1wk' (weekly)"
        default: "1d"
      rsi_period:
        type: "integer"
        description: "RSI calculation period (default 14)"
        default: 14
      fast_period:
        type: "integer"
        description: "MACD fast EMA period (default 12)"
        default: 12
      slow_period:
        type: "integer"
        description: "MACD slow EMA period (default 26)"
        default: 26
      signal_period:
        type: "integer"
        description: "MACD signal line period (default 9)"
        default: 9
      ma_periods:
        type: "string"
        description: "Comma-separated MA periods (e.g. '20,50,200')"
        default: "20,50,200"
    required: ["action", "symbol"]
---
# Stock Technical Analysis

Perform comprehensive technical analysis on any stock using RSI, MACD, VWAP, Moving Averages, and EMA indicators. Returns current values, signals, actionable insights, and a weighted buy/sell recommendation score between 0 and 1.

## Buy/Sell Score

Every `full_analysis` and `summary` response includes a `recommendation_score` between **0.0 and 1.0**:

- **0.0** = strongest sell signal
- **0.5** = neutral / no clear direction
- **1.0** = strongest buy signal

Each indicator contributes a weighted component to the score:

- RSI (weight 0.25): oversold → 1.0, overbought → 0.0, bullish → 0.75, bearish → 0.25, neutral → 0.5
- MACD (weight 0.25): bullish_crossover → 1.0, bullish → 0.75, bearish_crossover → 0.0, bearish → 0.25, neutral → 0.5
- VWAP (weight 0.20): above_vwap → 1.0, below_vwap → 0.0
- MA cross (weight 0.20): golden_cross → 1.0, bullish_alignment → 0.75, bearish_alignment → 0.25, death_cross → 0.0, neutral → 0.5
- Price vs SMA50 (weight 0.10): above → 1.0, below → 0.0

The `recommendation_label` maps the score to a human-readable label:

- 0.80 – 1.00 → "Strong Buy"
- 0.60 – 0.79 → "Buy"
- 0.40 – 0.59 → "Neutral"
- 0.20 – 0.39 → "Sell"
- 0.00 – 0.19 → "Strong Sell"

## Actions

### full_analysis
Run all technical indicators at once for a complete view.
- action: full_analysis, symbol: "AAPL", period: "6mo"
- Returns: RSI, MACD, VWAP, MA(20/50/200), EMA(9/21), signals, overall bias, recommendation_score, recommendation_label

### rsi
Calculate the Relative Strength Index to identify overbought/oversold conditions.
- action: rsi, symbol: "TSLA", period: "3mo", rsi_period: 14
- Returns: current RSI value, signal (overbought/oversold/neutral), trend, recent RSI history

### macd
Calculate MACD (Moving Average Convergence Divergence) for momentum analysis.
- action: macd, symbol: "MSFT", fast_period: 12, slow_period: 26, signal_period: 9
- Returns: MACD line, signal line, histogram, crossover signal (bullish/bearish)

### vwap
Calculate Volume Weighted Average Price for intraday value assessment.
- action: vwap, symbol: "NVDA", period: "1mo"
- Returns: VWAP value, current price vs VWAP, signal (above/below), percentage deviation

### moving_averages
Calculate Simple Moving Averages (SMA) and Exponential Moving Averages (EMA).
- action: moving_averages, symbol: "GOOGL", ma_periods: "20,50,200"
- Returns: SMA and EMA values, golden/death cross signals, price vs MA relationships

### summary
Get a concise trading summary with all key signals, overall recommendation, and weighted score.
- action: summary, symbol: "SPY", period: "3mo"
- Returns: bullish/bearish/neutral signal count, overall bias, key levels, recommendation_score, recommendation_label

## Usage Tips

- **Always start with `full_analysis` or `summary`** for a complete picture before diving into individual indicators.
- Use `recommendation_score` for programmatic decision-making; use `recommendation_label` for human-readable guidance.
- **RSI > 70** = overbought (potential sell), **RSI < 30** = oversold (potential buy).
- **MACD crossover** above signal line = bullish momentum; below = bearish momentum.
- **Price above VWAP** = bullish intraday bias; below = bearish.
- **Golden Cross** (50 MA crosses above 200 MA) = long-term bullish signal.
- **Death Cross** (50 MA crosses below 200 MA) = long-term bearish signal.
- Use `period: "1y"` or `"2y"` for long-term trend analysis and `"1mo"` for short-term signals.
- Combine multiple indicators for higher-confidence signals — no single indicator is definitive.