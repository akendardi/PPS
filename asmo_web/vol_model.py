from pathlib import Path
import base64
import io

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from catboost import CatBoostRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from .market_data import get_share_history, get_instrument_name, round_strike


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "moex_options_with_underlying.csv"
MODEL_DIR = BASE_DIR / "models"
MODEL_DIR.mkdir(exist_ok=True)

FEATURES = [
    "UNDERLYING_PRICE",
    "UNDERLYING_RET_1D",
    "HV_20",
    "STRIKE",
    "TTM_DAYS",
    "MONEYNESS",
    "LOG_MONEYNESS",
    "INTRINSIC",
    "SETTLEPRICE",
    "VOLUME",
    "NUMTRADES",
    "OPENPOSITION",
    "DAY_GAP",
]

HORIZONS = {
    "1d": 1,
    "7d": 7,
    "30d": 30,
}


def _bundle_path(horizon_code: str) -> Path:
    return MODEL_DIR / f"catboost_vol_bundle_{horizon_code}.pkl"


def _prepare_live_hv_series(ticker: str, days_back: int = 365) -> pd.DataFrame:
    df = get_share_history(ticker, days_back=days_back)
    if df.empty:
        raise ValueError(f"Не удалось загрузить рыночные данные для {ticker}")

    df = df.copy()
    df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"], errors="coerce")
    df = df.dropna(subset=["TRADEDATE", "CLOSE"]).sort_values("TRADEDATE")

    close = df["CLOSE"].astype(float)
    logret = np.log(close / close.shift(1))
    df["UNDERLYING_RET_1D"] = close.pct_change()
    df["HV_20"] = logret.rolling(20, min_periods=5).std() * np.sqrt(252)

    df = df.dropna(subset=["HV_20"]).copy()
    return df


def load_dataset():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Файл датасета не найден: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)
    df.columns = [c.upper() for c in df.columns]

    feature_cols = [c.upper() for c in FEATURES]
    required = feature_cols + ["TRADEDATE"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"В датасете нет колонок: {missing}")

    extra = [c for c in ["UNDERLYINGASSET", "SECID"] if c in df.columns]
    keep_cols = list(dict.fromkeys(required + extra))
    df = df[keep_cols].copy()

    for col in feature_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"], errors="coerce")
    df = df.dropna(subset=["TRADEDATE"]).copy()

    if "UNDERLYINGASSET" in df.columns:
        group_col = "UNDERLYINGASSET"
    elif "SECID" in df.columns:
        group_col = "SECID"
    else:
        raise ValueError("Нет колонки UNDERLYINGASSET или SECID для группировки")

    df = df.sort_values([group_col, "TRADEDATE"]).copy()
    df["_GROUP_COL"] = df[group_col].astype(str).str.upper()
    return df


def build_target(df: pd.DataFrame, horizon_days: int):
    df = df.copy()
    df["TARGET_VOL"] = df.groupby("_GROUP_COL")["HV_20"].shift(-horizon_days)

    feature_cols = [c.upper() for c in FEATURES]
    df = df.dropna(subset=feature_cols + ["TARGET_VOL"]).copy()

    if df.empty:
        raise ValueError("После построения target датасет пустой")

    return df


