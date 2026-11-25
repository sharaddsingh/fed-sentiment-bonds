"""
Event study: line up each statement with the market's move on that day.

Timing:
  Statements come out at 2:00 p.m. New York time (2:15 before 2013), while
  markets are open. So the reaction is the CLOSE-TO-CLOSE change from the day
  before to the release day. Emergency statements released on a weekend
  (e.g. Sunday 15 March 2020) are matched to the next trading day.

Tone change, not tone level:
  Markets move on SURPRISES. If the Fed was already hawkish last time and is
  equally hawkish today, nothing new happened. So the main signal is the change
  in tone versus the previous statement.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _move(series: pd.Series, release: pd.Timestamp, kind: str):
    """Change on the first trading day on/after `release` vs the day before.
    kind='bps': level change in basis points (for yields in %),
    kind='pct': percentage return."""
    s = series.dropna()
    pos = s.index.searchsorted(release)
    if pos == 0 or pos >= len(s):
        return np.nan, pd.NaT, pd.NaT
    t, prev = s.index[pos], s.index[pos - 1]
    if (t - release).days > 5:            # no data near the event
        return np.nan, pd.NaT, pd.NaT
    if kind == "bps":
        return (s.iloc[pos] - s.iloc[pos - 1]) * 100, t, prev
    return (s.iloc[pos] / s.iloc[pos - 1] - 1) * 100, t, prev


def build_events(scores: pd.DataFrame, fred: pd.DataFrame, yahoo: pd.DataFrame,
                 target: pd.Series) -> pd.DataFrame:
    """One row per statement: tone scores, tone changes, rate decision, reactions."""
    ev = scores.sort_values("date").reset_index(drop=True).copy()
    rows = []
    for d in ev["date"]:
        d = pd.Timestamp(d)
        d2y, t, prev = _move(fred["DGS2"], d, "bps")
        d10y, _, _ = _move(fred["DGS10"], d, "bps")
        # A new target usually takes effect the DAY AFTER the announcement, so
        # compare the day before the release with a few days after it.
        rate = (target.asof(d + pd.Timedelta(days=3)) - target.asof(d - pd.Timedelta(days=1))) * 100
        rows.append({
            "event_day": t,
            "d2y_bps": d2y,
            "d10y_bps": d10y,
            "rate_change_bps": rate,
            "zn_ret": _move(yahoo["ZN=F"], d, "pct")[0] if "ZN=F" in yahoo else np.nan,
            "dxy_ret": _move(yahoo["DX-Y.NYB"], d, "pct")[0] if "DX-Y.NYB" in yahoo else np.nan,
            "es_ret": _move(yahoo["ES=F"], d, "pct")[0] if "ES=F" in yahoo else np.nan,
        })
    ev = pd.concat([ev, pd.DataFrame(rows)], axis=1)
    ev["d_dict"] = ev["dict_score"].diff()
    if "llm_score" in ev:
        ev["d_llm"] = ev["llm_score"].diff()
    return ev


def normal_day_moves(fred: pd.DataFrame, event_days) -> pd.Series:
    """Daily 2Y yield changes (bps) on days WITHOUT a Fed statement."""
    s = fred["DGS2"].dropna()
    ch = s.diff().mul(100).dropna()
    return ch[~ch.index.isin(pd.DatetimeIndex(event_days).dropna())]
