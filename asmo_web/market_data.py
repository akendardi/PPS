import math
from datetime import datetime, timedelta
from urllib.parse import quote

import pandas as pd
import requests


MOEX_SEARCH_URL = "https://iss.moex.com/iss/securities.json"
MOEX_HISTORY_URL = "https://iss.moex.com/iss/history/engines/stock/markets/shares/securities"

FEATURED = [
    {"ticker": "MOEX", "name": "Московская биржа"},
    {"ticker": "SBER", "name": "Сбербанк"},
    {"ticker": "GAZP", "name": "Газпром"},
    {"ticker": "LKOH", "name": "Лукойл"},
    {"ticker": "ROSN", "name": "Роснефть"},
    {"ticker": "VTBR", "name": "ВТБ"},
]

INTERVALS = {
    "7d": {"label": "7 дней", "calendar_days": 7, "vol_window": 20},
    "30d": {"label": "30 дней", "calendar_days": 30, "vol_window": 20},
    "90d": {"label": "90 дней", "calendar_days": 90, "vol_window": 30},
    "180d": {"label": "180 дней", "calendar_days": 180, "vol_window": 60},
}


def get_featured_instruments():
    return FEATURED


def get_intervals():
    return INTERVALS


def get_interval_label(code: str) -> str:
    return INTERVALS.get(code, INTERVALS["30d"])["label"]


def search_instruments(query: str):
    query = (query or "").strip()

    if not query:
        return FEATURED

    try:
        url = (
            f"{MOEX_SEARCH_URL}"
            f"?iss.meta=off"
            f"&q={quote(query)}"
            f"&securities.columns=secid,shortname,primary_boardid,engine,market"
        )
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()

        sec = payload.get("securities", {})
        rows = sec.get("data", [])
        cols = sec.get("columns", [])

        if not rows:
            return FEATURED

        df = pd.DataFrame(rows, columns=cols)
        df.columns = [c.lower() for c in df.columns]

        if "engine" in df.columns:
            df = df[df["engine"].astype(str).str.lower() == "stock"]
        if "market" in df.columns:
            df = df[df["market"].astype(str).str.lower() == "shares"]

        df = df.dropna(subset=["secid"])
        if "shortname" not in df.columns:
            df["shortname"] = df["secid"]

        result = []
        seen = set()

        for _, row in df.head(20).iterrows():
            ticker = str(row["secid"]).upper().strip()
            if ticker in seen:
                continue
            seen.add(ticker)
            result.append(
                {
                    "ticker": ticker,
                    "name": str(row["shortname"]).strip() or ticker,
                }
            )

        return result or FEATURED

    except Exception:
        return [
            item for item in FEATURED
            if query.upper() in item["ticker"] or query.lower() in item["name"].lower()
        ] or FEATURED


def get_instrument_name(ticker: str) -> str:
    ticker = (ticker or "").strip().upper()

    for item in FEATURED:
        if item["ticker"] == ticker:
            return item["name"]

    items = search_instruments(ticker)
    for item in items:
        if item["ticker"] == ticker:
            return item["name"]

    return ticker


def get_share_history(ticker: str, days_back: int = 365, max_pages: int = 20) -> pd.DataFrame:
    """
    Берём только свежую историю за последние days_back дней.
    Это гарантирует, что график будет современным, а не из 2014 года.
    """
    ticker = ticker.strip().upper()

    date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    date_till = datetime.now().strftime("%Y-%m-%d")

    all_parts = []
    start = 0

    for _ in range(max_pages):
        url = (
            f"{MOEX_HISTORY_URL}/{ticker}.json"
            f"?iss.meta=off"
            f"&from={date_from}"
            f"&till={date_till}"
            f"&history.columns=TRADEDATE,CLOSE,VOLUME,NUMTRADES"
            f"&start={start}"
        )

        response = requests.get(url, timeout=20)
        response.raise_for_status()
        payload = response.json()

        history = payload.get("history", {})
        rows = history.get("data", [])
        cols = history.get("columns", [])

        if not rows:
            break

        df = pd.DataFrame(rows, columns=cols)
        if df.empty:
            break

        all_parts.append(df)

        if len(df) < 100:
            break

        start += 100

    if not all_parts:
        return pd.DataFrame()

    df = pd.concat(all_parts, ignore_index=True)
    df.columns = [c.upper() for c in df.columns]

    df["CLOSE"] = pd.to_numeric(df["CLOSE"], errors="coerce")
    if "VOLUME" in df.columns:
        df["VOLUME"] = pd.to_numeric(df["VOLUME"], errors="coerce")
    if "NUMTRADES" in df.columns:
        df["NUMTRADES"] = pd.to_numeric(df["NUMTRADES"], errors="coerce")

    df = df.dropna(subset=["CLOSE"]).copy()
    df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"], errors="coerce")
    df = df.dropna(subset=["TRADEDATE"]).sort_values("TRADEDATE")

    return df


def get_latest_underlying_price(ticker: str):
    df = get_share_history(ticker, days_back=365)
    if df.empty:
        return None
    return float(df.iloc[-1]["CLOSE"])


def estimate_historical_volatility(ticker: str, window: int = 20):
    df = get_share_history(ticker, days_back=365)
    if df.empty or len(df) < max(10, window + 2):
        return None

    close = df["CLOSE"].astype(float)
    log_returns = (close / close.shift(1)).apply(
        lambda x: math.log(x) if pd.notna(x) and x > 0 else None
    )
    hv = log_returns.rolling(window).std().iloc[-1]

    if pd.isna(hv):
        return None

    return float(hv * math.sqrt(252))


def round_strike(price: float):
    if price < 10:
        step = 0.5
    elif price < 100:
        step = 1
    elif price < 1000:
        step = 5
    else:
        step = 10

    return round(price / step) * step


def build_option_snapshot(ticker: str, interval_code: str):
    ticker = ticker.strip().upper()
    interval = INTERVALS.get(interval_code, INTERVALS["30d"])

    price = get_latest_underlying_price(ticker)
    if price is None:
        raise ValueError("Не удалось получить цену базового актива с MOEX")

    sigma = estimate_historical_volatility(ticker, window=interval["vol_window"])
    if sigma is None:
        sigma = 0.30

    T = interval["calendar_days"] / 365.0
    K = round_strike(price)

    return {
        "ticker": ticker,
        "instrument_name": get_instrument_name(ticker),
        "interval_code": interval_code,
        "interval_label": interval["label"],
        "S": round(float(price), 4),
        "K": round(float(K), 4),
        "T": round(float(T), 6),
        "r": 0.10,
        "sigma": round(float(sigma), 6),
    }