def train_vol_bundle(horizon_code: str = "7d", force: bool = False):
    if horizon_code not in HORIZONS:
        raise ValueError(f"Неизвестный горизонт: {horizon_code}")

    bundle_path = _bundle_path(horizon_code)
    if bundle_path.exists() and not force:
        return joblib.load(bundle_path)

    df = load_dataset()
    df = build_target(df, HORIZONS[horizon_code])

    feature_cols = [c.upper() for c in FEATURES]
    X = df[feature_cols]
    y = df["TARGET_VOL"]

    split_idx = int(len(df) * 0.8)
    if split_idx < 100:
        raise ValueError("Слишком мало данных для обучения модели")

    X_train = X.iloc[:split_idx].copy()
    y_train = y.iloc[:split_idx].copy()
    X_test = X.iloc[split_idx:].copy()
    y_test = y.iloc[split_idx:].copy()

    # Более консервативная модель
    common_params = dict(
        iterations=250,
        depth=4,
        learning_rate=0.03,
        l2_leaf_reg=12,
        random_strength=2.0,
        loss_function="RMSE",
        eval_metric="RMSE",
        verbose=False,
        random_seed=42,
    )

    median_model = CatBoostRegressor(**common_params)

    lower_model = CatBoostRegressor(
        iterations=250,
        depth=4,
        learning_rate=0.03,
        l2_leaf_reg=12,
        random_strength=2.0,
        loss_function="Quantile:alpha=0.15",
        verbose=False,
        random_seed=42,
    )

    upper_model = CatBoostRegressor(
        iterations=250,
        depth=4,
        learning_rate=0.03,
        l2_leaf_reg=12,
        random_strength=2.0,
        loss_function="Quantile:alpha=0.85",
        verbose=False,
        random_seed=42,
    )

    median_model.fit(X_train, y_train)
    lower_model.fit(X_train, y_train)
    upper_model.fit(X_train, y_train)

    y_pred = median_model.predict(X_test)

    metrics = {
        "rmse": float(mean_squared_error(y_test, y_pred) ** 0.5),
        "mae": float(mean_absolute_error(y_test, y_pred)),
        "r2": float(r2_score(y_test, y_pred)),
    }

    bundle = {
        "median_model": median_model,
        "lower_model": lower_model,
        "upper_model": upper_model,
        "feature_cols": feature_cols,
        "metrics": metrics,
        "test_actual": y_test.reset_index(drop=True),
        "test_pred": pd.Series(y_pred).reset_index(drop=True),
        "horizon_code": horizon_code,
        "horizon_days": HORIZONS[horizon_code],
    }

    joblib.dump(bundle, bundle_path)
    return bundle


def _build_feature_row_from_live_data(ticker: str, horizon_code: str):
    horizon_days = HORIZONS[horizon_code]
    hist = _prepare_live_hv_series(ticker, days_back=365)
    row = hist.iloc[-1]

    s = float(row["CLOSE"])
    strike = float(round_strike(s))
    hv20 = float(row["HV_20"])
    ret1d = float(row["UNDERLYING_RET_1D"]) if pd.notna(row["UNDERLYING_RET_1D"]) else 0.0
    moneyness = s / strike if strike > 0 else 1.0
    log_moneyness = float(np.log(moneyness)) if moneyness > 0 else 0.0

    features = {
        "UNDERLYING_PRICE": s,
        "UNDERLYING_RET_1D": ret1d,
        "HV_20": hv20,
        "STRIKE": strike,
        "TTM_DAYS": float(horizon_days),
        "MONEYNESS": moneyness,
        "LOG_MONEYNESS": log_moneyness,
        "INTRINSIC": 0.0,
        "SETTLEPRICE": s * hv20 * np.sqrt(max(horizon_days / 365.0, 1 / 365)),
        "VOLUME": float(row["VOLUME"]) if "VOLUME" in hist.columns and pd.notna(row["VOLUME"]) else 0.0,
        "NUMTRADES": float(row["NUMTRADES"]) if "NUMTRADES" in hist.columns and pd.notna(row["NUMTRADES"]) else 0.0,
        "OPENPOSITION": 0.0,
        "DAY_GAP": 1.0,
    }

    return features, hv20, hist


