import os
import json
import warnings
warnings.filterwarnings("ignore")

try:
    import pandas as pd
    import numpy as np
    import yfinance as yf
except ImportError as e:
    import json
    print(json.dumps({"error": f"Missing dependency: {e}. Ensure pandas, numpy, yfinance are installed."}))
    raise SystemExit


# ── Data fetching ──────────────────────────────────────────────────────────────

def fetch_data(symbol: str, period: str, interval: str) -> pd.DataFrame:
    ticker = yf.Ticker(symbol.upper())
    df = ticker.history(period=period, interval=interval, auto_adjust=True)
    if df.empty:
        raise ValueError(f"No data returned for '{symbol}'. Check the ticker symbol and period.")
    df.index = pd.to_datetime(df.index)
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(df) < 30:
        raise ValueError(f"Insufficient data for '{symbol}' ({len(df)} rows). Try a longer period.")
    return df


def get_ticker_info(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol.upper()).fast_info
        return {
            "symbol": symbol.upper(),
            "current_price": round(float(info.last_price), 4) if info.last_price else None,
        }
    except Exception:
        return {"symbol": symbol.upper(), "current_price": None}


# ── Indicator calculations ─────────────────────────────────────────────────────

def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_tpv = (typical * df["Volume"]).cumsum()
    cum_vol = df["Volume"].cumsum()
    return cum_tpv / cum_vol.replace(0, np.nan)


def calc_sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(window=period).mean()


def calc_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def rsi_signal(value: float) -> str:
    if value >= 70:
        return "overbought"
    elif value <= 30:
        return "oversold"
    elif value >= 60:
        return "bullish"
    elif value <= 40:
        return "bearish"
    return "neutral"


def macd_signal(hist: float, prev_hist: float) -> str:
    if hist > 0 and prev_hist <= 0:
        return "bullish_crossover"
    elif hist < 0 and prev_hist >= 0:
        return "bearish_crossover"
    elif hist > 0:
        return "bullish"
    elif hist < 0:
        return "bearish"
    return "neutral"


def safe_float(val, decimals: int = 4):
    try:
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        return round(float(val), decimals)
    except Exception:
        return None


# ── Weighted recommendation score ─────────────────────────────────────────────

# Weights must sum to 1.0
_WEIGHTS = {
    "rsi": 0.25,
    "macd": 0.25,
    "vwap": 0.20,
    "ma_cross": 0.20,
    "price_vs_sma50": 0.10,
}

_RSI_SCORES = {
    "oversold": 1.0,
    "bullish": 0.75,
    "neutral": 0.5,
    "bearish": 0.25,
    "overbought": 0.0,
}

_MACD_SCORES = {
    "bullish_crossover": 1.0,
    "bullish": 0.75,
    "neutral": 0.5,
    "bearish": 0.25,
    "bearish_crossover": 0.0,
}

_CROSS_SCORES = {
    "golden_cross": 1.0,
    "bullish_alignment": 0.75,
    "neutral": 0.5,
    "bearish_alignment": 0.25,
    "death_cross": 0.0,
}


def calc_recommendation_score(
    rsi_sig: str,
    macd_sig: str,
    vwap_sig: str,
    cross_signal: str,
    current_price,
    sma50,
) -> float:
    rsi_score = _RSI_SCORES.get(rsi_sig, 0.5)
    macd_score = _MACD_SCORES.get(macd_sig, 0.5)
    vwap_score = 1.0 if vwap_sig == "above_vwap" else 0.0
    cross_score = _CROSS_SCORES.get(cross_signal, 0.5)
    if sma50 and current_price:
        sma50_score = 1.0 if current_price > sma50 else 0.0
    else:
        sma50_score = 0.5

    score = (
        _WEIGHTS["rsi"] * rsi_score
        + _WEIGHTS["macd"] * macd_score
        + _WEIGHTS["vwap"] * vwap_score
        + _WEIGHTS["ma_cross"] * cross_score
        + _WEIGHTS["price_vs_sma50"] * sma50_score
    )
    return round(score, 4)


def recommendation_label(score: float) -> str:
    if score >= 0.80:
        return "Strong Buy"
    elif score >= 0.60:
        return "Buy"
    elif score >= 0.40:
        return "Neutral"
    elif score >= 0.20:
        return "Sell"
    return "Strong Sell"


# ── Action handlers ────────────────────────────────────────────────────────────

