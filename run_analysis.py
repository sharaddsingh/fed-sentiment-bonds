"""
Fed statement tone vs. market reaction: full pipeline.

    python run_analysis.py            # real data (+ LLM if an API key is set)
    python run_analysis.py --no-llm   # real data, dictionary method only
    python run_analysis.py --refresh  # re-download statements and market data
    python run_analysis.py --demo     # synthetic data, offline (testing only)

Outputs: results/REPORT.md, results/*.png, results/events.csv
"""
from __future__ import annotations

import argparse
import os

import pandas as pd

import config as C
from src import analysis as A
from src import plots as P
from src.dictionary import dictionary_score
from src.events import build_events, normal_day_moves
from src.fed_statements import download_statements
from src.llm_scorer import pick_provider, score_statements
from src.market_data import download_market_data, fed_funds_target


def update_readme(block: str, path: str = "README.md"):
    if not os.path.exists(path):
        return
    text = open(path, encoding="utf-8").read()
    a, b = text.find("<!-- RESULTS:START"), text.find("<!-- RESULTS:END -->")
    if a == -1 or b == -1:
        return
    b += len("<!-- RESULTS:END -->")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text[:a] + block + text[b:])
    print("Updated the results section in README.md")


def fmt(x, kind="f2"):
    if pd.isna(x):
        return "n/a"
    return {"f2": f"{x:+.2f}", "pct": f"{x:.0%}", "bps": f"{x:+.1f} bps",
            "r2": f"{x:.2f}", "p": f"{x:.3f}"}[kind]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    os.makedirs(C.RESULTS_DIR, exist_ok=True)

    # 1. Data ---------------------------------------------------------------
    mock_llm = None
    if args.demo:
        print("DEMO MODE: synthetic data. These results are NOT real.")
        from src.synthetic import make_demo_data
        statements, fred, yahoo, mock_llm = make_demo_data()
    else:
        statements = download_statements(C.START_YEAR, C.FED_RECENT_PAGE, C.FED_YEAR_PAGE,
                                         C.DATA_DIR, args.refresh, C.REQUEST_PAUSE_SEC)
        start = f"{C.START_YEAR - 1}-12-01"
        fred, yahoo = download_market_data(C.FRED_SERIES, C.YF_TICKERS, start, C.FRED_CSV,
                                           C.DATA_DIR, args.refresh)
    statements["date"] = pd.to_datetime(statements["date"])
    target = fed_funds_target(fred)
    print(f"{len(statements)} statements: {statements['date'].min().date()} "
          f"to {statements['date'].max().date()}")

    # 2. Dictionary scores -----------------------------------------------------
    scores = statements[["date"]].copy()
    scores = pd.concat([scores, pd.DataFrame([dictionary_score(t) for t in statements["text"]])],
                       axis=1)

    # 3. LLM scores --------------------------------------------------------------
    llm_label = None
    if args.demo:
        llm_label = "LLM (demo mock)"
        llm = score_statements(statements, "mock", "demo", "x", cache_dir=C.RESULTS_DIR + "/_demo",
                               pause=0, call_fn=mock_llm)
    elif not args.no_llm and (p := pick_provider(C.LLM_PROVIDERS)):
        name, model, key = p
        llm_label = f"LLM ({model})"
        llm = score_statements(statements, name, model, key, C.DATA_DIR,
                               C.LLM_PAUSE_SEC, C.LLM_MAX_RETRIES)
    else:
        llm = None
        print("No LLM API key found (or --no-llm): using the dictionary method only.")
    if llm is not None and len(llm):
        llm["date"] = pd.to_datetime(llm["date"])
        scores = scores.merge(llm, on="date", how="left")
    use_llm = "llm_score" in scores and scores["llm_score"].notna().sum() > 10

    # 4. Events ------------------------------------------------------------------
    ev = build_events(scores, fred, yahoo, target)
    ev.to_csv(os.path.join(C.RESULTS_DIR, "events.csv"), index=False)
    normal = normal_day_moves(fred, ev["event_day"])

    # 5. Statistics ----------------------------------------------------------------
    signals = {}
    if use_llm:
        signals["d_llm"] = "LLM tone change"
    signals["d_dict"] = "Dictionary tone change"
    corr = A.correlation_table(ev, signals, C.REACTIONS)
    reg = pd.DataFrame({signals[c]: A.regression(ev, c) for c in signals}).T
    hits = {signals[c]: A.hit_rate(ev, c) for c in signals}
    sub = A.subperiod_correlations(ev, signals, C.SUBPERIODS)
    level_corr = {lbl: ev[[c, "d2y_bps"]].dropna().corr().iloc[0, 1]
                  for c, lbl in ([("llm_score", "LLM tone level")] if use_llm else []) +
                  [("dict_score", "Dictionary tone level")]}
    agree = ev[["llm_score", "dict_score"]].corr().iloc[0, 1] if use_llm else float("nan")
    fomc_abs, normal_abs = ev["d2y_bps"].abs().mean(), normal.abs().mean()
    top = A.biggest_moves(ev)

    # 6. Charts --------------------------------------------------------------------
    main_col, main_label = (("llm_score", llm_label) if use_llm
                            else ("dict_score", "dictionary score"))
    P.plot_tone_timeline(ev, target, main_col, main_label, C.RESULTS_DIR)
    panels = ([("d_llm", "LLM", P.LLM)] if use_llm else []) + [("d_dict", "Dictionary", P.DICT)]
    P.plot_scatter(ev, panels, C.RESULTS_DIR)
    P.plot_correlations(corr, C.RESULTS_DIR)
    P.plot_fomc_vs_normal(ev["d2y_bps"].dropna(), normal, C.RESULTS_DIR)

    # 7. Report ------------------------------------------------------------------
    period = f"{ev['date'].min().date()} to {ev['date'].max().date()}"
    glance = pd.DataFrame({
        m: {
            "Correlation: tone change vs 2Y yield move": fmt(corr.loc[m, C.REACTIONS["d2y_bps"]]),
            "Direction hit rate (2Y yield)": f"{fmt(hits[m][0], 'pct')} of {hits[m][1]}",
            "2Y move per 1-sd tone change": fmt(reg.loc[m, "Tone effect (bps per 1 sd)"], "bps"),
            "t-stat (robust)": fmt(reg.loc[m, "t-stat"]),
            "R²: rate decision only → + tone": (f"{reg.loc[m, 'R² (rate only)']:.2f} → "
                                                f"{reg.loc[m, 'R² (tone + rate)']:.2f}"),
        } for m in signals.values()
    })
    tops = top.copy()
    tops["date"] = tops["date"].dt.date
    for c in tops.columns:
        if tops[c].dtype.kind == "f":
            tops[c] = tops[c].round(2)

    lines = ["> **DEMO RUN ON SYNTHETIC DATA. These numbers are not real.**", ""] if args.demo else []
    lines += [
        "# Fed tone vs. market reaction: report", "",
        f"**{len(ev)} FOMC statements, {period}.** Tone scored by "
        f"{(llm_label + ' and ') if use_llm else ''}a hawkish/dovish word dictionary.", "",
        "## Headline", "", glance.to_markdown(), "",
        f"- Fed statement days: average |2Y move| **{fomc_abs:.1f} bps** vs "
        f"**{normal_abs:.1f} bps** on other days.",
        (f"- Agreement between LLM and dictionary tone levels: correlation **{agree:.2f}**."
         if use_llm else "- LLM not used in this run."), "",
        "## Correlation of tone change with each market", "",
        corr.round(2).to_markdown(), "",
        "Expected signs for a hawkish surprise: yields up (+), T-Note futures down (-), "
        "dollar up (+), stocks down (-).", "",
        "## Tone level vs. tone change", "",
        "Correlation with the 2Y yield move:", "",
        pd.Series({**level_corr, **{v: corr.loc[v, C.REACTIONS['d2y_bps']]
                                    for v in signals.values()}}, name="corr")
        .round(2).to_markdown(), "",
        "## Regression: 2Y move = a + b·tone change (standardised) + c·rate change", "",
        reg.round(3).to_markdown(), "",
        "## Sub-periods (correlation of tone change with 2Y move)", "",
        sub.round(2).to_markdown(), "",
        "## 10 biggest 2Y yield moves on statement days", "",
        tops.to_markdown(index=False), "",
        "## Charts", "",
        "![Tone timeline](tone_timeline.png)",
        "![Tone vs 2Y yield](tone_vs_2y_yield.png)",
        "![Correlation by market](correlation_by_market.png)",
        "![FOMC vs normal days](fomc_vs_normal_days.png)", "",
    ]
    with open(os.path.join(C.RESULTS_DIR, "REPORT.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if not args.demo:
        update_readme("\n".join([
            "<!-- RESULTS:START (auto-generated by run_analysis.py, do not edit by hand) -->",
            f"*{len(ev)} FOMC statements, {period}. Market reaction = close-to-close move "
            "on the release day.*", "",
            glance.to_markdown(), "",
            f"Fed statement days move the 2Y yield **{fomc_abs:.1f} bps** on average, "
            f"vs **{normal_abs:.1f} bps** on other days.",
            "<!-- RESULTS:END -->",
        ]))

    print("\n" + glance.to_string())
    print(f"\nAvg |2Y move|: Fed days {fomc_abs:.1f} bps vs normal days {normal_abs:.1f} bps")
    print(f"\nDone. Open {C.RESULTS_DIR}/REPORT.md for the full report and charts.")


if __name__ == "__main__":
    main()
