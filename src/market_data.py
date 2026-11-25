"""
Market data: Treasury yields and the Fed funds target from FRED (free, no key),
and futures / dollar index prices from Yahoo Finance. Everything is cached.
"""
from __future__ import annotations

import io
import os

import pandas as pd


BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"),
    "Accept": "text/csv,text/plain,*/*",
}


def _parse_fred_csv(text: str, series: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text))
    date_col = df.columns[0]                         # 'observation_date' or 'DATE'
    value_col = series if series in df.columns else df.columns[1]
    s = pd.to_numeric(df[value_col], errors="coerce")  # FRED uses '.' for missing
    s.index = pd.to_datetime(df[date_col])
    return s.rename(series)


def _fred_series(series: str, url_tpl: str, cache_dir: str, tries: int = 4) -> pd.Series:
    """Download one FRED series, with retries. If FRED keeps refusing, you can
    download the CSV in your browser and save it as data/<SERIES>.csv."""
    import time

    import requests

    manual = os.path.join(cache_dir, f"{series}.csv")
    if os.path.exists(manual):
        print(f"  using {manual}")
        with open(manual, encoding="utf-8") as f:
            return _parse_fred_csv(f.read(), series)

    url = url_tpl.format(series=series)
    last_err = None
    for attempt in range(tries):
        try:
            r = requests.get(url, timeout=60, headers=BROWSER_HEADERS)
            r.raise_for_status()
            with open(manual, "w", encoding="utf-8") as f:
                f.write(r.text)
            print(f"  {series}: ok")
            return _parse_fred_csv(r.text, series)
        except Exception as e:
            last_err = e
            wait = 5 * (attempt + 1)
            print(f"  {series}: attempt {attempt + 1} failed ({type(e).__name__}); "
                  f"retrying in {wait}s")
            time.sleep(wait)
    raise RuntimeError(
        f"Could not download {series} from FRED ({last_err}).\n"
        f"Fix: open {url} in your browser; it downloads a CSV file. "
        f"Save it as {manual} and run again.")


def _yf_close(ticker: str, start: str) -> pd.Series:
    import yfinance as yf
    df = yf.download(ticker, start=start, auto_adjust=False, progress=False)
    if df is None or df.empty:
        raise RuntimeError(f"No data for {ticker} from Yahoo Finance")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.rename(ticker)


def download_market_data(fred_series, yf_tickers, start, fred_url, cache_dir="data",
                         refresh=False):
    """Returns (fred DataFrame, yahoo DataFrame), each indexed by date."""
    os.makedirs(cache_dir, exist_ok=True)
    f_cache = os.path.join(cache_dir, "fred.csv")
    y_cache = os.path.join(cache_dir, "yahoo.csv")

    if os.path.exists(f_cache) and not refresh:
        fred = pd.read_csv(f_cache, index_col=0, parse_dates=True)
    else:
        print("Downloading FRED data ...")
        fred = pd.concat([_fred_series(s, fred_url, cache_dir) for s in fred_series], axis=1)
        fred = fred.loc[start:]
        fred.to_csv(f_cache)

    if os.path.exists(y_cache) and not refresh:
        yahoo = pd.read_csv(y_cache, index_col=0, parse_dates=True)
    else:
        print("Downloading Yahoo Finance data ...")
        yahoo = pd.concat([_yf_close(t, start) for t in yf_tickers], axis=1)
        yahoo.to_csv(y_cache)
    return fred, yahoo


def fed_funds_target(fred: pd.DataFrame) -> pd.Series:
    """One continuous policy-rate series: the single target until Dec 2008,
    the upper bound of the target range after."""
    old = fred.get("DFEDTAR", pd.Series(dtype=float))
    new = fred.get("DFEDTARU", pd.Series(dtype=float))
    return new.combine_first(old).ffill().rename("fed_funds_target")