def do_rsi(inp: dict) -> dict:
    symbol = inp.get("symbol", "").strip()
    if not symbol:
        return {"error": "Provide symbol (e.g. 'AAPL')"}
    period = inp.get("period", "6mo")
    interval = inp.get("interval", "1d")
    rsi_period = int(inp.get("rsi_period", 14))
    df = fetch_data(symbol, period, interval)
    rsi = calc_rsi(df["Close"], rsi_period)
    current_rsi = safe_float(rsi.iloc[-1], 2)
    prev_rsi = safe_float(rsi.iloc[-2], 2)
    trend = "rising" if current_rsi > prev_rsi else "falling"
    recent = [safe_float(v, 2) for v in rsi.dropna().tail(5).tolist()]
    return {
        "symbol": symbol.upper(),
        "indicator": "RSI",
        "period": rsi_period,
        "current_rsi": current_rsi,
        "signal": rsi_signal(current_rsi),
        "trend": trend,
        "recent_values": recent,
        "interpretation": f"RSI at {current_rsi} is {rsi_signal(current_rsi)} and {trend}.",
    }


def do_macd(inp: dict) -> dict:
    symbol = inp.get("symbol", "").strip()
    if not symbol:
        return {"error": "Provide symbol (e.g. 'AAPL')"}
    period = inp.get("period", "6mo")
    interval = inp.get("interval", "1d")
    fast = int(inp.get("fast_period", 12))
    slow = int(inp.get("slow_period", 26))
    signal_p = int(inp.get("signal_period", 9))
    df = fetch_data(symbol, period, interval)
    macd_line, signal_line, histogram = calc_macd(df["Close"], fast, slow, signal_p)
    cur_macd = safe_float(macd_line.iloc[-1])
    cur_signal = safe_float(signal_line.iloc[-1])
    cur_hist = safe_float(histogram.iloc[-1])
    prev_hist = safe_float(histogram.iloc[-2])
    sig = macd_signal(cur_hist or 0, prev_hist or 0)
    return {
        "symbol": symbol.upper(),
        "indicator": "MACD",
        "settings": {"fast": fast, "slow": slow, "signal": signal_p},
        "macd_line": cur_macd,
        "signal_line": cur_signal,
        "histogram": cur_hist,
        "signal": sig,
        "momentum": "positive" if (cur_hist or 0) > 0 else "negative",
        "interpretation": f"MACD histogram is {cur_hist}, signal is {sig}.",
    }


def do_vwap(inp: dict) -> dict:
    symbol = inp.get("symbol", "").strip()
    if not symbol:
        return {"error": "Provide symbol (e.g. 'AAPL')"}
    period = inp.get("period", "1mo")
    interval = inp.get("interval", "1d")
    df = fetch_data(symbol, period, interval)
    vwap = calc_vwap(df)
    current_vwap = safe_float(vwap.iloc[-1])
    current_price = safe_float(df["Close"].iloc[-1])
    if current_vwap and current_price:
        pct_dev = round(((current_price - current_vwap) / current_vwap) * 100, 2)
        sig = "above_vwap" if current_price > current_vwap else "below_vwap"
        bias = "bullish" if current_price > current_vwap else "bearish"
    else:
        pct_dev, sig, bias = None, "unknown", "unknown"
    return {
        "symbol": symbol.upper(),
        "indicator": "VWAP",
        "current_price": current_price,
        "vwap": current_vwap,
        "deviation_pct": pct_dev,
        "signal": sig,
        "bias": bias,
        "interpretation": f"Price is {pct_dev}% {'above' if (pct_dev or 0) >= 0 else 'below'} VWAP ({current_vwap}), indicating a {bias} bias.",
    }


def do_moving_averages(inp: dict) -> dict:
    symbol = inp.get("symbol", "").strip()
    if not symbol:
        return {"error": "Provide symbol (e.g. 'AAPL')"}
    period = inp.get("period", "1y")
    interval = inp.get("interval", "1d")
    ma_periods_str = inp.get("ma_periods", "20,50,200")
    try:
        ma_periods = [int(x.strip()) for x in ma_periods_str.split(",") if x.strip()]
    except ValueError:
        ma_periods = [20, 50, 200]
    df = fetch_data(symbol, period, interval)
    close = df["Close"]
    current_price = safe_float(close.iloc[-1])
    sma_values = {}
    ema_values = {}
    price_vs_sma = {}
    price_vs_ema = {}
    for p in ma_periods:
        if len(df) >= p:
            sma_val = safe_float(calc_sma(close, p).iloc[-1])
            ema_val = safe_float(calc_ema(close, p).iloc[-1])
            sma_values[f"sma_{p}"] = sma_val
            ema_values[f"ema_{p}"] = ema_val
            if sma_val and current_price:
                price_vs_sma[f"sma_{p}"] = "above" if current_price > sma_val else "below"
            if ema_val and current_price:
                price_vs_ema[f"ema_{p}"] = "above" if current_price > ema_val else "below"
    cross_signal = "neutral"
    if "sma_50" in sma_values and "sma_200" in sma_values:
        sma50 = calc_sma(close, 50)
        sma200 = calc_sma(close, 200)
        if (len(sma50.dropna()) >= 2) and (len(sma200.dropna()) >= 2):
            if sma50.iloc[-1] > sma200.iloc[-1] and sma50.iloc[-2] <= sma200.iloc[-2]:
                cross_signal = "golden_cross"
            elif sma50.iloc[-1] < sma200.iloc[-1] and sma50.iloc[-2] >= sma200.iloc[-2]:
                cross_signal = "death_cross"
            elif sma50.iloc[-1] > sma200.iloc[-1]:
                cross_signal = "bullish_alignment"
            else:
                cross_signal = "bearish_alignment"
    ema9 = safe_float(calc_ema(close, 9).iloc[-1])
    ema21 = safe_float(calc_ema(close, 21).iloc[-1])
    return {
        "symbol": symbol.upper(),
        "indicator": "MA/EMA",
        "current_price": current_price,
        "sma": sma_values,
        "ema": ema_values,
        "ema_9": ema9,
        "ema_21": ema21,
        "price_vs_sma": price_vs_sma,
        "price_vs_ema": price_vs_ema,
        "cross_signal": cross_signal,
        "interpretation": f"SMA/EMA cross signal: {cross_signal}. Price is {'above' if price_vs_sma.get('sma_50') == 'above' else 'below'} SMA50.",
    }


