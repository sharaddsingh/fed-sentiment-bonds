# Project explained simply (for interview prep)

Read this until you can explain every point in your own words.

---

## 1. One-line pitch

> "I used an LLM to score every Federal Reserve statement since 2006 as hawkish or
> dovish, and tested whether a change in the Fed's tone predicts how Treasury
> yields, bond futures, the dollar and stocks move on the day."

## 2. Basic concepts

**The Fed / FOMC.** The US central bank. Its Federal Open Market Committee meets 8 times
a year, decides the interest rate, and publishes a short **statement** at 2:00 p.m.
New York time. Every market in the world watches it.

**Hawkish.** Worried about inflation, wants higher rates or tighter policy.
Typical market reaction: yields **up**, bond prices **down**, dollar **up**,
stocks often **down**.

**Dovish.** Worried about growth or jobs, wants lower rates or support.
Usually the opposite reaction.

**2-year Treasury yield.** The interest rate on a 2-year US government bond. It tracks
where the market thinks the Fed will set rates over the next 2 years, so it reacts
most to Fed news. That's why it's the main market in this project.

**Basis point (bp).** 0.01 percentage points. A yield going from 4.00% to 4.10% is +10 bps.

**10Y T-Note futures (ZN).** A futures contract on the 10-year Treasury note. When
yields go up, its price goes down. This is the same kind of instrument Futures
First analysts trade.

## 3. The pipeline (file by file)

| Step | File | What happens |
|---|---|---|
| 1 | `src/fed_statements.py` | Finds every "Statement" link on the Fed website, downloads it, keeps only the policy text |
| 2 | `src/dictionary.py` | Counts hawkish vs dovish words: score between -1 and +1 |
| 3 | `src/llm_scorer.py` | Asks an LLM for a -5 to +5 score + one-line reason (cached) |
| 4 | `src/market_data.py` | 2Y/10Y yields + Fed funds rate from FRED, futures/dollar/S&P from Yahoo |
| 5 | `src/events.py` | Tone change vs previous statement; market move on release day |
| 6 | `src/analysis.py` | Correlation, regression, hit rate, sub-periods |
| 7 | `run_analysis.py` | Runs everything, makes charts and REPORT.md |

## 4. The five design decisions interviewers will ask about

**1. Why tone CHANGE and not tone level?**
Markets react to *surprises*. If the Fed was hawkish last time and is equally hawkish
today, there is no news, so prices don't move. The change versus the previous
statement is a simple proxy for surprise. The report shows both, so you can compare.

**2. Why close-to-close on the release day?**
The statement comes out at 2 p.m. while markets are open, so the close-to-close move
on that day includes the reaction. Weakness: it also includes everything else that
happened that day (other news, the press conference). Intraday data would be cleaner.

**3. Why control for the rate change in the regression?**
Hawkish statements often come with rate hikes. I want to know whether the *words*
matter beyond the decision. So I compare R² with the rate decision only vs. rate
decision + tone. If R² goes up, the wording adds information.

**4. What is "LLM hindsight" and how did you handle it?**
The LLM was trained on news written after these statements. It might "know" that
2022 was a hiking cycle and score accordingly. That's a form of look-ahead bias.
I reduce it by sending only the statement text (no date, no headline) and telling
it to judge the wording only. The dictionary method can't have hindsight, so if
the LLM is much better, I check that the gap isn't just hindsight. Honest answer:
it can't be fully ruled out.

**5. Why also a dictionary method?**
It's a transparent baseline. If an expensive LLM can't beat counting words, it isn't
adding value. The dictionary fails on context: "inflation has eased" contains the
word "inflation" but is dovish. That's where the LLM should do better.

## 5. Statistics in plain words

- **Correlation (r):** between -1 and +1. How strongly two things move together.
  +0.3 is a meaningful relationship for daily market data.
- **Regression coefficient:** "If tone becomes 1 standard deviation more hawkish, the
  2Y yield moves about X bps."
- **t-stat:** how sure we are the effect isn't zero. Above about 2 (in absolute value)
  is usually considered significant.
- **Robust (HC1) standard errors:** crisis days have huge moves, so errors aren't
  uniform. Robust errors account for that.
- **R²:** share of the market move explained by the model (0 to 1).
- **Hit rate:** % of times the yield moved in the direction the tone change predicted.
  50% = coin flip.

## 6. Likely interview questions

- **"Was the LLM better than the dictionary?"** → No. At daily frequency both were
  weak (+0.10 vs +0.13) and the dictionary was slightly higher. Say it plainly:
  an expensive model didn't beat a simple baseline here, and here's why
  (expectations, press conferences, daily noise, scale saturation).
- **"So did the project fail?"** → No. The question was answered: Fed days move
  the 2Y yield ~60% more, but statement text alone (vs the previous statement)
  is a poor proxy for the surprise. Knowing *why* a signal is weak is useful research.
- **"Did it work in 2009-2015?"** → It was actually strongest there (0.25-0.30).
  I first expected it to be weaker, because short rates were stuck at zero. But
  then the statement wording (forward guidance) WAS the policy tool, so words
  mattered more. A good example of updating a hypothesis with data.
- **"What is scale saturation?"** → March 2009 (QE): the LLM already scored the
  previous statement -5, so the much more dovish QE statement also got -5 and the
  measured change was 0. Fix: ask the LLM to compare two statements directly.
- **"Which market reacts most?"** → the 2Y yield (as expected); the dollar and
  stocks barely react to tone at daily frequency.
- **"Pick one statement and explain the LLM's score."** → choose one from the "10
  biggest moves" table and read its reason.
- **"Could you trade this?"** → Not directly from daily closes, because by the
  close the move has already happened. You would need to score within seconds of
  2 p.m. That's the extension: real-time scoring plus a backtest on T-Note futures.
- **"What would you improve?"** → fed funds futures for the true surprise, intraday
  data, scoring press conferences and minutes, comparing several LLMs.

## 7. After running with real data

Write down: the correlation, hit rate and t-stat for LLM vs dictionary, the
sub-period results, and one interesting statement from the top-10 table with
the LLM's reason. Never round numbers in your favour.