def _stabilize_forecast(
    current_hv20: float,
    raw_pred: float,
    raw_low: float,
    raw_up: float,
    hist: pd.DataFrame,
    horizon_code: str,
):
    hv_series = hist["HV_20"].dropna().astype(float)
    recent = hv_series.tail(60)

    recent_mean = float(recent.mean())
    recent_median = float(recent.median())
    recent_std = float(recent.std()) if len(recent) > 1 else 0.0
    recent_q10 = float(recent.quantile(0.10))
    recent_q25 = float(recent.quantile(0.25))
    recent_q75 = float(recent.quantile(0.75))
    recent_q90 = float(recent.quantile(0.90))
    recent_max = float(recent.max())

    # Центральный "якорь" — это то, куда волатильность обычно возвращается
    anchor = 0.50 * current_hv20 + 0.30 * recent_mean + 0.20 * recent_median

    # Очень сильное сглаживание прогноза
    blend_map = {
        "1d": 0.80,
        "7d": 0.88,
        "30d": 0.93,
    }
    alpha = blend_map.get(horizon_code, 0.88)

    pred = (1.0 - alpha) * raw_pred + alpha * anchor

    # Жёсткий потолок: не даём прогнозу улетать сильно выше недавней истории
    if horizon_code == "1d":
        upper_cap = max(
            current_hv20 * 1.08,
            recent_q75 * 1.05,
            recent_mean + 0.6 * max(recent_std, 0.008),
        )
    elif horizon_code == "7d":
        upper_cap = max(
            current_hv20 * 1.15,
            recent_q75 * 1.08,
            recent_q90 * 1.03,
            recent_mean + 0.8 * max(recent_std, 0.01),
            recent_max * 1.02,
        )
    else:  # 30d
        upper_cap = max(
            current_hv20 * 1.22,
            recent_q75 * 1.12,
            recent_q90 * 1.06,
            recent_mean + 1.0 * max(recent_std, 0.012),
            recent_max * 1.04,
        )

    lower_cap = max(
        0.01,
        min(
            recent_q10 * 0.90,
            recent_q25 * 0.92,
            current_hv20 * 0.88,
            recent_mean * 0.88,
        ),
    )

    pred = float(np.clip(pred, lower_cap, upper_cap))

    # Интервал вокруг уже сглаженного прогноза
    base_span = max(0.006, 0.8 * max(recent_std, 0.008))

    if horizon_code == "1d":
        down_span = min(base_span * 0.8, pred - lower_cap if pred > lower_cap else base_span * 0.5)
        up_span = min(base_span * 0.9, upper_cap - pred if upper_cap > pred else base_span * 0.5)
    elif horizon_code == "7d":
        down_span = min(base_span * 1.0, pred - lower_cap if pred > lower_cap else base_span * 0.7)
        up_span = min(base_span * 1.1, upper_cap - pred if upper_cap > pred else base_span * 0.7)
    else:
        down_span = min(base_span * 1.15, pred - lower_cap if pred > lower_cap else base_span * 0.8)
        up_span = min(base_span * 1.25, upper_cap - pred if upper_cap > pred else base_span * 0.8)

    low = pred - max(down_span, 0.004)
    up = pred + max(up_span, 0.004)

    low = max(lower_cap, low)
    up = min(upper_cap, up)

    low = min(low, pred)
    up = max(up, pred)

    return float(pred), float(low), float(up)


def _make_forecast_path(result: dict) -> pd.DataFrame:
    hist = result["history_df"].copy()
    last_date = pd.to_datetime(hist["TRADEDATE"].iloc[-1])

    horizon_days = int(result["horizon_days"])
    forecast_dates = pd.date_range(
        last_date + pd.Timedelta(days=1),
        periods=horizon_days,
        freq="D",
    )

    start_val = float(result["current_hv20"])
    mid_val = float(result["prediction"])
    low_val = float(result["lower"])
    up_val = float(result["upper"])

    low_val = min(low_val, mid_val)
    up_val = max(up_val, mid_val)

    if horizon_days == 1:
        t = np.array([1.0])
    else:
        t = np.linspace(0.0, 1.0, horizon_days)

    # Очень спокойная траектория:
    # сначала почти плоско, потом мягкий подход к целевому уровню
    s = t ** 1.8
    smooth_mid = start_val + (mid_val - start_val) * s

    final_down = max(mid_val - low_val, 1e-6)
    final_up = max(up_val - mid_val, 1e-6)

    # Интервал раскрывается умеренно
    growth = 0.35 + 0.65 * (t ** 1.4)
    smooth_low = smooth_mid - final_down * growth
    smooth_up = smooth_mid + final_up * growth

    smooth_low = np.minimum(smooth_low, smooth_mid)
    smooth_up = np.maximum(smooth_up, smooth_mid)

    forecast_df = pd.DataFrame({
        "DATE": forecast_dates,
        "IV_FACT": np.nan,
        "IV_FORECAST": smooth_mid,
        "LOWER": smooth_low,
        "UPPER": smooth_up,
    })

    return forecast_df