def do_full_analysis(inp: dict) -> dict:
    symbol = inp.get("symbol", "").strip()
    if not symbol:
        return {"error": "Provide symbol (e.g. 'AAPL')"}
    period = inp.get("period", "6mo")
    interval = inp.get("interval", "1d")
    rsi_period = int(inp.get("rsi_period", 14))
    fast = int(inp.get("fast_period", 12))
    slow = int(inp.get("slow_period", 26))
    signal_p = int(inp.get("signal_period", 9))
    df = fetch_data(symbol, period, interval)
    close = df["Close"]
    current_price = safe_float(close.iloc[-1])
    # RSI
    rsi = calc_rsi(close, rsi_period)
    cur_rsi = safe_float(rsi.iloc[-1], 2)
    rsi_sig = rsi_signal(cur_rsi)
    # MACD
    macd_line, sig_line, histogram = calc_macd(close, fast, slow, signal_p)
    cur_hist = safe_float(histogram.iloc[-1])
    prev_hist = safe_float(histogram.iloc[-2])
    macd_sig = macd_signal(cur_hist or 0, prev_hist or 0)
    # VWAP
    vwap = calc_vwap(df)
    cur_vwap = safe_float(vwap.iloc[-1])
    vwap_sig = "above_vwap" if (current_price or 0) > (cur_vwap or 0) else "below_vwap"
    vwap_pct = round(((current_price - cur_vwap) / cur_vwap) * 100, 2) if cur_vwap and current_price else None
    # Moving Averages
    sma20 = safe_float(calc_sma(close, 20).iloc[-1]) if len(df) >= 20 else None
    sma50 = safe_float(calc_sma(close, 50).iloc[-1]) if len(df) >= 50 else None
    sma200 = safe_float(calc_sma(close, 200).iloc[-1]) if len(df) >= 200 else None
    ema9 = safe_float(calc_ema(close, 9).iloc[-1])
    ema21 = safe_float(calc_ema(close, 21).iloc[-1])
    # Cross signal
    cross_signal = "neutral"
    if sma50 and sma200:
        s50 = calc_sma(close, 50)
        s200 = calc_sma(close, 200)
        if s50.iloc[-1] > s200.iloc[-1] and s50.iloc[-2] <= s200.iloc[-2]:
            cross_signal = "golden_cross"
        elif s50.iloc[-1] < s200.iloc[-1] and s50.iloc[-2] >= s200.iloc[-2]:
            cross_signal = "death_cross"
        elif s50.iloc[-1] > s200.iloc[-1]:
            cross_signal = "bullish_alignment"
        else:
            cross_signal = "bearish_alignment"
    # Legacy signal counts
    bullish_count = sum([
        rsi_sig in ("oversold", "bullish"),
        macd_sig in ("bullish", "bullish_crossover"),
        vwap_sig == "above_vwap",
        (current_price or 0) > (sma50 or 0) if sma50 else False,
        cross_signal in ("golden_cross", "bullish_alignment"),
    ])
    bearish_count = sum([
        rsi_sig in ("overbought", "bearish"),
        macd_sig in ("bearish", "bearish_crossover"),
        vwap_sig == "below_vwap",
        (current_price or 0) < (sma50 or 0) if sma50 else False,
        cross_signal in ("death_cross", "bearish_alignment"),
    ])
    if bullish_count > bearish_count:
        overall_bias = "bullish"
    elif bearish_count > bullish_count:
        overall_bias = "bearish"
    else:
        overall_bias = "neutral"
    # Weighted recommendation score
    rec_score = calc_recommendation_score(
        rsi_sig=rsi_sig,
        macd_sig=macd_sig,
        vwap_sig=vwap_sig,
        cross_signal=cross_signal,
        current_price=current_price,
        sma50=sma50,
    )
    rec_label = recommendation_label(rec_score)
    return {
        "symbol": symbol.upper(),
        "current_price": current_price,
        "overall_bias": overall_bias,
        "bullish_signals": bullish_count,
        "bearish_signals": bearish_count,
        "recommendation_score": rec_score,
        "recommendation_label": rec_label,
        "rsi": {"value": cur_rsi, "signal": rsi_sig},
        "macd": {
            "macd_line": safe_float(macd_line.iloc[-1]),
            "signal_line": safe_float(sig_line.iloc[-1]),
            "histogram": cur_hist,
            "signal": macd_sig,
        },
        "vwap": {"value": cur_vwap, "signal": vwap_sig, "deviation_pct": vwap_pct},
        "moving_averages": {
            "sma_20": sma20,
            "sma_50": sma50,
            "sma_200": sma200,
            "ema_9": ema9,
            "ema_21": ema21,
            "cross_signal": cross_signal,
        },
        "price_vs_levels": {
            "vs_sma20": ("above" if (current_price or 0) > (sma20 or 0) else "below") if sma20 else None,
            "vs_sma50": ("above" if (current_price or 0) > (sma50 or 0) else "below") if sma50 else None,
            "vs_sma200": ("above" if (current_price or 0) > (sma200 or 0) else "below") if sma200 else None,
            "vs_ema9": ("above" if (current_price or 0) > (ema9 or 0) else "below") if ema9 else None,
            "vs_ema21": ("above" if (current_price or 0) > (ema21 or 0) else "below") if ema21 else None,
            "vs_vwap": vwap_sig,
        },
        "summary": (
            f"{symbol.upper()} at ${current_price} is showing {overall_bias} bias "
            f"({bullish_count} bullish / {bearish_count} bearish signals). "
            f"RSI: {cur_rsi} ({rsi_sig}), MACD: {macd_sig}, VWAP: {vwap_sig} ({vwap_pct}%), "
            f"MA cross: {cross_signal}. "
            f"Recommendation score: {rec_score} ({rec_label})."
        ),
    }


