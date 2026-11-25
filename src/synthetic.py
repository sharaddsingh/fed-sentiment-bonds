"""
Fake statements and market data for the offline demo and the tests.
NOTHING here is real. A hidden "true tone" drives the statement wording,
the Fed funds rate and the 2Y yield, so the pipeline can be checked end to end.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

HAWK = [
    "Inflation remains elevated and the Committee is highly attentive to inflation risks.",
    "The labor market remains tight and job gains have been strong.",
    "The Committee anticipates that additional policy firming may be appropriate.",
    "Economic activity has been expanding at a solid pace.",
]
DOVE = [
    "Economic activity has weakened and labor market slack remains.",
    "Inflation has eased and remains subdued.",
    "The Committee will maintain an accommodative stance to support the economy.",
    "Downside risks to the outlook have increased.",
]
NEUTRAL = [
    "The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent over the longer run.",
    "The Committee will continue to monitor the implications of incoming information for the economic outlook.",
]


def make_demo_data(seed: int = 7):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2006-01-02", "2026-10-30")
    # ~8 statements a year on Wednesdays, plus one Sunday emergency statement
    wed = days[days.weekday == 2]
    stmt_dates = list(wed[::7])
    stmt_dates.append(pd.Timestamp("2020-03-15"))      # Sunday
    stmt_dates = sorted(set(stmt_dates))

    tau, taus = 0.0, []
    for _ in stmt_dates:
        tau = float(np.clip(0.8 * tau + rng.normal(0, 1.6), -5, 5))
        taus.append(tau)

    rows, truth = [], {}
    for d, t in zip(stmt_dates, taus):
        n_h = int(np.clip(round(2 + t / 2 + rng.normal(0, 0.6)), 0, 4))
        n_d = int(np.clip(round(2 - t / 2 + rng.normal(0, 0.6)), 0, 4))
        sents = (list(rng.choice(HAWK, n_h, replace=False)) +
                 list(rng.choice(DOVE, n_d, replace=False)) + NEUTRAL)
        rng.shuffle(sents)
        text = " ".join(sents)
        rows.append({"date": d, "url": "synthetic", "text": text})
        truth[text] = t
    statements = pd.DataFrame(rows)

    # Fed funds target moves with tone
    rate, target = 4.25, pd.Series(np.nan, index=pd.date_range(days[0], days[-1]))
    rate_moves = {}
    for d, t in zip(stmt_dates, taus):
        move = 0.25 if t > 2 else (-0.25 if t < -2 else 0.0)
        rate = max(0.25, rate + move)
        rate_moves[d] = move
        target.loc[d:] = rate
    target = target.fillna(4.25)

    # Yields: random walk + reaction on statement days
    d2y = rng.normal(0, 0.05, len(days))
    prev_tau = 0.0
    for d, t in zip(stmt_dates, taus):
        i = days.searchsorted(d)
        if i < len(days):
            d2y[i] += 0.035 * (t - prev_tau) + 0.3 * rate_moves[d] + rng.normal(0, 0.04)
        prev_tau = t
    y2 = 4.5 + np.cumsum(d2y)
    y10 = 4.8 + np.cumsum(0.5 * d2y + rng.normal(0, 0.04, len(days)))
    fred = pd.DataFrame({"DGS2": y2, "DGS10": y10}, index=days)
    fred["DFEDTAR"] = target.reindex(days).where(days <= "2008-12-15")
    fred["DFEDTARU"] = target.reindex(days).where(days > "2008-12-15")

    r_zn = -0.06 * np.diff(y10, prepend=y10[0]) + rng.normal(0, 0.001, len(days))
    r_dxy = 0.02 * d2y + rng.normal(0, 0.004, len(days))
    r_es = -0.03 * d2y + rng.normal(0, 0.011, len(days))
    yahoo = pd.DataFrame({
        "ZN=F": 120 * np.exp(np.cumsum(r_zn)),
        "DX-Y.NYB": 90 * np.exp(np.cumsum(r_dxy)),
        "ES=F": 1300 * np.exp(np.cumsum(r_es)),
    }, index=days)

    def mock_llm(provider, model, key, prompt):
        """Pretend LLM: reads the hidden tone (with some noise)."""
        text = next((tx for tx in truth if tx in prompt), None)
        t = truth.get(text, 0.0)
        score = int(np.clip(round(t + rng.normal(0, 0.7)), -5, 5))
        return json.dumps({"score": score, "reason": "Synthetic demo statement."})

    return statements, fred, yahoo, mock_llm