def build_forecast_table(result: dict, history_tail: int = 5, forecast_tail: int = 10) -> pd.DataFrame:
    hist = result["history_df"].copy()
    hist = hist.tail(history_tail).copy()

    hist_df = pd.DataFrame({
        "DATE": pd.to_datetime(hist["TRADEDATE"]),
        "IV_FACT": hist["HV_20"].astype(float),
        "IV_FORECAST": np.nan,
        "LOWER": np.nan,
        "UPPER": np.nan,
    })

    forecast_df = _make_forecast_path(result).head(forecast_tail).copy()
    table_df = pd.concat([hist_df, forecast_df], ignore_index=True)

    return table_df


def predict_vol_for_ticker(ticker: str, horizon_code: str = "7d"):
    bundle = train_vol_bundle(horizon_code=horizon_code, force=False)

    features, current_hv20, hist = _build_feature_row_from_live_data(ticker, horizon_code)
    feature_cols = bundle["feature_cols"]
    X_one = pd.DataFrame([[features[col] for col in feature_cols]], columns=feature_cols)

    raw_lower = float(bundle["lower_model"].predict(X_one)[0])
    raw_median = float(bundle["median_model"].predict(X_one)[0])
    raw_upper = float(bundle["upper_model"].predict(X_one)[0])

    prediction, lower, upper = _stabilize_forecast(
        current_hv20=current_hv20,
        raw_pred=raw_median,
        raw_low=raw_lower,
        raw_up=raw_upper,
        hist=hist,
        horizon_code=horizon_code,
    )

    result = {
        "ticker": ticker.upper(),
        "instrument_name": get_instrument_name(ticker),
        "current_hv20": float(current_hv20),
        "prediction": float(prediction),
        "lower": float(lower),
        "upper": float(upper),
        "metrics": bundle["metrics"],
        "horizon_code": horizon_code,
        "horizon_days": HORIZONS[horizon_code],
        "history_df": hist,
    }

    result["forecast_table"] = build_forecast_table(result)
    return result


def make_vol_forecast_chart(result: dict):
    hist = result["history_df"].copy().tail(60)
    forecast_df = _make_forecast_path(result)

    fig = plt.figure(figsize=(6.6, 3.2))
    ax = fig.add_subplot(111)

    ax.plot(
        hist["TRADEDATE"],
        hist["HV_20"],
        linewidth=1.4,
        label="Историческая IV",
    )

    ax.plot(
        forecast_df["DATE"],
        forecast_df["IV_FORECAST"],
        linestyle="--",
        linewidth=1.3,
        label="Прогноз IV",
    )

    ax.plot(
        forecast_df["DATE"],
        forecast_df["LOWER"],
        linestyle=":",
        linewidth=1.0,
        label="Нижняя граница",
    )

    ax.plot(
        forecast_df["DATE"],
        forecast_df["UPPER"],
        linestyle=":",
        linewidth=1.0,
        label="Верхняя граница",
    )

    ax.fill_between(
        forecast_df["DATE"],
        forecast_df["LOWER"],
        forecast_df["UPPER"],
        alpha=0.10,
    )

    ax.scatter(
        forecast_df["DATE"].iloc[-1],
        forecast_df["IV_FORECAST"].iloc[-1],
        s=32,
        zorder=6,
    )

    ax.set_title("Прогноз волатильности с доверительным интервалом", fontsize=9)
    ax.set_xlabel("Дата", fontsize=8)
    ax.set_ylabel("Имплайд-волатильность / proxy", fontsize=8)
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=7, loc="upper left")

    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m.%Y"))
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=140)
    buf.seek(0)
    plt.close(fig)

    return base64.b64encode(buf.read()).decode("utf-8")