def do_summary(inp: dict) -> dict:
    full = do_full_analysis(inp)
    if "error" in full:
        return full
    return {
        "symbol": full["symbol"],
        "current_price": full["current_price"],
        "overall_bias": full["overall_bias"],
        "bullish_signals": full["bullish_signals"],
        "bearish_signals": full["bearish_signals"],
        "recommendation_score": full["recommendation_score"],
        "recommendation_label": full["recommendation_label"],
        "key_signals": {
            "rsi": f"{full['rsi']['value']} ({full['rsi']['signal']})",
            "macd": full["macd"]["signal"],
            "vwap": f"{full['vwap']['signal']} ({full['vwap']['deviation_pct']}%)",
            "ma_cross": full["moving_averages"]["cross_signal"],
        },
        "key_levels": {
            "vwap": full["vwap"]["value"],
            "sma_20": full["moving_averages"]["sma_20"],
            "sma_50": full["moving_averages"]["sma_50"],
            "sma_200": full["moving_averages"]["sma_200"],
            "ema_9": full["moving_averages"]["ema_9"],
            "ema_21": full["moving_averages"]["ema_21"],
        },
        "recommendation": (
            "Strong buy signal" if full["bullish_signals"] >= 4 else
            "Buy signal" if full["bullish_signals"] >= 3 else
            "Strong sell signal" if full["bearish_signals"] >= 4 else
            "Sell signal" if full["bearish_signals"] >= 3 else
            "Neutral / wait for confirmation"
        ),
        "summary": full["summary"],
    }


# ── Main dispatch ──────────────────────────────────────────────────────────────

try:
    inp = json.loads(os.environ.get("INPUT_JSON", "{}"))
    action = inp.get("action", "").strip()

    dispatch = {
        "full_analysis": do_full_analysis,
        "rsi": do_rsi,
        "macd": do_macd,
        "vwap": do_vwap,
        "moving_averages": do_moving_averages,
        "summary": do_summary,
    }

    if not action:
        result = {"error": "Provide action. Available: full_analysis, rsi, macd, vwap, moving_averages, summary"}
    elif action not in dispatch:
        result = {"error": f"Unknown action '{action}'. Available: {', '.join(dispatch.keys())}"}
    else:
        result = dispatch[action](inp)

    print(json.dumps(result))
except Exception as e:
    print(json.dumps({"error": str(e)}))