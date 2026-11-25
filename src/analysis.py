"""
Statistics: does the tone change explain the market move?

  - Correlation of tone change with each market's reaction
  - Regression:  2Y yield move = a + b * (tone change, standardised) + c * (rate change)
      b = basis points the 2Y yield moves for a 1-standard-deviation tone change.
      The rate-change control asks: does the WORDING matter beyond the decision itself?
      Robust (HC1) standard errors, because big crisis days make errors uneven.
  - Hit rate: how often the yield moved in the direction the tone change predicted
  - FOMC days vs normal days: are Fed days actually special?
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def correlation_table(ev: pd.DataFrame, signals: dict, reactions: dict) -> pd.DataFrame:
    rows = {}
    for sig_col, sig_name in signals.items():
        rows[sig_name] = {
            name: ev[[sig_col, col]].dropna().corr().iloc[0, 1] for col, name in reactions.items()
        }
    return pd.DataFrame(rows).T


def ols_hc1(y: np.ndarray, X: np.ndarray) -> dict:
    """Ordinary least squares with HC1 robust standard errors, in plain NumPy.

    beta = (X'X)^-1 X'y
    robust covariance = n/(n-k) * (X'X)^-1 [sum e_i^2 x_i x_i'] (X'X)^-1
    p-values use the normal distribution (standard for robust errors).
    """
    from math import erfc, sqrt
    n, k = X.shape
    xtx_inv = np.linalg.inv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    meat = (X * resid[:, None] ** 2).T @ X
    cov = xtx_inv @ meat @ xtx_inv * n / (n - k)
    se = np.sqrt(np.diag(cov))
    t = beta / se
    p = np.array([erfc(abs(v) / sqrt(2)) for v in t])
    r2 = 1 - (resid @ resid) / ((y - y.mean()) @ (y - y.mean()))
    return {"beta": beta, "se": se, "t": t, "p": p, "r2": float(r2), "n": n}


def regression(ev: pd.DataFrame, tone_col: str, y_col: str = "d2y_bps") -> dict:
    df = ev[[tone_col, "rate_change_bps", y_col]].dropna()
    z = (df[tone_col] - df[tone_col].mean()) / df[tone_col].std()
    y = df[y_col].to_numpy(float)
    ones = np.ones(len(df))
    full = ols_hc1(y, np.column_stack([ones, z.to_numpy(float),
                                       df["rate_change_bps"].to_numpy(float)]))
    only_rate = ols_hc1(y, np.column_stack([ones, df["rate_change_bps"].to_numpy(float)]))
    return {
        "Tone effect (bps per 1 sd)": full["beta"][1],
        "t-stat": full["t"][1],
        "p-value": full["p"][1],
        "Rate-change effect (bps per 1 bp)": full["beta"][2],
        "R² (tone + rate)": full["r2"],
        "R² (rate only)": only_rate["r2"],
        "N": full["n"],
    }


def hit_rate(ev: pd.DataFrame, tone_col: str, y_col: str = "d2y_bps") -> tuple[float, int]:
    df = ev[[tone_col, y_col]].dropna()
    df = df[(df[tone_col] != 0) & (df[y_col] != 0)]
    if df.empty:
        return float("nan"), 0
    return float((np.sign(df[tone_col]) == np.sign(df[y_col])).mean()), len(df)


def subperiod_correlations(ev, tone_cols: dict, periods: dict, y_col="d2y_bps"):
    rows = {}
    for name, (a, b) in periods.items():
        part = ev[(ev["date"] >= a) & (ev["date"] <= b)]
        rows[name] = {label: part[[c, y_col]].dropna().corr().iloc[0, 1]
                      if len(part) > 5 else np.nan for c, label in tone_cols.items()}
        rows[name]["Statements"] = len(part)
    return pd.DataFrame(rows).T


def biggest_moves(ev: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    cols = ["date", "d2y_bps", "rate_change_bps", "dict_score", "d_dict"]
    if "llm_score" in ev:
        cols += ["llm_score", "d_llm", "llm_reason"]
    df = ev.dropna(subset=["d2y_bps"])
    return df.reindex(df["d2y_bps"].abs().sort_values(ascending=False).index)[cols].head(n)
