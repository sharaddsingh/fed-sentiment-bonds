"""
All settings in one place.

LLM SETUP (pick ONE, or none):
    Set an environment variable with your API key, e.g. in PowerShell:
        $env:GEMINI_API_KEY = "your-key"        # free tier, recommended
        $env:OPENAI_API_KEY = "your-key"
        $env:ANTHROPIC_API_KEY = "your-key"
    The first key found (in the order below) is used. With no key, the project
    still runs using only the dictionary (word-count) method.
"""

# ---------------------------------------------------------------------------
# Fed statements
# ---------------------------------------------------------------------------
START_YEAR = 2006           # Bernanke era onwards (~170 statements)
FED_BASE = "https://www.federalreserve.gov"
FED_RECENT_PAGE = FED_BASE + "/monetarypolicy/fomccalendars.htm"          # last ~5 years
FED_YEAR_PAGE = FED_BASE + "/monetarypolicy/fomchistorical{year}.htm"     # older years
REQUEST_PAUSE_SEC = 1.0     # be polite to the Fed's website

# ---------------------------------------------------------------------------
# LLM providers (model names change over time: if you get a "model not found"
# error, check the provider's docs and update the name here)
# ---------------------------------------------------------------------------
LLM_PROVIDERS = [
    # (provider, environment variable, model)
    ("gemini", "GEMINI_API_KEY", "gemini-3.5-flash-lite"),
    ("openai", "OPENAI_API_KEY", "gpt-6-luna"),
    ("anthropic", "ANTHROPIC_API_KEY", "claude-haiku-5-5"),
]
LLM_PAUSE_SEC = 6.0         # pause between calls (free tiers have per-minute limits)
LLM_MAX_RETRIES = 5

# ---------------------------------------------------------------------------
# Market data
# ---------------------------------------------------------------------------
# FRED series (free, no key): https://fred.stlouisfed.org
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
FRED_SERIES = {
    "DGS2": "2Y Treasury yield",
    "DGS10": "10Y Treasury yield",
    "DFEDTAR": "Fed funds target (until Dec 2008)",
    "DFEDTARU": "Fed funds target upper bound (from Dec 2008)",
}
# Yahoo Finance tickers
YF_TICKERS = {
    "ZN=F": "10Y T-Note futures",
    "DX-Y.NYB": "US Dollar index",
    "ES=F": "S&P 500 futures",
}

# Markets we measure the reaction of, and how
REACTIONS = {
    "d2y_bps": "2Y yield change (bps)",
    "d10y_bps": "10Y yield change (bps)",
    "zn_ret": "10Y T-Note futures return (%)",
    "dxy_ret": "US Dollar index return (%)",
    "es_ret": "S&P 500 futures return (%)",
}

# Sub-periods: normal interest rates vs. the zero-lower-bound era
SUBPERIODS = {
    "2006-2008 (normal rates)": ("2006-01-01", "2008-12-15"),
    "2009-2015 (zero lower bound)": ("2008-12-16", "2015-12-15"),
    "2016-today (normal rates)": ("2015-12-16", "2100-01-01"),
}

DATA_DIR = "data"
RESULTS_DIR = "results"
