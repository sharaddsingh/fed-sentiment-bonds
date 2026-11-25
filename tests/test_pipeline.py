"""Run with:  python -m pytest -q   (no internet or API key needed)"""
import json

import numpy as np
import pandas as pd
import pytest

from src.dictionary import dictionary_score
from src.events import _move, build_events
from src.fed_statements import extract_statement_text, statement_links
from src.llm_scorer import PROMPT, parse_llm_json, pick_provider, score_statements

# A trimmed copy of the structure of a real federalreserve.gov statement page
STATEMENT_PAGE = """
<html><body>
<p>An official website of the United States Government</p>
<p>January 31, 2024</p>
<h3>Federal Reserve issues FOMC statement</h3>
<p class="releaseTime">For release at 2:00 p.m. EST</p>
<p>Recent indicators suggest that economic activity has been expanding at a solid pace.</p>
<p>The Committee seeks to achieve maximum employment and inflation at the rate of 2 percent.</p>
<p>Voting for the monetary policy action were Jerome H. Powell, Chair; John C. Williams.</p>
<p>For media inquiries, please email media@frb.gov or call 202-452-2955.</p>
<p>Last Update: January 31, 2024</p>
</body></html>
"""

CALENDAR_PAGE = """
<html><body>
<a href="/newsevents/pressreleases/monetary20240131a.htm">Statement</a>
<a href="/monetarypolicy/files/monetary20240131a1.pdf">PDF</a>
<a href="/newsevents/pressreleases/monetary20250822a.htm">Statement on Longer-Run Goals</a>
<a href="/newsevents/press/monetary/20081216b.htm">Statement</a>
</body></html>
"""


def test_statement_text_keeps_only_policy_language():
    text = extract_statement_text(STATEMENT_PAGE)
    assert text.startswith("Recent indicators suggest")
    assert "Voting for" not in text          # vote list removed
    assert "January 31, 2024" not in text    # date removed (no hindsight hint)
    assert "media inquiries" not in text


def test_statement_links_parsed_with_dates():
    links = statement_links(CALENDAR_PAGE, "https://www.federalreserve.gov/monetarypolicy/x.htm")
    dates = [str(d) for d, _ in links]
    assert dates == ["2024-01-31", "2008-12-16"]     # PDF and 'Longer-Run Goals' ignored
    assert links[0][1].startswith("https://www.federalreserve.gov/newsevents/")


@pytest.mark.parametrize("raw", [
    '{"score": 3, "reason": "Signals further hikes."}',
    '```json\n{"score": -2, "reason": "Cuts rates."}\n```',
    'Sure! {"score": "4", "reason": "Hawkish."}',
])
def test_llm_json_parsing(raw):
    out = parse_llm_json(raw)
    assert -5 <= out["llm_score"] <= 5 and out["llm_reason"]


def test_llm_json_rejects_out_of_range():
    with pytest.raises(ValueError):
        parse_llm_json('{"score": 9, "reason": "x"}')


def test_prompt_contains_no_date():
    prompt = PROMPT.format(text="Inflation remains elevated.")
    assert "2024" not in prompt and "Inflation remains elevated." in prompt


def test_dictionary_direction():
    assert dictionary_score("Inflation remains elevated; additional policy firming "
                            "may be appropriate.")["dict_score"] > 0
    assert dictionary_score("Activity has weakened and the stance remains "
                            "accommodative.")["dict_score"] < 0
    assert dictionary_score("The Committee met today.")["dict_score"] == 0


def test_weekend_statement_matched_to_next_trading_day():
    days = pd.bdate_range("2020-03-09", "2020-03-20")
    s = pd.Series(np.arange(len(days), dtype=float), index=days)
    move, t, prev = _move(s, pd.Timestamp("2020-03-15"), "bps")   # a Sunday
    assert t == pd.Timestamp("2020-03-16") and prev == pd.Timestamp("2020-03-13")
    assert move == pytest.approx(100.0)                            # +1.00% = +100 bps


def test_tone_change_uses_previous_statement_only():
    days = pd.bdate_range("2024-01-01", "2024-03-29")
    fred = pd.DataFrame({"DGS2": 4.0, "DGS10": 4.0}, index=days)
    target = pd.Series(5.5, index=pd.date_range("2024-01-01", "2024-03-31"))
    scores = pd.DataFrame({"date": pd.to_datetime(["2024-01-10", "2024-02-14", "2024-03-13"]),
                           "dict_score": [0.0, 0.5, -0.5], "llm_score": [1, 3, 0]})
    ev = build_events(scores, fred, pd.DataFrame(index=days), target)
    assert np.isnan(ev.loc[0, "d_llm"])
    assert list(ev["d_llm"].iloc[1:]) == [2, -3]


