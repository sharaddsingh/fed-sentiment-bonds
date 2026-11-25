"""
Download every FOMC statement from federalreserve.gov and extract its text.

How the Fed's website is organised:
  - fomccalendars.htm lists the last ~5 years of meetings
  - fomchistorical{YEAR}.htm lists older years
On both, each meeting has a link whose text is exactly "Statement". The link
contains the release date, e.g. .../monetary20240131a.htm -> 2024-01-31.

Inside a statement page we keep only the statement itself: from just after the
"For release at ..." line up to (not including) "Voting for ...". This drops
the headline, date, vote list, and website boilerplate, so the LLM sees only
the policy language and not the date.
"""
from __future__ import annotations

import os
import re
import time
from datetime import date
from urllib.parse import urljoin

import pandas as pd

HEADERS = {"User-Agent": "Mozilla/5.0 (research project; FOMC statement text analysis)"}
DATE_IN_URL = re.compile(r"(\d{8})[a-z]?\.htm$")
STATEMENT_URL = re.compile(r"/newsevents/press(?:releases)?/monetary/?\d{8}[a-z]\.htm$")


def _get(url: str) -> str:
    import requests
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text


def statement_links(html: str, base_url: str) -> list[tuple[date, str]]:
    """All (release_date, url) pairs for FOMC statement pages.

    Two layouts exist on the Fed's site:
      - historical year pages:  <a>Statement</a>
      - current calendar page:  Statement: <a>PDF</a> | <a>HTML</a>
    In both cases the URL looks like .../monetaryYYYYMMDDa.htm
    (implementation notes end in 'a1.htm' and are excluded by the pattern).
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(strip=True)
        if not STATEMENT_URL.search(href):
            continue
        if text == "Statement":
            pass
        elif text == "HTML":
            context = a.parent.get_text(" ", strip=True) if a.parent else ""
            if "Statement" not in context or "Longer-Run" in context:
                continue
        else:
            continue
        m = DATE_IN_URL.search(href)
        if not m:
            continue
        d = pd.to_datetime(m.group(1), format="%Y%m%d").date()
        out.append((d, urljoin(base_url, href)))
    return out


def extract_statement_text(html: str) -> str:
    """Return only the policy statement paragraphs from a statement page."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in soup.find_all("p")]
    paras = [p for p in paras if p]

    start = None
    for i, p in enumerate(paras):
        if re.match(r"^For (immediate )?release", p, re.I):
            start = i + 1
            break
    if start is None:   # fallback: first paragraph that talks about the Committee
        start = next((i for i, p in enumerate(paras)
                      if "Committee" in p or "Information received" in p), 0)

    end = len(paras)
    for i in range(start, len(paras)):
        p = paras[i]
        if (p.startswith("Voting for") or p.startswith("For media inquiries")
                or p.startswith("Last Update") or p.startswith("Implementation Note")):
            end = i
            break
    return "\n\n".join(paras[start:end]).strip()


def list_all_statements(start_year: int, recent_page: str, year_page: str,
                        pause: float = 1.0) -> list[tuple[date, str]]:
    links = {}
    pages = [recent_page] + [year_page.format(year=y)
                             for y in range(start_year, date.today().year)]
    for page in pages:
        print(f"Reading {page}")
        try:
            html = _get(page)
        except Exception as e:   # recent years have no historical page yet: normal
            print("  (no historical page for this year yet, covered by the calendar page)"
                  if "404" in str(e) else f"  skipped ({e})")
            continue
        for d, url in statement_links(html, page):
            if d.year >= start_year:
                links[d] = url
        time.sleep(pause)
    return sorted(links.items())


def download_statements(start_year, recent_page, year_page, cache_dir="data",
                        refresh=False, pause=1.0) -> pd.DataFrame:
    """DataFrame with columns: date, url, text (cached in data/statements.csv)."""
    os.makedirs(cache_dir, exist_ok=True)
    cache = os.path.join(cache_dir, "statements.csv")
    existing = pd.DataFrame(columns=["date", "url", "text"])
    if os.path.exists(cache):
        existing = pd.read_csv(cache, parse_dates=["date"])
        if not refresh:
            print(f"Loaded {len(existing)} cached statements from {cache} "
                  "(use --refresh to check for new ones)")
            return existing

    links = list_all_statements(start_year, recent_page, year_page, pause)
    have = set(existing["date"].dt.date) if len(existing) else set()
    rows = []
    for d, url in links:
        if d in have:
            continue
        print(f"Downloading statement {d}")
        try:
            text = extract_statement_text(_get(url))
        except Exception as e:
            print(f"  failed: {e}")
            continue
        if len(text) < 200:
            print(f"  warning: very short text ({len(text)} chars), check {url}")
        rows.append({"date": pd.Timestamp(d), "url": url, "text": text})
        time.sleep(pause)

    df = pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df.to_csv(cache, index=False)
    print(f"{len(df)} statements saved to {cache}")
    return df
