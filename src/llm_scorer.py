"""
LLM method: ask a language model to rate each statement from -5 (very dovish)
to +5 (very hawkish) and explain why in one sentence.

Design choices worth explaining in an interview:
  - The model sees ONLY the statement text (no date, no headline), and is told
    to judge the wording, not what it knows happened afterwards. LLMs were
    trained on later news, so "hindsight leakage" is a real risk; see README.
  - Scores are cached in data/, so the analysis is reproducible and each
    statement is only sent once (cheap, and kind to free-tier limits).
  - Plain HTTPS calls (requests) instead of provider SDKs, so the same code
    works for Gemini, OpenAI and Anthropic.
"""
from __future__ import annotations

import json
import os
import re
import time

import pandas as pd

PROMPT = """You are a fixed-income analyst. Rate the monetary-policy stance of the
following FOMC statement on a scale from -5 to +5:

  -5 = extremely dovish (aggressive easing, big rate cuts, emergency support)
   0 = neutral / balanced
  +5 = extremely hawkish (aggressive tightening, big rate hikes, strong inflation worry)

Judge ONLY the wording of this statement: the policy action, the description of
inflation and growth, and the guidance about future policy. Do not use any
knowledge of what happened after this statement was released.

Reply with JSON only, exactly like:
{{"score": <integer from -5 to 5>, "reason": "<one short sentence>"}}

STATEMENT:
\"\"\"
{text}
\"\"\"
"""


def pick_provider(providers):
    """First (provider, model, key) whose API key is set in the environment."""
    for name, env, model in providers:
        key = os.environ.get(env, "").strip()
        if key:
            return name, model, key
    return None


def parse_llm_json(raw: str) -> dict:
    """Pull {"score":..,"reason":..} out of a reply, even with ```json fences."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError(f"No JSON in reply: {raw[:200]}")
    obj = json.loads(m.group(0))
    score = int(round(float(obj["score"])))
    if not -5 <= score <= 5:
        raise ValueError(f"Score out of range: {score}")
    return {"llm_score": score, "llm_reason": str(obj.get("reason", "")).strip()}


def _call(provider: str, model: str, key: str, prompt: str) -> str:
    import requests
    if provider == "gemini":
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        r = requests.post(url, headers={"x-goog-api-key": key}, timeout=120, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        })
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

    if provider == "openai":
        r = requests.post("https://api.openai.com/v1/responses", timeout=120,
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": model, "input": prompt})
        r.raise_for_status()
        data = r.json()
        if data.get("output_text"):
            return data["output_text"]
        texts = [c.get("text", "") for item in data.get("output", [])
                 for c in item.get("content", []) or [] if c.get("type") == "output_text"]
        return "".join(texts)

    if provider == "anthropic":
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=120,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01"},
                          json={"model": model, "max_tokens": 300,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json()["content"])

    raise ValueError(f"Unknown provider {provider}")


def score_statements(statements: pd.DataFrame, provider: str, model: str, key: str,
                     cache_dir="data", pause=6.0, max_retries=5,
                     call_fn=None) -> pd.DataFrame:
    """Score every statement (cached). Returns date, llm_score, llm_reason."""
    call_fn = call_fn or _call
    os.makedirs(cache_dir, exist_ok=True)
    safe_model = re.sub(r"[^A-Za-z0-9.-]", "_", model)
    cache = os.path.join(cache_dir, f"llm_scores_{provider}_{safe_model}.csv")
    done = (pd.read_csv(cache, parse_dates=["date"]) if os.path.exists(cache)
            else pd.DataFrame(columns=["date", "llm_score", "llm_reason"]))
    have = set(done["date"]) if len(done) else set()

    todo = statements[~statements["date"].isin(have)]
    if len(todo):
        print(f"Scoring {len(todo)} statements with {provider}/{model} "
              f"(about {len(todo) * pause / 60:.0f} min) ...")
    consecutive_failures = 0
    for i, row in enumerate(todo.itertuples(index=False), 1):
        prompt = PROMPT.format(text=row.text)
        for attempt in range(max_retries):
            try:
                result = parse_llm_json(call_fn(provider, model, key, prompt))
                break
            except Exception as e:
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status in (400, 401, 403, 404):
                    body = getattr(e.response, "text", "")[:300].replace(key, "***")
                    raise RuntimeError(
                        f"{provider} API error {status}. Check your API key and the model "
                        f"name '{model}' in config.py.\nServer said: {body}") from e
                wait = pause * (2 ** attempt)
                msg = str(e).replace(key, "***") if key else str(e)   # never print the key
                print(f"  {row.date.date()}: attempt {attempt + 1} failed ({msg}); "
                      f"retrying in {wait:.0f}s")
                time.sleep(wait)
        else:
            consecutive_failures += 1
            print(f"  {row.date.date()}: giving up on this one, run again later to resume")
            if consecutive_failures >= 3:
                print("  3 statements in a row failed: stopping LLM scoring. "
                      "Scores so far are saved; run again later to continue.")
                break
            continue
        consecutive_failures = 0
        done = pd.concat([done, pd.DataFrame([{"date": row.date, **result}])],
                         ignore_index=True)
        done.to_csv(cache, index=False)      # save after every call -> safe to stop
        print(f"  [{i}/{len(todo)}] {row.date.date()}: {result['llm_score']:+d}  "
              f"{result['llm_reason'][:70]}")
        time.sleep(pause)
    done["date"] = pd.to_datetime(done["date"])
    done["llm_score"] = pd.to_numeric(done["llm_score"], errors="coerce")
    return done.sort_values("date").reset_index(drop=True)