def test_scoring_is_cached_and_resumable(tmp_path):
    st = pd.DataFrame({"date": pd.to_datetime(["2024-01-31", "2024-03-20"]),
                       "text": ["Hawkish words.", "Dovish words."]})
    calls = []

    def fake(provider, model, key, prompt):
        calls.append(1)
        return json.dumps({"score": 2, "reason": "ok"})

    score_statements(st, "p", "m", "k", cache_dir=tmp_path, pause=0, call_fn=fake)
    score_statements(st, "p", "m", "k", cache_dir=tmp_path, pause=0, call_fn=fake)
    assert len(calls) == 2            # second run used the cache


def test_pick_provider(monkeypatch):
    provs = [("gemini", "GEMINI_API_KEY", "g"), ("openai", "OPENAI_API_KEY", "o")]
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "abc")
    assert pick_provider(provs) == ("openai", "o", "abc")
    monkeypatch.delenv("OPENAI_API_KEY")
    assert pick_provider(provs) is None


def test_bad_api_key_fails_fast(tmp_path):
    """A 401/404 (wrong key or model name) should stop at once, not retry for hours."""
    class Resp:
        status_code = 401
        text = "invalid key"

    class HTTPError(Exception):
        response = Resp()

    def bad(provider, model, key, prompt):
        raise HTTPError("401")

    st = pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]), "text": ["x"]})
    with pytest.raises(RuntimeError, match="API error 401"):
        score_statements(st, "gemini", "m", "k", cache_dir=tmp_path, pause=0, call_fn=bad)


def test_current_calendar_layout_statement_html_links():
    """fomccalendars.htm shows 'Statement: PDF | HTML' instead of a 'Statement' link."""
    page = """
    <div class="col-xs-12 col-md-4 col-lg-2">Statement:<br>
      <a href="/monetarypolicy/files/monetary20240131a1.pdf">PDF</a> |
      <a href="/newsevents/pressreleases/monetary20240131a.htm">HTML</a><br>
      <a href="/newsevents/pressreleases/monetary20240131a1.htm">Implementation Note</a>
    </div>
    <div>Minutes: <a href="/monetarypolicy/fomcminutes20240131.htm">HTML</a></div>
    <div>Statement on Longer-Run Goals:
      <a href="/newsevents/pressreleases/monetary20250822a.htm">HTML</a></div>
    """
    links = statement_links(page, "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm")
    assert [str(d) for d, _ in links] == ["2024-01-31"]


def test_fred_manual_csv_fallback(tmp_path):
    from src.market_data import _fred_series
    (tmp_path / "DGS2.csv").write_text("observation_date,DGS2\n2024-01-02,4.33\n2024-01-03,.\n")
    s = _fred_series("DGS2", "http://unused/{series}", str(tmp_path))
    assert s.iloc[0] == 4.33 and np.isnan(s.iloc[1])


def test_api_key_never_printed(tmp_path, capsys):
    calls = {"n": 0}

    def flaky(provider, model, key, prompt):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError(f"503 Server Error for url: https://x/?key={key}")
        return json.dumps({"score": 1, "reason": "ok"})

    st = pd.DataFrame({"date": pd.to_datetime(["2024-01-31"]), "text": ["x"]})
    score_statements(st, "gemini", "m", "SECRET123", cache_dir=tmp_path, pause=0, call_fn=flaky)
    assert "SECRET123" not in capsys.readouterr().out


def test_regression_recovers_known_effect():
    from src.analysis import ols_hc1
    rng = np.random.default_rng(3)
    X = np.column_stack([np.ones(500), rng.normal(size=500)])
    y = 2.0 + 4.0 * X[:, 1] + rng.normal(size=500)
    out = ols_hc1(y, X)
    assert abs(out["beta"][1] - 4.0) < 0.2 and out["t"][1] > 20 and out["p"][1] < 1e-6


def test_rate_change_effective_next_day():
    """15-Jun-2022: Fed hiked 75 bps, effective 16-Jun. Must be counted as +75."""
    days = pd.bdate_range("2022-06-01", "2022-06-30")
    fred = pd.DataFrame({"DGS2": 3.0, "DGS10": 3.0}, index=days)
    cal = pd.date_range("2022-06-01", "2022-06-30")
    target = pd.Series(1.0, index=cal)
    target.loc["2022-06-16":] = 1.75
    scores = pd.DataFrame({"date": pd.to_datetime(["2022-06-15"]), "dict_score": [0.5]})
    ev = build_events(scores, fred, pd.DataFrame(index=days), target)
    assert ev.loc[0, "rate_change_bps"] == pytest.approx(75)
