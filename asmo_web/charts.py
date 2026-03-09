import base64
import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .pricing import OptionInputs, bs_call_put, greeks
from .market_data import get_share_history


def _build_png_buffer(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=140)
    buf.seek(0)
    plt.close(fig)
    return buf


def fig_to_base64(fig):
    buf = _build_png_buffer(fig)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def make_delta_chart(snapshot, return_buffer=False):
    s0 = snapshot["S"]
    k = snapshot["K"]
    t = snapshot["T"]
    r = snapshot["r"]
    sigma = snapshot["sigma"]

    s_values = np.linspace(max(1, s0 * 0.6), s0 * 1.4, 100)
    delta_values = []

    for s in s_values:
        inp = OptionInputs(S=float(s), K=k, T=t, r=r, sigma=sigma)
        g = greeks(inp)
        delta_values.append(float(g["delta_call"]))

    fig = plt.figure(figsize=(4.2, 3.0))
    ax = fig.add_subplot(111)
    ax.plot(s_values, delta_values)
    ax.set_title("Delta-график", fontsize=9)
    ax.set_xlabel("Цена базового актива (S)", fontsize=8)
    ax.set_ylabel("Delta", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if return_buffer:
        return _build_png_buffer(fig)
    return fig_to_base64(fig)


def make_vega_chart(snapshot, return_buffer=False):
    s = snapshot["S"]
    k = snapshot["K"]
    t = snapshot["T"]
    r = snapshot["r"]
    sigma0 = snapshot["sigma"]

    sigma_values = np.linspace(max(0.05, sigma0 * 0.5), sigma0 * 1.8, 100)
    vega_values = []

    for sigma in sigma_values:
        inp = OptionInputs(S=s, K=k, T=t, r=r, sigma=float(sigma))
        g = greeks(inp)
        vega_values.append(float(g["vega"]))

    fig = plt.figure(figsize=(4.2, 3.0))
    ax = fig.add_subplot(111)
    ax.plot(sigma_values, vega_values)
    ax.set_title("Vega-график", fontsize=9)
    ax.set_xlabel("Волатильность (sigma)", fontsize=8)
    ax.set_ylabel("Vega", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if return_buffer:
        return _build_png_buffer(fig)
    return fig_to_base64(fig)


def make_time_decay_chart(snapshot, return_buffer=False):
    s = snapshot["S"]
    k = snapshot["K"]
    r = snapshot["r"]
    sigma = snapshot["sigma"]

    t_values = np.linspace(1 / 365, 1.0, 120)
    price_values = []

    for t in t_values:
        inp = OptionInputs(S=s, K=k, T=float(t), r=r, sigma=sigma)
        call_price, _ = bs_call_put(inp)
        price_values.append(float(call_price))

    days = t_values * 365

    fig = plt.figure(figsize=(4.2, 3.0))
    ax = fig.add_subplot(111)
    ax.plot(days, price_values)
    ax.set_title("Временной профиль", fontsize=9)
    ax.set_xlabel("Время до экспирации (дни)", fontsize=8)
    ax.set_ylabel("Цена опциона", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if return_buffer:
        return _build_png_buffer(fig)
    return fig_to_base64(fig)


def make_price_history_chart(snapshot, return_buffer=False):
    ticker = snapshot["ticker"]
    df = get_share_history(ticker)

    fig = plt.figure(figsize=(4.2, 3.0))
    ax = fig.add_subplot(111)

    if not df.empty:
        df["TRADEDATE"] = pd.to_datetime(df["TRADEDATE"])
        ax.plot(df["TRADEDATE"], df["CLOSE"])
        ax.set_title(f"История цены {ticker}", fontsize=9)
        ax.set_xlabel("Дата", fontsize=8)
        ax.set_ylabel("Цена", fontsize=8)
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate()
        ax.grid(True, alpha=0.3)
    else:
        ax.text(0.5, 0.5, "Нет данных", ha="center", va="center")
        ax.set_title(f"История цены {ticker}", fontsize=9)

    fig.tight_layout()

    if return_buffer:
        return _build_png_buffer(fig)
    return fig_to_base64(fig)


def build_all_charts(snapshot):
    return {
        "delta_chart": make_delta_chart(snapshot),
        "vega_chart": make_vega_chart(snapshot),
        "time_chart": make_time_decay_chart(snapshot),
        "price_chart": make_price_history_chart(snapshot),
    }


def build_chart_buffers(snapshot):
    return {
        "delta_chart": make_delta_chart(snapshot, return_buffer=True),
        "vega_chart": make_vega_chart(snapshot, return_buffer=True),
        "time_chart": make_time_decay_chart(snapshot, return_buffer=True),
        "price_chart": make_price_history_chart(snapshot, return_buffer=True),
    }