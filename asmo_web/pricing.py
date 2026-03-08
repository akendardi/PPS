import math
from dataclasses import dataclass
from scipy.stats import norm


@dataclass
class OptionInputs:
    S: float      # цена базового актива
    K: float      # страйк
    T: float      # время до экспирации (в годах)
    r: float      # безрисковая ставка (например 0.12 = 12%)
    sigma: float  # волатильность (например 0.35 = 35%)


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float):
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_call_put(inp: OptionInputs):
    d1, d2 = _d1_d2(inp.S, inp.K, inp.T, inp.r, inp.sigma)
    call = inp.S * norm.cdf(d1) - inp.K * math.exp(-inp.r * inp.T) * norm.cdf(d2)
    put = inp.K * math.exp(-inp.r * inp.T) * norm.cdf(-d2) - inp.S * norm.cdf(-d1)
    return call, put


def greeks(inp: OptionInputs):
    d1, d2 = _d1_d2(inp.S, inp.K, inp.T, inp.r, inp.sigma)
    pdf_d1 = norm.pdf(d1)

    delta_call = norm.cdf(d1)
    delta_put = delta_call - 1

    gamma = pdf_d1 / (inp.S * inp.sigma * math.sqrt(inp.T))
    vega = inp.S * pdf_d1 * math.sqrt(inp.T)  # на 1.0 (не на 1%)

    theta_call = (
        -(inp.S * pdf_d1 * inp.sigma) / (2 * math.sqrt(inp.T))
        - inp.r * inp.K * math.exp(-inp.r * inp.T) * norm.cdf(d2)
    )
    theta_put = (
        -(inp.S * pdf_d1 * inp.sigma) / (2 * math.sqrt(inp.T))
        + inp.r * inp.K * math.exp(-inp.r * inp.T) * norm.cdf(-d2)
    )

    rho_call = inp.K * inp.T * math.exp(-inp.r * inp.T) * norm.cdf(d2)
    rho_put = -inp.K * inp.T * math.exp(-inp.r * inp.T) * norm.cdf(-d2)

    return {
        "delta_call": delta_call,
        "delta_put": delta_put,
        "gamma": gamma,
        "vega": vega,
        "theta_call": theta_call,
        "theta_put": theta_put,
        "rho_call": rho_call,
        "rho_put": rho_put,
    }