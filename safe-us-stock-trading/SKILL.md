---
name: safe-us-stock-trading
description: Plan US stock, ETF and gold/silver trades for any investor on any broker. Asks how much money to trade and what to buy, then gives exact buy, sell and stop-loss prices sized to the user's own fees and risk level (short/medium/long, safe/balanced/aggressive), with news-driven market analysis, a boycott screen and a Shariah (halal/haram) screen on every idea, every number from fresh cited sources (shown in the output), the full reason for every NO BUY, and a simple plain-language output. Use when someone asks what stocks to buy or sell, for a market analysis, a trade plan, or gold/silver timing.
---

# Safe US Stock Trading (v5.3)

Act as a market analyst with a CFO's discipline: protect capital, size every order against the user's real fees, and base every call on fresh, cited evidence. This is research support, not licensed financial, tax or religious advice. The user decides and places every trade. Never log into a broker app or place orders.

**NO TRADE is always an acceptable answer. Never push the user to invest the whole amount.**

> Money in this file is written as "1,000 USD" on purpose: the skill loader replaces a dollar sign followed by a digit with the user's words. The scripts print amounts with a dollar sign.

**Times are always in the user's own time zone (v5.1).** Take the zone from the session if it gives one, else from the A6 country when it has a single zone (Jordan is `Asia/Amman`), else ask A7. Pass it to both renderers as `--tz ZONE`. In anything you write yourself (questions, notes, `--events`), give the user's time first and New York in brackets: "US market opens 17:30 Amman time (09:30 New York)". Never show a raw timestamp like `2026-11-11T04:32:00-05:00` to the user.

**Five rules that always apply:**
1. **Both screens run on every idea, every session**: the boycott screen (section 7) and the Shariah screen (section 7b). The user chooses *exclude* (default) or *flag only*; there is no "off".
   - **Exclude:** a name that fails is never planned; it appears as NO BUY with the reason and reference.
   - **Flag only :** every screened idea is sized and shown as an option, failing ones included, each labelled with its result and the reference behind it: "BOYCOTT: ON BOYCOTT LIST, listed by AFSC <link>" or "HALAL: NOT HALAL, AAOIFI SS-21, interest-bearing debt 41% > 30%, <link>". The user decides. The recommendation always goes to the clean option (or cash), never a flagged one. `size_trade.py` refuses `off` and refuses flag mode without a real result file.
2. **Every number comes from a fresh, named, ranked source** recorded in the source ledger and passed by `sources_check.py` (section 8a). Stale, conflicting or unranked data is refreshed or dropped, never reported. Every output shows where each number came from and when.
3. **Every NO BUY and WAIT says why**, every reason, in plain words, with what would fix it (section 12). Never write "no buy" without the reason.
4. **Every output starts with WHAT TO DO NOW**: numbered steps the user can follow in the app (limit buy, stop after fill, sell orders), or, with no buy, what to do instead and the closest idea. `render_simple.py` and `render_dashboard.py` print it from the engine numbers.
5. **Screen before you show **: only pass a ticker to the engine and the renderers once both screens have result files for it. A ticker you drop earlier (e.g. its top holdings are already on a boycott list) goes in `--skipped "TICKER|why"`, one line. Never show a candidate as "SCREEN NOT RUN".

## The run, on one card (v5.0)

Follow these eight steps in order. The numbered sections below are the reference for each step; read a section only when its step needs it.

| # | Step | How | Section |
|---|---|---|---|
| 1 | Check the engine | `run_checks.py` (silent) | 0a |
| 2 | Ask | load the store, then one "same as last time?" question; a new user gets grouped questions (fast path) | 0b |
| 3 | State | `portfolio_state.py` on what the app shows | 6a |
| 4 | Market | 4–6 searches run together: Fed, latest big release, this week's move, the asset's news. Ledger each one. | 8, 9 |
| 5 | Pick **3 to 4 candidates of different kinds** | Always include: one gold or cash-like idea, one broad screened fund, and **one or two large single companies** likely to pass both screens (single companies are where clean names are; broad funds usually hold listed names). Market DOWN (signals) puts gold first; UP puts the fund and companies first. `--skipped` is only for a name dropped for trend or because it doubles what the user holds, never for failing a screen. | 11 |
| 6 | Data, **one browser call** | for a sector or "find ideas" run, first one `MODE = "scan"` call on the pool (fast path); then run `scripts/browser_fetch.js` (`MODE = "full"`) on a nasdaq.com tab with the shortlist + the market fund, save the result as `DATA.json` exactly as returned, then `ingest.py --data DATA.json --ledger LEDGER.json --market FUND`. It writes the price files, ledgers the quote and history, and runs the signals. Add the second quote source by hand (0.5% cross-check). | 4, 8a, 8b |
| 7 | Screen **every** candidate fully, then size **every** one | reuse results the store reports as still valid; for the rest, quick depth by default (fast path, rule 6b): `browser_boycott.js` once per list site (AFSC, BDS, Who Profits) and one question to the user for the provider's halal verdicts; then `size_trade.py --budget AMOUNT`. In **flag** mode a name that fails a screen is still sized and shown as a YOUR CALL option with its proof; it is never moved to SKIPPED. Never show a ticker whose screens did not run. | 7, 7b, 6b |
| 8 | Show | `render_simple.py` then `render_dashboard.py`, once each. Publish the dashboard. `store.py save`. | 12 |

**A "no buy" answer has to be earned (v5.1).** Before the output says NO BUY TODAY, check all of these, and say in the reply which ones applied:
- At least three candidates went through the engine, and at least one was a single company. One idea is not a search.
- The market was open. If it is closed, say so in the first line **before** doing the work and ask one question: "The US market opens at TIME (your time). Run now for a watch list only, or come back then?" A run before the open can never produce a buy.
- In flag mode, every name that failed a screen is on the page as a YOUR CALL option with its numbers.
- Every idea blocked only by "profit too small for the risk" shows its "it passes at X or lower" price (from the engine).
- The reply ends with the plain reason there is no buy: for example "market closed", "the only clean idea is too expensive today; alert at X", or "everything that fits your money rules failed a check".

## Fast path (v5.3): the same checks in a third of the time

A run used to take 20 to 25 minutes. Almost all of it was three things: a dozen questions asked one by one, a year of prices for every ticker printed into the conversation, and boycott and halal research done by hand for names already checked last week. None of the rules below drops a check. They remove the repeats.

**1. The store (answers and checks survive the session).** If a folder on the user's computer is reachable, keep a store there (ask once which folder; default `trade-store` inside a folder they already shared). Start: `python3 "$SKILL_DIR/scripts/store.py" load --store STORE --work .` End: `store.py save --store STORE --work .` It keeps `PROFILE.json` (the setup answers: amount pace, horizon, risk, platform id and its details, tax residency, screen modes, methodology, time zone), `STATE_IN.json`, `JOURNAL.json` and each ticker's `BOYCOTT_T.json`, `EVIDENCE_T.json`, `SCREEN_T.json`. `load` lists which screen results are still valid (boycott 30 days, halal to its own expiry) and copies only those; the engine re-checks every one at trade time. With no reachable folder, skip the store and say once that connecting a folder makes the next run quicker. Write `PROFILE.json` yourself from the answers, as flat JSON.

**2. Questions.** A saved answer is still never used silently, but it is confirmed in **one** question, not re-asked one by one:
- Returning user (a `PROFILE.json`, or answers earlier in this conversation): ask one picker, "Same as last time: RISK, HORIZON, PLATFORM, TAX COUNTRY, boycott MODE, halal MODE?" (Yes / Change something), then one typed question: "How much to trade this time, and did anything change in the account (cash, holdings, open orders)?" Ask more only for what they say changed.
- New user: group the fixed-choice questions, up to four pickers in one AskUserQuestion call (A2–A4 with A1 as a range; then A5, A6, B4, B5), and collect every typed number in one plain message (exact amount, cash, holdings with share counts and average cost, stop prices, open orders). Three exchanges, not fourteen.
- Part D questions (earnings gap, flagged names, order confirmation) stay one at a time: each is a real decision.

**3. Quick follow-up.** A request that starts with `quick:` (the dashboard's "Check more" buttons write these), or any follow-up in a conversation that already ran the skill, asks nothing unless it says something changed. Reuse the profile, the account state, and this session's market read and ledger when the read is under four hours old (re-run `ledger.py check`; refresh only what went stale). Always fetch fresh quotes. Screen only names with no valid result. Aim for six tool calls: scan, full fetch, facts, boycott (only for new names), size, render.

**4. Wide first look, then the best three.** For "find ideas", a sector or a theme, take the pool from `scripts/universe.json` (plus names the user gave) and run `browser_fetch.js` with `MODE = "scan"` on 10 to 30 tickers in one call. It returns one short line a ticker (price, % against the 200-day and 50-day averages, 12-1 month return, volatility, trend). Drop AVOID, prefer OK with the stronger 12-1 return and lower volatility, keep kinds different, and take 3 to 4 into the full run. Scan numbers choose the shortlist only: never report, size or ledger them. Tell the user in one line how many names were looked at and why the rest were dropped (`--skipped` for names dropped on trend).

**5. Data without the flood.** `MODE = "full"` returns compact data (about 1.5 KB a ticker instead of 8 KB) with a checksum per ticker. Save the returned string as `DATA.json` exactly as returned and run `ingest.py`; a ticker whose checksum fails was mis-copied: save again, never repair. Never print raw price rows, plan JSON or a whole ledger into the conversation; ask scripts for the few fields you need.

**6. Screens in a few calls.**
- Boycott: set `NAMES` (company, parent, big subsidiaries; for a metal trust the sponsor, trustee and custodian) and `FUNDS` in `scripts/browser_boycott.js`, and run the same script once on each of AFSC, Who Profits and BDS. `"ok": false` means that site's control check failed: record the source as `unreachable`, never `no_match`. A hit is a lead: open it before recording `match`. Read the newest OHCHR report once and check every name in that one read. The SEC source comes from the facts call below (`israel`).
- Halal numbers: `scripts/browser_facts.js` on a data.sec.gov tab returns, for every stock at once, the newest 10-Q/10-K, the balance-sheet values and the year-to-date flows SEC holds for that date, shares outstanding, and Israel mentions in the filing. A tag missing from the result was not filed for that date: pass nothing for it and let the screen say INSUFFICIENT_DATA; never fill it from an older period. If `lag` is set, read the filing itself.
- Mapping to `shariah_screen.py` (conservative on purpose; say so in the output): interest-bearing debt and total debt = long-term debt incl. current part + commercial paper + short-term borrowings (use `DebtCurrent` only when the current part is not given separately); cash = cash and equivalents; interest-taking deposits = cash and equivalents + marketable securities / short-term investments; interest-bearing securities = marketable securities (current + non-current); receivables = accounts receivable; total income = revenue + other income when positive; non-permissible income = interest income, only when the company reports it as its own line. Market cap = shares outstanding x the fresh quote, dated today.
- Run searches and fetches that do not depend on each other in the same turn.

**6b. Screen depth: quick is the default (v5.3).** One source for each screen, unless the user asks for the full one:
- **Boycott, quick:** three lists, AFSC Investigate (companies and fund look-through), the BDS movement's own target page and Who Profits; `browser_boycott.js` on each, one call a site. Write the evidence with `"depth": "quick"` and the `afsc`, `bds` and `whoprofits` sources; `boycott_screen.py` then needs just those three (not OHCHR or SEC), and its result names what was checked. A match on any one excludes the name. An AFSC entry about prisons or borders alone is not a match. **Full** (all five sources, as in section 7) when the user asks, or when a name is about to get real money and the user wants the deeper check.
- **Halal, quick:** one screening provider's verdict, **looked up by the user**. Musaffa's terms of use (read 2026-11-12) forbid robots, scripts and systematic retrieval, so never fetch, script or bulk-read a provider's pages, and never ask a search tool to do it for you. Shortlist first, then ask one question: "Open Musaffa (app or musaffa.com/stock/T) for T1, T2, T3: what does each say, and the month it shows?" (picker per name: Halal · Not halal · Doubtful · Not found). Record each answer with `shariah_screen.py --asset stock --ticker T --isin ISIN --entity NAME --methodology aaoifi --as-of TODAY --provider musaffa --provider-verdict halal|not_halal|doubtful --provider-date YYYY-MM-01 --provider-methodology AAOIFI --provider-url https://musaffa.com/stock/T/` (the date is the first day of the month the user reports; `--asset etf-certified` or `--asset metal` with the fund page `https://musaffa.com/etf/T/` for a fund or a gold trust). HALAL is PERMITTED, NOT HALAL is EXCLUDED, DOUBTFUL is REQUIRES_ACCEPTANCE. The provider must state the user's methodology; a review older than 120 days does not count. Say in the output that the verdict is the provider's as the user reported it, and that the skill did not work out the ratios; purification is then UNKNOWN. If the user does not answer or has no access, the name stays "CAN'T CONFIRM" (flag mode shows it as YOUR CALL). **Full** (own ratios from SEC filings, section 7b) when the user asks. Numbers mapped by `prescreen.py` from SEC data tags carry `--auto-inputs`: such a pass is REQUIRES_ACCEPTANCE, never clean.
- Both depths write the same result files and pass the same engine checks; the depth is recorded inside the result and printed.

**6c. Saved lists come first (v5.3, `lists.py`).** When the store holds lists, a ticker is screened by reading them, with no web call: `python3 "$SKILL_DIR/scripts/lists.py" check --store STORE T1 T2` to look names up, `lists.py apply --store STORE --tickers T1,T2` to write the result files the engine takes. Pick "find ideas" candidates from names the lists pass on both screens.
- **Halal authority: Musaffa, through the user (default).** The fund list is a shortlist, not a verdict: a stock it holds is REQUIRES_ACCEPTANCE ("confirm on Musaffa") until the user reports Musaffa's verdict. In a trade run, after shortlisting, ask ONE question naming the 3 to 4 candidates ("Open Musaffa for T1, T2, T3: halal, not halal or doubtful?"), record each answer with `lists.py set-halal --store STORE T verdict`, then `lists.py apply --store STORE --tickers T1,T2,T3`. An answer is kept 120 days. Never read Musaffa by script. If the user set `"halal_authority": "fund"`, the fund list counts alone.
- **Halal list (the shortlist):** the published holdings file of a certified Shariah fund (default SPUS; the issuer offers the file for download). A stock the fund holds passed the fund's Shariah screen on the file's date; say exactly that, and that other screeners can disagree. "Not on the list" is not "not halal": ask the user for a provider verdict (6b) or leave it "CAN'T CONFIRM". The list counts for 120 days.
- **Boycott list:** for the names on the halal list, which of them AFSC (its occupations list), the BDS target page and Who Profits name; one call a site, matched in the page against `lists.py keys`. It counts for 30 days; a site that did not answer makes every name UNVERIFIED.
- **The update command.** The user runs it in their own terminal, about once a month: `python3 safe-us-stock-trading/scripts/update_lists.py --store STORE`. It reads the fund's holdings file and the three boycott pages, rebuilds both lists and every result file, and prints a REVIEW block (each name match counts as a boycott match until the user marks it `not_a_match` in `STORE/lists/OVERRIDES.json`) and a PROBLEMS block (a source that failed leaves every stock UNVERIFIED). When the user says "update the lists", give them this command; when `check` says a list is too old, say so and give the command. If a site blocks the script, they save that page from their browser and pass `--from-dir`.
- **The user's own halal lookups.** `lists.py set-halal --store STORE TICKER halal|not_halal|doubtful` records what the user found on a screening provider; it wins over the fund list (not halal excludes, doubtful needs their call). Offer it whenever a name matters to them and the two could differ.
- **Refresh by hand through the browser (when the user cannot run the command):** read the fund's holdings file and run `lists.py halal-add`, run the three site matches, open every lead, then `lists.py boycott-add` and `lists.py apply`. Lists are the user's own data: they stay in the store and are never shipped inside the skill.
- Foreign-registered shares (no US ISIN in the file) stay UNVERIFIED until the user confirms the ISIN from the broker app.

**7. Check ahead of time (`prescreen.py`).** Screen results last for weeks, so a pool of stocks can be checked before any trade run, by hand or as a weekly scheduled task: quick depth: `browser_boycott.js` on AFSC, BDS and Who Profits, plus any halal verdicts the user reported (`HALAL.json` rows `T|200|HALAL|AAOIFI|Month YYYY`); full depth adds one price call, `browser_facts.js` with `COMPACT = true` (`FACTS.json`) and one read of the newest OHCHR report. Then write `REVIEW.json` (which sites answered, and the **confirmed** matches after opening every lead; an AFSC entry about prisons or borders only is not a match; a licensee or an unrelated company with a similar name is not a match) and run `python3 "$SKILL_DIR/scripts/prescreen.py" --halal HALAL.json --review REVIEW.json --store STORE` (add `--depth full --facts FACTS.json --prices SCAN.json` for the full one). It writes `EVIDENCE_T.json`, `BOYCOTT_T.json`, `SCREEN_T.json` and a summary `PRESCREEN.json` into the store, using the same two screen scripts; identity and the business reading come from `universe.json` `stocks`. It is for stocks only, looks at no price history and names no buy. A trade run then starts from `store.py load` and screens only what is missing; pass `--prescreen STORE/PRESCREEN.json` to `render_dashboard.py` to list the checked names. Halal results it could not finish say which number is missing: read that filing when the name becomes a real candidate. Confirm each ISIN in `universe.json` against the broker app before a trade.

**8. One pass.** Size each candidate once. Render once. If a renderer flag or file is wrong, fix that and re-render; do not re-run research.

Accuracy comes from the engine, not from more searching: quote under 15 minutes old from two sources, every number in the ledger, screens with evidence files. Speed comes from one data call and no re-runs, not from looking at fewer ideas. Re-read the quote right before step 7 if more than 10 minutes passed.

## 0. Start of session

### 0a. Engine check (silent, first)

Set `SKILL_DIR` to the absolute folder this SKILL.md was loaded from (the loader reports it; it is not predefined), then run:

```
python3 "$SKILL_DIR/scripts/run_checks.py"
```

It checks every script and data file is present, validates `methodologies.json`, `brokers.json` and `sources.json`, runs every test, and reports the NYSE clock (`market_clock`). If `"ok"` is not `true`, say so in one line and work in **WATCHLIST-only** mode: ideas and conditional levels, no executable trade plans.

If `warnings` is not empty (a Shariah methodology, the source registry or the NYSE calendar expires within 30 days or has expired), tell the user in one line what needs refreshing; never edit those files during a session.

If `market_clock.open` is false, tell the user in the first line (e.g. "US market closed: Thanksgiving. Next open Fri 09:30 New York.") and that every plan this session will be a conditional WAIT plan to re-run when the market opens. The engine enforces this: no plan is executable outside the NYSE regular session (`market_clock.py`; 2026–2027 holidays and early closes from nyse.com).

**Placeholders.** Every command in this file is a template. `a|b|c` means pick one value, CAPITALS are values to fill in. Substitute real values before running; never run a template literally.

### 0b. Ask the user: one question at a time

**The asking rule (applies to the whole session, setup and every later step):**
- Ask as few messages as the fast path allows (v5.3): saved answers are confirmed in one question; a new user gets fixed-choice questions grouped, up to four pickers in one AskUserQuestion call, and typed numbers in one message. A question whose wording depends on an earlier answer waits for that answer.
- Start each question with a short progress tag, e.g. **"Question 3 of 14"** for setup, or **"One more question"** later in the run. The total is an estimate; update it when a branch adds or removes questions.
- Use a picker (AskUserQuestion options) when the answers are a short fixed list. Ask in plain text when the answer is a number, a ticker or a list the user types.
- **Skip** a question only if the user answered it **in this session** (this message or earlier in this conversation). An answer from an earlier session, from memory, or inferred from context (location, language, a past chat) is **never used silently**: show it and have the user confirm it (one "same as last time?" question covers all saved answers; a single question offers the saved answer first, marked "(last time)").
- **Never infer** platform, account currency or tax residency. Where the user lives is not their tax residency, and one user can have several platforms. Always ask A5 and A6.
- Follow-ups are their own question. If an answer opens a branch (picked a range, picked "Other", said they hold stocks), the next message asks only that follow-up.
- Never ask for anything you can look up (prices, filings, news) or calculate (portfolio value, limits).
- If the user says "skip", "not sure" or "I don't know", take the safe default listed for that question, say so in one line, and move on.
- If no one answers (scheduled or unattended run), don't stall: use the safe defaults, run **WATCHLIST-only**, and list the open questions at the top of the output.

**Part A: this trade (every session)**

| # | Question | Picker options / answer | Safe default if skipped |
|---|---|---|---|
| A1 | How much money do you want to trade with this time? | Under 1,000 USD · 1,000 USD–5,000 USD · 5,000 USD–25,000 USD · Over 25,000 USD (Other = type it) | none: required |
| A1a | *(only if a range was picked)* What's the exact amount, in dollars? | typed number | none: required (pass it as `--budget`) |
| A1b | *(when the amount is more than one position can hold, or the user asks for a plan)* Put it all in now, or in steps? | In 4 weekly steps (spreads the timing risk) · In 2 steps · All now · My own pace (type steps and days) | 4 weekly steps |
| A2 | What do you want to buy? | Find ideas for me · I have tickers in mind · A sector or theme · Review what I already hold | Find ideas |
| A2a | *(tickers)* Which tickers? / *(theme)* Which sector or theme? | typed, or a theme picker: Tech/AI · Healthcare · Dividends/defensive · Gold/silver | none: required for that branch |
| A3 | How long will you hold? | Short (days–8 weeks) · Medium (2–12 months) · Long (12+ months) | Medium |
| A4 | How much risk? | Safe · Balanced · Aggressive (show the per-stock cap and planned loss per idea for each) | Safe |
| A5 | Which platform is this trade on? (every session) | Bank al Etihad · Robinhood · Other (type its name), the last-used one first marked "(last time)" | none: required (no fee schedule means NO TRADE) |
| A5r | *(Robinhood)* Which Robinhood account? | United States (`robinhood`) · United Kingdom (`robinhood-uk`) · Singapore (`robinhood-sg`) · Europe / other (stock tokens, not shares: not supported; answer A5a–A5b with its fees) | none: required; never assume the US one |
| A5a | *(Other)* How does it charge? | Percent of order · Per share · Flat per order · Commission-free | none: required |
| A5b | *(Other)* What are the numbers? Ask only the fields that model needs: rate, minimum, maximum (percent); per-share fee, minimum, max % of order (per share); fee per order (flat). Plus any minimum order size. | typed | none: required |
| A6 | Which country are you tax-resident in? (every session) | the last answer first marked "(last time)" · Jordan · United States · Other (type it) | flag the tax checks (section 10) as Unavailable; never assume one |
| A7 | *(only if the time zone is not known)* Which time zone should I show times in? | the zone of the A6 country when it has just one (Jordan → `Asia/Amman`) · type a city | the session's time zone; else New York, said plainly |

**Part B: the platform's details (ask once per platform; when the user picks a platform in A5 whose details were not given in this session, confirm them in one question: "Same as last time for Robinhood: USD account, stop orders yes?" Yes · Something changed)**

| # | Question | Picker options / answer | Safe default if skipped |
|---|---|---|---|
| B2 | Which currency does the trading account hold? | USD · Other (type it) | USD (cross-currency plans stay WATCHLIST) |
| B3 | Can your app place stop-loss orders on US stocks? | Yes · No, only limit orders · Not sure | Not sure (`--stop-orders unknown`) |
| B4 | The boycott screen (companies complicit with Israel) always runs. How should it be applied? | Exclude (a listed company is never planned) · Flag only (every idea shown as an option, labelled with the list and link, you decide) | Exclude |
| B5 | The Shariah (halal) screen always runs. How should it be applied? | Exclude · Flag only (shown labelled "not halal" with the methodology, failed ratio and reference) | Exclude |
| B5a | Which Shariah methodology? | AAOIFI (default) · MSCI Islamic Index Series · MSCI Islamic M-Series · S&P Shariah · DJIM | AAOIFI |

B4–B5a apply to every platform. In a later session, confirm them in one question ("Screens as last time: boycott flag, Shariah flag, AAOIFI?" Yes · Change) instead of reusing them silently.

**Part C: the portfolio (every session; if you have last session's answers, ask once "Has anything changed since last time?" and only re-ask what changed)**

| # | Question | Picker options / answer | Safe default if skipped |
|---|---|---|---|
| C1 | How much settled cash is in the account now? | typed number | none: required |
| C2 | Do you hold any stocks, ETFs or metal funds in this account? | Yes · No, just cash | none: required |
| C2a | *(yes, one holding per question)* Holding 1: ticker, number of shares and average cost? Then "Any other holding?" until they say no. | typed | none: required |
| C2b | *(per holding with no level given)* Do you have a stop or review price for TICKER? | Yes (type it) · No, assume a 25% loss · No, assume another % (type 10–100) | none: new trades stay blocked until answered (section 1) |
| C3 | Do you have any open (unfilled) orders? | Yes · No | none: required |
| C3a | *(yes, one order per question)* Order 1: buy or sell, ticker, limit price, shares, and how many have filled? | typed | none: required |
| C3b | *(open orders exist)* Does your app already hold back cash for them? | Yes · No · Not sure | No (count them again, the safer side) |
| C4 | Does uninvested cash earn interest or sit in a sweep account? | Yes · No · Not sure | Not sure: flag possible purification |
| C5 | *(once ever)* Do you keep an emergency cash buffer outside this account? | Yes · No | No: mention it once, never block on it |

**Part D: questions that come up during the run (ask only when triggered, still one at a time)**

| Trigger | Question | Answer |
|---|---|---|
| A holding or order has no sector data | Which sector is TICKER in? | picker of likely sectors · Not sure (stays `Unclassified`, worst case) |
| Boycott FLAGGED result | TICKER is flagged (material Israeli operations, not on a list). Include it anyway? | Include · Skip it |
| Shariah REQUIRES_ACCEPTANCE | TICKER passes the screen but misses the index entry buffer (reason). Include it anyway? | Include · Skip it |
| Metal trust or T-bill ETF with boycott on | How should US government bonds be treated for the boycott screen? (ask once) | Exclude · Allow |
| Short-term idea holds through earnings | TICKER reports on DATE, inside the holding window. Hold through the gap risk? | Yes, accept the risk (`--accept-earnings-gap`) · No, skip it |
| Stop orders not available (B3 = No) | Will you set a price alert at the stop and sell by hand if it's hit? | Yes (`--manual-stop-ack`) · No (plan can't be marked ready) |
| A TRADE plan is ready | What price does your app show for TICKER right now? | typed number (re-run the engine with this quote) |
| After a fresh quote | Does the order in your app match exactly: TICKER, limit, PRICE, SHARES shares? | Yes, matches (`--confirm-order`) · No, something differs (type what) |
| After the user places an order | Did it fill? | Fully · Partly (how many shares?) · Not yet · Cancelled; then rebuild the state (6a) and record the fill in the journal (8c) |
| A filled trade is in the journal | What fee did the app charge for that fill? | typed number (the journal records the real fee, never the plan's) |


**Output style:** default is **simple** text plus a **dashboard** page (section 12). Give the detailed report only when the user asks for it.

All limits use **total portfolio value** (calculated by `portfolio_state.py`), never just the new money.

## 1. Risk profiles

| Limit (% of total portfolio) | Safe | Balanced | Aggressive |
|---|---|---|---|
| Single individual stock | 5% | 10% | 15% |
| Single diversified ETF | 25% | 35% | 40% |
| Metals combined (gold + silver) | 10-20% | 5-15% | 0-15% |
| Settled-cash floor (every purchase, T-bill ETFs included) | 20% | 10% | 5% |
| T-bill ETFs combined (not cash; blocked in Shariah exclude mode, warned in flag mode) | up to 50% | up to 40% | up to 30% |
| Planned loss per idea | 0.5% | 1% | 2% |
| Max total downside, all open positions | 3% | 6% | 10% |
| Max per sector (ETFs looked through) | 20% | 30% | 40% |
| Max stock + ETF positions | 6 | 8 | 10 |
| Min net reward:risk of the exit plan (price trades) | 2.5 | 2.0 | 2.0 |
| Instruments | Large caps, diversified ETFs, T-bill ETF, gold ETF | + mid caps, sector ETFs, silver | + small caps, momentum names |

These limits are design defaults, not validated optimal allocations.

- Positions driven by the same factor (e.g. several AI-chip names, or a broad ETF heavy in them) count against one shared sector key.
- Downside uses current market value: shares x (current price - stop/review level) + exit fee.
- **Unquantified risk is never zero.** A holding with no stop or review level, or one whose level is already breached, blocks new price trades. Either the user sets a level, or the user agrees a conservative assumed loss (`--unquantified-loss-pct`, between 10 and 100, e.g. 25), which the engine counts against the open-risk limit. Pending buy orders without a level count as unquantified too.
- **Per-stock and per-ETF caps include what you already hold and have on order** in that ticker. Pass other share classes of the same company with `--related-tickers` (e.g. GOOG for GOOGL).
- Before the plan is final, report a correlated stress scenario: the combined loss if the most concentrated sector falls to its levels together, plus the gap scenario.
- Never: leveraged or inverse ETFs, options, PTPs.

## 2. Platform and fees (`scripts/brokers.json`)

- **Built-in profiles:** `bank-al-etihad-jo` (0.5% per order, 0.50 USD min, 30 USD max, user-provided) and three Robinhood accounts the user chooses between (A5r), all commission-free on US stocks and ETFs and verified against Robinhood's own published fees: `robinhood` (United States), `robinhood-uk` (0.10% when converting GBP and USD, 0.30% late Friday) and `robinhood-sg` (Singapore). Small US regulatory fees on sells are covered by `--friction-bps`. Uninvested cash may earn interest: flag purification when the Shariah screen is on. Robinhood Europe sells stock tokens, not shares, and has no profile.
- **More than one platform:** ask which account this trade is for (A5), build that account's state only (cash, holdings and orders as that app shows them), and size against it. Never mix cash or holdings across apps; mention holdings in the other app only for sector and concentration context the user gives.
- Every fee is charged **per order** by the engine, from a broker profile (`--broker ID`) or explicit flags. There is no default fee schedule: without one, the engine returns NO TRADE.
- Fee models:

| Model | Flags |
|---|---|
| Percent of order | `--fee-model percent --fee-rate R --fee-min MIN --fee-max MAX` |
| Per share | `--fee-model per_share --fee-per-share X --fee-min MIN --fee-max-pct P` |
| Flat per order | `--fee-model flat --fee-flat F` |
| Commission-free | `--fee-model zero` |

  Add `--min-order M` if the platform has a minimum order, and `--fx-pct F` for a currency-conversion cost.
- **FX is charged only when currency is actually converted:** when `--instrument-currency` (default USD) differs from the account currency (`--account-currency`, else the broker profile's `currency`). A USD account buying a USD stock pays no FX. The account currency comes from question B2. There is no exchange-rate model yet, so a cross-currency plan is research only (WATCHLIST); suggest holding USD in the trading account.
- **Units: every rate is a fraction.** `0.005` means 0.5%. The engine rejects a rate of 0.1 or more as a likely percent-vs-fraction mistake.
- **Different buy and sell charges:** a broker profile may carry a separate `sell` schedule, plus `fx_pct`.
- **Spread and slippage are separate** (`--friction-bps`, default 5 per side). A commission-free broker still has trading costs.
- Profiles are **user-provided** unless `verified_source` is set. The simple output prints "FEE SCHEDULE: USER-PROVIDED, NOT VERIFIED" on every plan until the profile is verified against the broker's published tariff.
- **Never edit `brokers.json` during a session.** To keep a new platform for next time, a maintainer copies a template, fills it in, and re-runs `run_checks.py`.
- Ticker availability and order types (limit, stop) on the user's platform are **UNVERIFIED** until the user confirms. Pass what they confirm as `--stop-orders yes|no|unknown`. If stop orders are unavailable, the user must accept a price alert at the stop and a manual sell (`--manual-stop-ack`); until then a short/medium plan can't be marked ready.
- PTPs are excluded (10% US withholding on gross proceeds, with exceptions). Grantor-trust metal ETFs (GLD, IAU, SLV, SIVR) are not PTPs; confirm each time.
- **Cash interest:** if uninvested cash earns interest or is swept into an interest-bearing account, say so. With the Shariah screen on, flag that this interest needs purification or a non-interest cash option.

## 3. Evidence labels

Every number and claim in the detailed output carries one label:

| Label | Meaning |
|---|---|
| **Verified** | From a source in the ledger that `sources_check.py` marked FRESH (section 8a), with source name, link, date and time |
| **User-provided** | Given by the user: fees, holdings, cash |
| **Assumption** | Model estimate: friction, gap %, support levels |
| **Calculated** | Output of a script |
| **Unavailable** | Could not be obtained; say what's missing |

## 4. Price data

Per ticker, WebFetch a quote page (Yahoo Finance, Nasdaq.com, stockanalysis.com) and record:
- price, timestamp and quote status
- day range and 52-week range
- 20/50/200-day moving averages
- ATR(14) or 14-day average range
- recent swing lows and highs
- next earnings date

For medium- and long-term ideas also record forward P/E, its 5-year average, analyst consensus target, number of analysts, and consensus EPS for the next two fiscal years. If a valuation input a target depends on is missing, label it **Unavailable** and give no target from it.

Quote status (`--quote-status`):

| Status | Meaning | Engine result |
|---|---|---|
| `live` | Last trade, at most **15 minutes** old by the system clock | Executable |
| `delayed` | Stated delay of 20 minutes or less (`--quote-delay-min`), and age at most delay + 15 minutes | Limit orders only; say the delay |
| `previous_close` or `unknown` | No reliable current price | WATCHLIST: levels are conditional, not executable |

Always pass `--quote-time`, `--quote-source` and `--market-price` (the last price from that same quote). Without them, or without a stated delay for a delayed quote, the engine returns WATCHLIST. Freshness is measured against the **system clock**, not against a date you pass, so an old quote can't be made "current" by choosing `--as-of`. Outside market hours or after a pause in the session, plans come back as WATCHLIST with the full conditional plan; get a fresh quote and re-run. A "live" label from a data site never makes an order ready on its own; the user's in-app check does (6d).

Never invent ATR, moving-average or swing levels without adequate price history. Label them **Unavailable** and give a watchlist entry instead.

## 5. Levels

**Entry**: a limit price and a zone.
- Short-term pullback: nearest support or 20-day MA, or price - 0.5 x ATR, whichever is closer to the current price.
- Short-term breakout: resistance + 0.25 x ATR, only with confirming volume or news.
- Long-term: near the 50-day MA or support. If price is more than 10% above the 50-day MA, use 2-3 tranches with a price each.
- Never more than 1% above the current price. **Enforced in code:** every entry/tranche must be at most 1% above `--market-price`, and the stop must be below it, or the result is NO TRADE.

**Stop**:
- Short-term: below nearest support - 1 x ATR. Hard stop.
- Medium-term: below the 50-day MA or a major swing low - 1 x ATR. Hard stop.
- Long-term: a price **review level** below the 200-day MA or a major swing low - 1 x ATR, plus a stated **fundamental exit condition** (e.g. two guidance cuts in a row, a thesis-breaking event). A review level is not an automatic sale.
- The engine rejects the idea if the stop is further below **any** entry or tranche price than:

| Horizon | Safe | Balanced | Aggressive |
|---|---|---|---|
| Short | 4% | 6% | 10% |
| Medium | 8% | 12% | 18% |
| Long (review level) | 12% | 18% | 25% |

**Targets**:
- Short-term: T1 = next resistance, or roughly 2R; T2 = next major resistance or about 3R.
- Medium-term: T1 = next major resistance or the analyst consensus target, whichever is lower; T2 = a stated valuation scenario.
- Long-term: T1 = the lower of the analyst consensus target and fair value from forward P/E vs its 5-year average; T2 = a stated bull-case valuation (EPS assumption x multiple). Include a review date.

## 6. Sizing and lifecycle (always run the engine; never compute by hand)

### 6a. Portfolio state (actual vs projected)

Write the user's current view to `STATE_IN.json` (format in the `portfolio_state.py` header): settled cash, whether the app already reserves cash for open orders, holdings, and working orders.

```
python3 "$SKILL_DIR/scripts/portfolio_state.py" --input STATE_IN.json --broker ID > ACTUAL.json
python3 "$SKILL_DIR/scripts/size_trade.py" ... --state ACTUAL.json > PLAN1.json
python3 "$SKILL_DIR/scripts/portfolio_state.py" --input STATE_IN.json --broker ID --plans PLAN1.json > PROJECTED1.json
python3 "$SKILL_DIR/scripts/size_trade.py" ... --state PROJECTED1.json > PLAN2.json
```

- **Actual** comes only from what the user's app shows. List each ticker once (combine lots: total shares, weighted average cost) and each working order once; duplicates are an error, because a repeated row would inflate the portfolio value and every limit computed from it. A recommendation never changes it; executed fills do, once the user reports them.
- **Projected** adds accepted plans as reserved orders, never as holdings. Each later idea is sized against the projected state.
- **Every working order states `"side": "buy"` or `"sell"` and a `"status"` of `open`, `partial`, `filled` or `cancelled`.** `shares` is a positive whole number and `filled_shares` a whole number between 0 and `shares`; `open` means nothing filled yet, `partial` means some but not all. Anything else is an error, and the state can't be used until it matches the app.
- **Sector weights in the state** follow the same rule as the engine: each between 0 and 1, summing to 1. Invalid weights are an error, never silently counted.
- **A stock or ETF with no sector data** (held or on order) is counted as `Unclassified`. The engine treats Unclassified money as worst case: it could all be in whichever sector a new buy adds to, so it reduces the room in every sector. Ask the user for the sector (Part D, one question) to free up that room.
- Order handling:
  - **Buy orders** reserve cash and add pending exposure and risk.
  - **Sell orders** reserve no cash and add no exposure. The shares stay in holdings, with their risk, until the sale executes; they're reported as `shares_reserved_for_sale`. Sell orders can't exceed the shares held (no short selling).
  - Filled orders are already in holdings, so they are not counted again.
  - Cancelled orders release their cash.
  - A partial fill reserves only the remaining shares plus their own commission.
  - If the app already reserves cash for open orders, it is not subtracted twice.
- A holding whose level is at or above its current price is **BREACHED**. It blocks every new trade until the user reconciles it.
- After a fill, rebuild the state from the app (new average cost and shares), then re-run the engine on any remaining tranches.
- Cash model: `--cash` is settled cash after executed buys; `--committed` is unfilled orders only. Available = cash - committed - cash floor.

### 6b. Price trades (stocks, equity ETFs, metal trusts)

```
python3 "$SKILL_DIR/scripts/size_trade.py" --asset stock|etf|metal --ticker TICKER --isin ISIN --as-of YYYY-MM-DD \
  --profile safe|balanced|aggressive --horizon short|medium|long --state STATE.json [--related-tickers T2,T3] \
  --broker ID   (or --fee-model ... flags) \
  --quote-status live|delayed|previous_close|unknown --quote-time 2026-11-05T15:30:00-05:00 --quote-source SOURCE \
  [--quote-delay-min N] --market-price PX \
  --boycott-mode exclude|flag --boycott-result BOYCOTT.json [--accept-flagged] \
  --shariah-mode exclude|flag --shariah-result SCREEN.json [--accept-shariah-review] \
  --sources-check SOURCES_CHECK.json --next-earnings YYYY-MM-DD [--accept-earnings-gap] \
  --signals SIG_TICKER.json [--dividend-yield-pct Y --dividend-withholding-pct W] \
  --stop-orders yes|no|unknown [--manual-stop-ack] [--account-currency CUR] [--instrument-currency USD] \
  [--unquantified-loss-pct P] [--confirm-order "TICKER|limit|PRICE|SHARES"] \
  --entry E  (or --tranches "P1,P2,P3") --stop S --t1 T1 --t2 T2 \
  --sector-weights '{"Tech":1}' --budget AMOUNT [--friction-bps 5] [--gap-pct 5]
```

**Gates enforced in code** (any failure means NO TRADE):
- **Invalid inputs:** every number must be finite, and positive or non-negative as appropriate. A negative or zero price, a negative exposure, or a NaN stops the plan.
- **Sector weights:** each between 0 and 1, totalling 1. Put any unknown share under `"Unclassified"`. Names that differ only in case or spacing ("Technology", "technology ") are merged, so use the portfolio's existing sector names.
- **Asset type:** a ticker with company data in the ledger (earnings date, 10-Q/10-K, analyst consensus) can't be sized as `--asset metal` or `tbill`. Holdings and orders in the state must use `stock`, `etf`, `metal` or `tbill` exactly.
- **Screen results are re-checked at trade time:** expiry is recomputed from each result's own date (the stored `expires_on` is not trusted), the boycott evidence must be for the same asset type and ISIN, and validity is counted from the later of `--as-of` and today.
- **Plan files:** a plan is only used downstream (state, output, journal) if it is a genuine TRADE: no reasons and placeable. An edited verdict is refused. Pass each plan once.
- **Prices under 1.00 USD** are not supported (sub-penny ticks): NO TRADE.
- **One-cent grid:** every entry, tranche, stop, target and T-bill limit must be a whole number of cents (100.25, not 100.004). Off-grid prices are NO TRADE and are never rounded for you. Produce levels in cents.
- **Unclassified sector money is worst case:** the portfolio's Unclassified exposure, and the new instrument's own Unclassified weight, are counted against every sector the buy touches (`(any other sector)` covers sectors not yet held).
- **Stop distance:** as in section 5, checked against every entry.
- **Screens are mandatory (v4.8):** `--boycott-mode` and `--shariah-mode` must be `exclude` or `flag`; `off` is NO TRADE. Both need their result file in either mode (flag mode only decides whether an EXCLUDED name blocks or is shown with a label). `--isin` is required for stocks and ETFs.
- **Sources are mandatory (v4.8):** `--sources-check` (section 8a). The engine re-runs the check on the recorded ledger against the system clock, so data that went stale since the check is caught. Any of these gives WATCHLIST: no check, any ledger entry not FRESH, a missing source category for this ticker (below), fewer than 2 fresh news items plus 1 fresh official release or market series, or a `--market-price`/`--quote-time` that is not a quote recorded in the ledger.

  | Asset / horizon | Fresh source categories needed for this ticker |
  |---|---|
  | Stock, short | quote, price_history, earnings_date |
  | Stock, medium / long | quote, price_history, earnings_date, fundamentals, consensus |
  | ETF | quote, price_history, fund_holdings |
  | Metal trust | quote, price_history |
  | T-bill ETF | quote |
- **Boycott, in exclude mode:** needs `--boycott-result`, a file written by `boycott_screen.py` (section 7) for this ticker, asset type and ISIN, made within the last 30 days. The status is recomputed from the recorded evidence, and a typed status is not accepted.
  - EXCLUDED or UNVERIFIED blocks the trade.
  - FLAGGED needs the user's explicit OK (`--accept-flagged`).
- **Shariah, in exclude mode:** needs `--shariah-result`, a file written by `shariah_screen.py` for this ticker. The engine rejects the file if:
  - it is for a different ticker, a different asset type (an ETF certificate cannot clear a stock), or a different ISIN
  - it has expired (92 days after its `as_of`)
  - it was made under different rules (rule fingerprint mismatch) or a historical methodology
  - it is missing identity or provenance
  - **re-running the screen from the recorded inputs gives a different verdict**

  - its market-cap date is now more than 31 days old, or its certificate is now more than 400 days old (both re-checked at trade time, not only when the file was made)

  This is a consistency check, not tamper-proofing: it catches an edited verdict, but not a file whose inputs were also changed. A typed verdict is not accepted. EXCLUDED or UNVERIFIED blocks the trade, and REQUIRES_ACCEPTANCE needs `--accept-shariah-review`.
- **Earnings (stocks):** record the date in the ledger (`earnings_date` entry with `--event-date`); the engine takes the **earliest** fresh recorded date (sources that disagree get a warning), and a `--next-earnings` that differs from it is NO TRADE. Missing or already past gives WATCHLIST. A short-term trade whose window (21 calendar days) contains earnings is NO TRADE unless the user explicitly accepts the gap risk (`--accept-earnings-gap`); medium-term earnings within 8 weeks are a warning, and the gap % should cover the stock's usual earnings move.
- **Signals (8b):** `--signals` from `signals.py` for this ticker. The file records its own price rows and the engine recomputes every signal from them, so an edited file (hint, dates, price) is NO TRADE; never edit it. Prices prices at most 4 days old, last close within 20% of `--market-price` (over 5% is a warning: check it is this ticker's split-adjusted file). AVOID is NO TRADE. CAUTION blocks short-term entries and is a warning for medium/long. Short-term entries need signals: no file, or UNKNOWN (too little history), gives WATCHLIST; for medium/long a missing file is a warning ("TREND: NOT CHECKED").
- **Fees vs profit:** the engine reports round-trip fees and spread as a % of the gross profit at T1 (`fee_check`). Above 25% is NO TRADE for short-term trades and a warning otherwise. On a 0.5%-per-order broker a round trip costs about 1%, so short-term trades need targets well above that; prefer medium/long horizons there.
- **Dividends after US tax:** pass the trailing yield and the user's US withholding rate (30% unless a US tax treaty applies to their residency; label it Verified only with a current IRS source). The plan shows the net yield and the yearly net amount; long-horizon names yielding 2% or more at 30% withholding get a warning pointing to low-dividend names or Irish-domiciled UCITS funds.
- **Flag mode is still screening.** Flag mode with no valid result file is NO TRADE ("screen not run"). With a valid file, an EXCLUDED or FLAGGED name is planned with its screen label printed, and the user decides.
- Unquantified risk without `--unquantified-loss-pct` blocks the trade (section 1).
- **Time and quotes** (checked against the system clock, same rule for every asset type), any failure gives WATCHLIST:
  - the NYSE regular session must be open now (weekends, holidays, before 09:30 and after the close, including 1:00 p.m. early closes, New York time), the holiday list must cover this year, and the quote must be from today's session (a pre-open quote is not executable after the open)
  - `--as-of` must be today (within one day of the clock's UTC date)
  - `--quote-time` is ISO 8601 with a UTC offset and not more than 5 minutes in the future
  - live at most 15 minutes old; delayed needs a stated delay of 20 minutes or less and at most delay + 15 minutes of age
  - `--market-price` from the same quote is present
  - `--now` is **replay only** (research and backtests): a replay is never executable
- **Market price vs levels:** an entry more than 1% above `--market-price`, or a market price at or below the stop, gives NO TRADE.
- **Order confirmation:** plans are limit orders, so only a limit confirmation with the same ticker, price and shares counts. For short/medium horizons it is marked ready only when the hard stop can be handled: `--stop-orders yes`, or `--stop-orders no` with `--manual-stop-ack`.

**Inputs and outputs:**
- **Sector data:** a stock passes `{"Sector": 1}`; an ETF passes its published sector weights. Every sector the purchase touches is checked.
- **Tranches:** the full position is sized across all prices, and each order is checked against its own commission and the minimum order. The engine returns `cash_for_first_order` and `commit_for_later_tranches`.
- `--gap-pct`: about 1 x ATR as a % of price (minimum 3), higher before earnings. For long-term ideas, use the worst one-week drop of the past year (minimum 10).
- **What the engine returns:**
  - per-order shares and fees
  - fee-adjusted breakeven
  - downside by bucket and a gap scenario
  - net reward:risk at T1, at T2 and for the half/half exit plan
  - the stop rule after T1 (never lower; optional raise to the remaining shares' breakeven, which includes all exit costs, is rounded up to the cent, and is verified to net zero or better)
  - projected sector exposure
  - portfolio risk after the trade

### 6c. T-bill ETFs (cash management, not a price trade)

```
python3 "$SKILL_DIR/scripts/size_trade.py" --asset tbill --ticker TICKER --profile P --state STATE.json \
  --broker ID --quote-status S --quote-time ISO --quote-source SRC --as-of DATE \
  --boycott-mode exclude|flag --boycott-result BOYCOTT.json --shariah-mode exclude|flag --sources-check SOURCES_CHECK.json \
  --amount $ --price PX --market-price PX --yield-pct YIELD --yield-basis sec|gross --expense-ratio-pct ER \
  --duration-yrs D --spread-bps 2 --hold-months M
```

- **Market price:** pass `--market-price` from the same quote. Missing gives WATCHLIST; a `--price` more than 1% above it is NO TRADE. The price must be on the cent grid.
- There is no stop for a T-bill fund; the confirmation text says so and points to the rate-shock figure instead.
- Shariah screen: in exclude mode NO TRADE (interest-bearing; keep cash); in flag mode allowed with a non-compliance warning (no result file needed: a T-bill fund is interest by definition). `off` is refused.
- The 30-day SEC yield is already net of fund expenses, so use `--yield-basis sec`. The engine does not deduct the expense ratio again.
- Income is an **estimate**, not a forward promise.
- The engine reports net return after both commissions and the spread, the days needed just to cover fees, and the loss from a 1-point rate rise. If fees exceed income, the result is NO TRADE.

### 6d. Using results

- **Be the analyst (v5.2).** The user comes for a market read, not only for a sized order. Every session, after the news scan, write `ANALYSIS.json` and pass `--analysis ANALYSIS.json` to `render_dashboard.py`; give the same read in the chat in a few plain lines. It has:
  - `mood`: `RISK-ON`, `NEUTRAL` or `RISK-OFF`, and `one_line` saying why.
  - `facts`: 3 to 6 things that happened, each `{what, means, source, url, date}`. Every fact must be in the source ledger; `date` is `YYYY-MM-DD`. The renderer drops, and counts on the page, any fact with no https link, an unreadable date, or a date more than 7 days old. Read actual vs expected (section 8), not headlines.
  - `favours` and `against`: the **kinds** of thing these conditions help or hurt, each with the reason (`{kind, why}`). Kinds only (gold, cash, broad funds, large steady companies, fast-growing companies), never a promise about a named stock.
  - `scenarios`: 2 to 3 "if this happens, then likely that, watch this date".
  - `change_my_mind`: what would make you change the read.
  Take a clear position and say how sure you are; "it could go either way" with no lean is not analysis. Always give the other side. Never promise a result, and say once that this is your reading, not licensed advice. The engine still decides whether any order is allowed: the read explains, it never overrides a gate.
- **Money plan for the whole amount (v5.2).** When the user gives a total to invest, asks "when and what should I invest in", or the amount is bigger than one position may hold, run `money_plan.py --state ACTUAL.json --profile P [--amount USD] --steps N --every-days D > MONEY_PLAN.json` and pass `--money-plan MONEY_PLAN.json` to `render_dashboard.py`. It gives the safety cash to keep, the dated steps (in the user's time zone), the most money allowed per kind of thing, and anything to fix first. It names **no stock** and promises nothing: each step means "run the skill that day", and the names come from that day's fresh prices and checks. Say plainly that steps spread the timing risk and do not make a profit more likely. Never write such a plan by hand, and never fill a step with a ticker in advance.
- **Honest odds (v5.1).** Every sized plan carries `needed_win_rate_pct`: of 100 trades like it, how many must reach the targets just to break even if the rest end at the stop. The renderers print it with "nobody can promise that". Never soften or drop it, and never say or imply that a plan will make money.
- **Is it making money? (v5.1).** Every session run `journal.py report --journal JOURNAL.json [--benchmark FUND.csv] --json > REPORT.json` (when a journal exists) and pass `--journal REPORT.json` to `render_dashboard.py`. The page shows the result in plain words: no record yet, too few trades to know, not working, behind just holding the fund, or working so far. With no journal the page says there is no record and asks the user to report fills.
- **"It passes at X or lower" (v5.1).** When the only thing wrong with a plan is that the profit is too small for the risk, the engine returns `buy_at_or_below`: the highest entry price, with the same stop and targets, at which the plan passes every gate (each candidate price is run through the full engine). The renderers print it as the fix. Never work out such a price yourself, and re-run the engine at that price with a fresh quote before calling it a plan.
- Use the engine's numbers verbatim (label **Calculated**). On NO TRADE, say why; never adjust levels to force a pass. An engine error means NO TRADE.
- **TRADE is provisional** until the user checks the exact order in their app: ticker, order type, limit price and shares, with the live quote inside the entry zone, and whether the app accepts a stop order for it. Then re-run with a fresh quote, `--confirm-order "TICKER|limit|PRICE|SHARES"` and `--stop-orders yes|no` (plus `--manual-stop-ack` if they accept a manual stop). It is marked ready only if all four order fields match the first order and the stop can be handled. Old confirmations and old quotes are never reused.
- **WATCHLIST with levels** is a conditional plan: show it (the simple output prints "IF READY LATER, PLAN IS"), and tell the user what to refresh.
- No limit fill or stop execution is guaranteed.
- **After T1, never lower the stop.** Keep it at least at the original level (`stop_after_t1.keep_at_least`). The engine also gives `optional_raise_to`, the fee-adjusted breakeven of the remaining shares. Raising to it is optional and should fit the thesis. `whole_trade_breakeven_after_t1` is information only and is never a stop.
- Review timing: short-term at 15 trading days if T1 isn't reached; medium-term at 8 weeks. Reviews, not automatic sales.
- Short-term trades are not held through earnings unless the user explicitly accepts the gap risk.

## 7. Boycott screen (mandatory: every idea, every session)

**Depth (v5.3):** the default is the quick screen in the fast path (rule 6b): AFSC, BDS and Who Profits, evidence marked `"depth": "quick"`. The steps below are the **full** screen (all five sources), used when the user asks for it.

Screens out companies complicit with Israel. The status is **computed by `boycott_screen.py` from source-by-source evidence**, never typed in. The evidence file is a structured record of your research, not independent verification, so be accurate.

1. **Resolve identity**: legal name, ticker, ISIN, share classes, parent company and major subsidiaries. Screen all of them, and set `identity_resolved` true only when that is done.
2. **Check all five sources fresh.** For each, record the finding (`match`, `no_match` or `unreachable`), the date checked and the https URL:

| Key | Source | Where |
|---|---|---|
| `ohchr` | UN OHCHR database of businesses in settlements | ohchr.org/en/business/bhr-database. Latest verified: A/HRC/63/20, 25 Sep 2026, 214 enterprises from 11 countries (200 "contributing", 14 "directly linked"). Record `list_version` and `involvement`. Recheck for a newer update every session. |
| `bds` | BDS targets and divestment guidance | bdsmovement.net/get-involved/what-to-boycott |
| `afsc` | AFSC Investigate | investigate.afsc.org |
| `whoprofits` | Who Profits | whoprofits.org |
| `sec` | SEC filings | sec.gov EDGAR; also record `israel_hq` and `material_israel_ops` as true or false |

3. **Write the evidence and run the screen** (the evidence format is in the script header):

```
python3 "$SKILL_DIR/scripts/boycott_screen.py" --evidence EVIDENCE.json --as-of YYYY-MM-DD \
  --strictness strict|moderate --out BOYCOTT_TICKER.json
```

4. **How the status is computed:**

| Status | STRICT rule (default) |
|---|---|
| EXCLUDED | Any OHCHR, BDS, AFSC or Who Profits match, or Israel-headquartered. ETFs: any excluded weight. |
| FLAGGED | Material Israeli operations per filings. ETFs: flagged weight. |
| REVIEWED_NO_MATCH | All five sources checked within 30 days, identity resolved, nothing found |
| UNVERIFIED | Any source missing, unreachable, undated, older than 30 days or dated in the future; identity unresolved; ETF holdings not 100% screened |

   In MODERATE strictness, AFSC and Who Profits matches are FLAGGED instead of EXCLUDED, and an ETF's excluded weight up to 5% is FLAGGED. Absence from a list is "reviewed, no match", never "clean".
5. **Equity ETFs:** start with AFSC's own fund screen, `https://investigate.afsc.org/fund-search?keyword=TICKER&strict=0` (it looks through the fund's holdings: red = owns BDS divestment-shortlist companies, with the shortlist and total counts). Then check the holdings against the full Who Profits list (fetch all `/index.php/companies?page=N` pages in one in-page script), the BDS targets and the OHCHR list. Record it all, then screen the full holdings file and record `screened_weight_pct`, `excluded_weight_pct` and `flagged_weight_pct`. Each is a percentage from 0 to 100; screened must be 100, and excluded + flagged can't exceed it. Anything else is UNVERIFIED. If the excluded weight is material, offer a basket of screened individual names instead.
6. **Metal trusts and T-bill ETFs:** screen the sponsor, trustee, custodian and issuer. Ask the user once how to treat US government bonds (Part D).
7. Pass the result to `size_trade.py` with `--boycott-result`. It expires after 30 days.

## 7b. Shariah screen (mandatory: every idea, every session)

**Depth (v5.3):** the default is the quick screen in the fast path (rule 6b): one screening provider's published verdict, copied. The steps below are the **full** screen (the skill's own ratios from SEC filings), used when the user asks for it or the provider has no page for the name. A full-screen PASS built from `browser_facts.js` numbers alone is a first pass: read the filing before relying on it.

A screen against a published methodology, not a fatwa.

**Rules live only in `scripts/methodologies.json`.** Each entry carries:
- provider and document version
- effective date and source URL
- the date it was verified
- exact ratios and comparators
- entry, threshold and exit-buffer values, and any multi-period rule
- the purification method

`run_checks.py` validates its schema. Historical versions are kept for comparison only, and results made under them are rejected for decisions.

**Each session, before screening:**
1. Open the selected provider's official methodology page and note the document version. Pass it as `--source-version-seen`, with today's date as `--as-of`.
2. The result is **UNVERIFIED** if:
   - the version is neither the registry version nor a listed `equivalent_versions` entry. An alternate edition is listed as equivalent only after a maintainer has compared every rule and recorded the comparison in the entry's `evidence`. Titles alone never establish equivalence.
   - the entry is past the registry's maximum age
   - the entry is disabled

   If the page can't be reached, a registry entry within its age limit may be used; the result is marked `source_rechecked_this_session: false`.
3. **Never edit the registry or any script during a session.** Report the mismatch. A maintainer adds the new version (or marks an identical one as equivalent) from the source document, then re-runs `run_checks.py`.

Reference only, verified 2026-11-05 (the registry is authoritative):

| Methodology | Version | Denominator | Ratios |
|---|---|---|---|
| AAOIFI SS-21 | SS-21 | Market cap | Interest-bearing debt <= 30%; interest-taking deposits <= 30%; prohibited income <= 5% of total income |
| MSCI Islamic Index Series | May 2025 | Total assets | Debt and cash + interest-bearing securities: entry 30%, threshold 33.33%, exit 35%; receivables + cash: entry 46%, threshold 70% |
| MSCI Islamic M-Series | May 2025 | 36-month average market cap | Debt and cash: entry 30%, threshold 33.33%; receivables + cash: entry 46%, threshold 49% |
| S&P Shariah | Oct 2026 (effective 2026-09-21) | 36-month average market value of equity | Debt < 30%; cash & deposits + interest-bearing securities < 30%; 2-point buffer, 3 periods |
| DJIM | Sep 2026 (effective 2026-09-18) | 24-month average market cap | Interest-bearing debt < 30%; cash + interest-bearing securities < 30%; 2-point buffer, 3 periods |

**Screen each stock and write the result to a file:**

```
python3 "$SKILL_DIR/scripts/shariah_screen.py" --asset stock --ticker TICKER --isin ISIN --entity "LEGAL NAME" \
  --methodology aaoifi|msci|msci-m|sp|djim --as-of YYYY-MM-DD --source-version-seen "VERSION SEEN" \
  --business permissible|mixed|prohibited --period PERIOD --data-published YYYY-MM-DD \
  [--existing-holding] [--previous-index-status compliant|noncompliant|unknown] [--consecutive-periods N] \
  --market-cap MC --total-assets TA [--avg-market-cap-24m A24] [--avg-market-cap-36m A36] \
  --interest-debt D --total-debt TD --cash C --interest-deposits ID --interest-securities IS \
  --receivables R --nonpermissible-income NPI --total-income TI --market-cap-date YYYY-MM-DD \
  [--shares-outstanding SO --shares-held N --held-at-period-end yes|no] \
  [--dividend-per-share DPS --dividends-count K] [--fund-purifies yes|no|unknown] \
  --out SCREEN_TICKER.json
```

- Collect each balance-sheet item separately from the latest 10-Q/10-K on SEC EDGAR. Missing required data means UNVERIFIED; nothing is estimated.
- **`--market-cap-date` is required** for every methodology whose ratios use market cap (AAOIFI, MSCI M-Series, S&P, DJIM): the date the market cap was observed (for an average, the end of its window). It must be at most 31 days old when screened, and is re-checked when the trade is sized; refresh the market cap and re-screen if it has aged out. MSCI Index Series uses total assets and doesn't need it.
- The file carries provenance:
  - ticker, ISIN and legal entity
  - methodology version and rule fingerprint
  - fiscal period and filing date
  - `as_of` and `expires_on`
  - the four outcomes
  - the recorded inputs, so the verdict can be recomputed when it is used

  Pass it to `size_trade.py` with `--shariah-result`.

**Four separate outcomes:**

| Outcome | Values |
|---|---|
| `screening_result` | PASS / FAIL / BORDERLINE / INSUFFICIENT_DATA |
| `index_entry` | ELIGIBLE / INELIGIBLE / UNKNOWN / not applicable |
| `retention` (existing holdings) | RETAINED / REMOVAL_CONDITION_MET / UNKNOWN / not applicable |
| `policy_decision` | PERMITTED / REQUIRES_ACCEPTANCE / EXCLUDED / UNVERIFIED |

- Failing an index **entry buffer** alone is not a religious prohibition: it gives REQUIRES_ACCEPTANCE, not EXCLUDED.
- The 10% near-limit margin is an **internal conservative policy** (`--internal-margin`, 0 disables it), reported under `internal_policy_flags`.
- For S&P and DJIM, a ratio inside the 2-point buffer depends on the index's previous status and consecutive periods. If those are unknown, the result is BORDERLINE or UNKNOWN, never PASS.

**Purification** (USD, period and method; never estimated; always rounded **up** to the cent so charity is never underpaid):
- **AAOIFI SS-21** (clauses 3/4/6/1, /2, /4): the company's prohibited income for the period / shares outstanding x shares held. Owed by whoever holds at period end, whether or not profits are distributed, and not owed if sold before the period ends.
- **Index methodologies**: dividends received x non-permissible income / total income.
- If the fund already purifies (`--fund-purifies yes`), don't purify again. Missing inputs mean UNAVAILABLE.

**Other products:**
- **Physical gold/silver trusts:** run `shariah_screen.py --asset metal --metal-structure physical` (futures or leveraged products: `--metal-structure futures|leveraged`, which fails), with `--allocated`, `--ownership-rights`, `--spot-settlement` and `--no-lending` each `yes|no|unknown`, plus `--certifier`, `--certificate-date` and `--certificate-url` when there is a certificate. Without `--metal-structure` the result is UNVERIFIED. Allocation alone is not enough. Verify from the fund documents:
  - allocated bars
  - investor ownership rights
  - spot settlement / constructive possession
  - no lending of the metal

  Any unknown means UNVERIFIED, and any no means EXCLUDED. All verified plus a current certificate means PERMITTED; all verified without one means REQUIRES_ACCEPTANCE. A certificate that is supplied but undated, future-dated, older than 400 days or without an https link is UNVERIFIED. Futures and leveraged products are EXCLUDED. Buy with full cash only.
- **Shariah-certified equity ETFs:** `--certifier`, `--certificate-date` and `--certificate-url` (https link to the certificate or the fund page stating it) are required. The date must not be after `--as-of` and must be at most 400 days old, checked again at trade time. Certification does not cover the boycott screen.
- **T-bill / Treasury ETFs:** EXCLUDED (interest).

Recheck every holding each quarter after earnings, and flag changes.

## 8. News and data sources

Search fresh every run; never use remembered prices or rates. Show the observation date and the publication date for every data point. Every source you use goes in the ledger (8a); the registry `scripts/sources.json` is the authority on which sources count for which data.

**Most accurate source first** (the registry tiers; when sources disagree, the higher tier wins):

| Tier | What | Examples |
|---|---|---|
| 1, official / primary | The regulator, statistics agency, central bank, exchange, fund issuer, or the company's own SEC filing | SEC EDGAR, Nasdaq, NYSE, Cboe, Federal Reserve, BLS, BEA, Treasury, FRED, CME FedWatch, EIA, WGC, iShares/SPDR/Vanguard |
| 2, wire / major press | Fast and edited, but a report about the fact | Reuters, AP, CNBC, BBC, MarketWatch |
| 3, data site | Convenient copies of tier-1 data | Yahoo Finance, Stooq, StockAnalysis, Investing.com, Morningstar |

Rules (from practice; also how the open-source trader-skill pack treats SEC and news data):
- **Filed numbers first.** Revenue, EPS, debt, cash, receivables and income come only from the 10-Q/10-K on SEC EDGAR (the `fundamentals` category accepts nothing else). Press releases and data sites are context.
- **Check that the filing is the latest one.** Open the company's EDGAR filing list the same day (`latest_filing_checked_at`). SEC's XBRL "company facts" API can lag a new filing: if the newest 10-Q is later than the newest quarter in the facts, read the 10-Q itself.
- **Headlines are leads, not facts.** Open the story or the filing before reporting it. If an 8-K and a headline disagree, the 8-K is what the company told the SEC. A story you couldn't open is not a source.
- **Two sources for every price.** Read the exchange (Nasdaq/NYSE) plus a second quote site. If they differ by more than 0.5% the check returns CONFLICT; re-read both and trust the exchange.
- **Two outlets, or one official source, for every market-moving claim** (the check warns otherwise).
- **A scheduled release must be the latest.** Record each release's `next_release` date; once it has passed, the old number is STALE.

**Official and primary data (highest weight):**

| Category | Source |
|---|---|
| Fed decisions, minutes, speeches | federalreserve.gov press releases (RSS federalreserve.gov/feeds/press_all.xml); FOMC calendar |
| CPI, jobs, PPI | bls.gov/schedule/news_release (RSS bls.gov/feed/bls_latest.rss) |
| GDP, PCE | bea.gov/news/schedule |
| Yields and real yields | home.treasury.gov yield curve; FRED DFII10 |
| Dollar | FRED DTWEXBGS (Nominal Broad Dollar Index), the trend benchmark. ICE DXY is a different index: context only, never mixed into the score. |
| Rate expectations | CME FedWatch |
| Company events | SEC EDGAR 8-K feed; company investor-relations pages |
| Gold demand, central banks | gold.org Goldhub |
| Oil | eia.gov; opec.org |
| Volatility | cboe.com (VIX) |
| Consensus forecasts | investing.com/economic-calendar |

**World and financial news (speed and context; check numbers against the primary sources above):**

| # | Outlet | Where | Feed (may change; fall back to WebSearch) |
|---|---|---|---|
| 1 | BBC News: Business | bbc.com/news/business | feeds.bbci.co.uk/news/business/rss.xml |
| 2 | BBC News: World | bbc.com/news/world | feeds.bbci.co.uk/news/world/rss.xml |
| 3 | Reuters | reuters.com/markets, /world | none public; use WebSearch |
| 4 | Associated Press | apnews.com/hub/business | none public; use WebSearch |
| 5 | CNBC | cnbc.com/markets | cnbc.com/id/100003114/device/rss/rss.html |
| 6 | MarketWatch | marketwatch.com | feeds.marketwatch.com/marketwatch/topstories/ |
| 7 | Yahoo Finance | finance.yahoo.com/news | finance.yahoo.com/news/rssindex |
| 8 | Al Jazeera: Economy | aljazeera.com/economy | aljazeera.com/xml/rss/all.xml |
| 9 | The Guardian: Business | theguardian.com/business | theguardian.com/business/rss |

- **Readable sources only.** A source that can't be read (the site blocks automated readers, sits behind a paywall or needs a login) is not used and not cited: drop it and use another source for that fact. Never work around a block. If a source in this file stops being readable, say so in the output and tell the maintainer so it is removed.
- Prefer two independent outlets for any market-moving claim.

### 8a. Source ledger and freshness check (mandatory)

Add every data point to `LEDGER.json` with `ledger.py`, one command per source, right after you read it. It recognises the source from the URL, fills `observed_at` with now, and checks the entry immediately, so a wrong or stale source is fixed on the spot. Never hand-write ledger JSON.

```
python3 "$SKILL_DIR/scripts/ledger.py" add --ledger LEDGER.json --category quote --ticker TICKER \
  --url URL --value PRICE --observed-at QUOTE_TIME            # the quote's own time; reuse it as --quote-time
python3 "$SKILL_DIR/scripts/ledger.py" add --ledger LEDGER.json --category fundamentals --ticker TICKER --url SEC_URL \
  --published-at FILED --form 10-Q --period-end PERIOD --latest-filing-checked-at now
python3 "$SKILL_DIR/scripts/ledger.py" add --ledger LEDGER.json --category earnings_date --ticker TICKER --url URL \
  --event-date YYYY-MM-DD                                      # the earnings date itself
python3 "$SKILL_DIR/scripts/ledger.py" add --ledger LEDGER.json --category news --url URL \
  --published-at TIME --claim-id SHORT-ID --what "ONE-LINE CLAIM"
python3 "$SKILL_DIR/scripts/ledger.py" list  --ledger LEDGER.json                          # status of every entry
python3 "$SKILL_DIR/scripts/ledger.py" check --ledger LEDGER.json --out SOURCES_CHECK.json  # for size_trade.py
```

Re-adding the same page (same category, ticker and URL) replaces the old entry; `drop --id ID` removes one. Each `add` exits 1 with the problem when the entry is not FRESH. `ledger.py check` is the same check as `sources_check.py --ledger ... --out ...`.

| Category | Accepted sources (tier) | Fresh means |
|---|---|---|
| `quote` | Nasdaq, NYSE, Cboe (1); Reuters, CNBC, MarketWatch (2); Yahoo, Stooq, StockAnalysis (3) | read <= 15 min ago (+ stated delay, max 20); two sources within 0.5% |
| `price_history` (MAs, ATR, swings, 52-week) | Nasdaq, NYSE, MarketWatch, Yahoo, Stooq, StockAnalysis, Investing, Morningstar | read today; history includes the latest session (<= 4 days) |
| `earnings_date` | SEC, Nasdaq, NYSE, Reuters, Yahoo, StockAnalysis, MarketWatch, Investing | read today; `event_date` recorded and not yet passed |
| `fundamentals` | **SEC EDGAR only** | filed <= 135 days ago; EDGAR filing list re-checked within 24 h |
| `fund_holdings` (ETF holdings, sector weights) | fund issuer, SEC | read today; published <= 35 days ago |
| `consensus` | StockAnalysis, Yahoo, MarketWatch, Investing, Morningstar, Nasdaq, Reuters, CNBC | read today |
| `macro_release` (FOMC, CPI, jobs, PPI, GDP, PCE, WGC) | Fed, BLS, BEA, Treasury, EIA, WGC (official only) | read today; `next_release` not yet passed |
| `market_series` (yields, DFII10, DTWEXBGS, VIX, FedWatch, oil) | Treasury, FRED, Cboe, CME, EIA, Fed | read today; data <= 5 days old |
| `release_consensus` | Investing, Reuters, MarketWatch, CNBC | read within 7 days |
| `news` | official sources, tier-2 outlets, Yahoo | read today; published <= 7 days ago; 2 outlets or 1 official per `claim_id` |

The check also rejects a read time without a clock time (`observed_at` and `latest_filing_checked_at` need a time with a UTC offset), a URL that is not on the named source's own site, an unregistered source, a source not accepted for that category, and any date in the future. `ok` is true only if **every** entry is FRESH: refresh or delete the rest, and never report a number whose entry failed. Pass `SOURCES_CHECK.json` to every `size_trade.py` call. Never edit `sources.json` during a session; a maintainer adds a source and re-runs `run_checks.py`.

### 8b. Signals (long-only, from *151 Trading Strategies*)

`signals.py` computes, from real daily prices you recorded as `price_history`, the long-only signals of Kakushadze & Serur, *151 Trading Strategies* (2018, SSRN 3247865):

```
python3 "$SKILL_DIR/scripts/signals.py" one --ticker TICKER --prices TICKER.csv --market MARKETFUND.csv [--eps "E0,E1,...,E11"] --out SIG_TICKER.json
python3 "$SKILL_DIR/scripts/signals.py" rank --signals SIG_A.json SIG_B.json ...
```

| Signal | Paper section | Used for |
|---|---|---|
| 12-1 month price momentum (and risk-adjusted) | 3.1 | ranking candidates |
| SUE earnings momentum (12 quarters of diluted EPS from SEC, newest first) | 3.2 | ranking; negative SUE is flagged |
| 126-day historical volatility | 3.4 | ranking (lower ranks better) |
| Demeaned rank average of the factors | 3.6 | the "find ideas" order |
| MA3 > MA10 > MA21 | 3.13 | confirms a short-term breakout entry |
| Pivot point support / resistance | 3.14 | candidate entry and T1 levels |
| Donchian 20-day channel, 20-day swing low/high, ATR(14), 20/50/200-day MAs | 3.15 + section 5 | entry, stop and target inputs (label **Calculated**) |
| Trend filter: price > 200-day MA | 4.1.1 | `hint`: below it is CAUTION; below it with negative 12-1 momentum is **AVOID** |
| Dual momentum: broad market fund > its 200-day MA and 12-month return > 0 | 4.1.2 | market DOWN: no new short-term equity entries; favour gold or cash (not Treasuries when the Shariah screen excludes interest) |

- For the market fund, use a broad fund that passes both screens when possible (for example a Shariah-screened US equity ETF); say which one you used.
- **AVOID** names are not planned; pass their signal files to `render_simple.py --signals` so each gets a NO BUY with the reason. CAUTION names can be planned only on medium/long horizons, and the caution goes in the "why" line.
- Missing history is **Unavailable**, never estimated: signals with too little data come back `UNKNOWN`.
- The paper warns that single-stock technical rules have weak theoretical support and that momentum fades with longer holds. These signals rank and filter; they never override the screens, the sources check, fees or limits. Shorting, options, leverage and pairs trading from the paper are out of scope.

**Expectations-based reading.** For every material release or event:

actual -> consensus -> surprise (size and sign) -> observed reaction in stocks, yields, dollar, gold -> confidence (high/medium/low) -> portfolio implication.

Never use fixed "rate cut = stocks up" mappings. Tendencies only, always overridden by the observed reaction:
- dovish surprises tend to lift stocks and gold
- hawkish surprises tend to lift yields and the dollar
- geopolitical shocks tend to favour gold
- a recession-driven cut can coincide with falling stocks

## 8c. Trade journal (is it working?)

Every plan the user acts on goes in the journal, with the fills **as the app shows them** (shares, price, fee charged, date), never the plan's numbers. Paper trades are marked `--paper`.

```
python3 "$SKILL_DIR/scripts/journal.py" open   --journal JOURNAL.json --plan PLAN1.json [--paper]
python3 "$SKILL_DIR/scripts/journal.py" fill   --journal JOURNAL.json --id ID --side buy|sell --shares N --price P --fee F --date YYYY-MM-DD
python3 "$SKILL_DIR/scripts/journal.py" purify --journal JOURNAL.json --id ID --amount USD
python3 "$SKILL_DIR/scripts/journal.py" report --journal JOURNAL.json [--benchmark BENCH.csv] [--paper|--real]
python3 "$SKILL_DIR/scripts/journal.py" reconcile --journal JOURNAL.json --state STATE_IN.json
```

- **Reconcile before every report** (treasury control): open real positions in the journal must match the shares the app shows. Any BREAK means a fill or a position is missing from the journal; record it before reading the results.
- Each journal entry keeps an audit trail: a SHA-256 fingerprint of the plan as sized, the broker, whether the fee schedule was verified, the placement status and when it was recorded.

- The report gives win rate, average result in R (multiples of the planned loss) and in dollars, total after fees and charity, profit factor, worst drop, stops hit, average hold, and, with a benchmark file (daily closes of a fund that passes both screens), the same money held in that fund over each trade's own days.
- Under 20 closed trades the verdict is "too few to judge". Say so plainly, and never call the skill profitable from a handful of trades.
- In a "review my holdings" session, ask the user for fills since the last session, record them, then show the report.
- If the verdict is "not working" or "behind the benchmark", say it plainly and suggest holding the benchmark fund instead of trading.

## 9. Gold / silver signal

Score six factors +1, 0 or -1, each with a cited source:

| Factor | +1 | -1 |
|---|---|---|
| Fed path vs expectations | Dovish surprise | Hawkish surprise |
| Real yields, DFII10, 4 weeks | Falling | Rising |
| Dollar, DTWEXBGS, 4 weeks | Weakening | Strengthening |
| Geopolitical / political shock | Escalation | De-escalation |
| Central-bank buying (WGC) | Strong | Weak |
| Equity stress | VIX above 25, or S&P 500 down 10% | VIX below 15 |

A factor that can't be verified is **Unknown**, never 0.

| Score | Action |
|---|---|
| Score >= +3 | Consider the top of the metals range. Silver only if the gold/silver ratio is above 80. |
| Score +1 to +2 | Consider the middle of the range. |
| Score <= 0 | Consider the bottom of the range. No new short-term metal entries. |

- Confidence: high when no factor is Unknown, medium with 1-2 Unknown, low with 3 or more. A low-confidence signal moves nothing.
- Never chase a one-day move of 3% or more.
- The signal never overrides fees, limits or a contradictory thesis.
- Metal ETFs go through sections 5-6 with `--asset metal`.

## 10. Tax and cross-border checks (based on the user's tax residency)

Flag each one; label it **Verified** only with a current source.
- US dividend withholding for non-resident aliens: generally 30% unless a treaty rate applies. Check the user's country.
- US estate tax for non-resident non-citizens: 60,000 USD is generally the filing threshold for US-situs assets. Verify current rules.
- Fund domicile: compare US-domiciled ETFs with Irish-domiciled UCITS equivalents (withholding, estate exposure, availability on the user's platform, FX, fees).
- FX cost if the account currency isn't USD.

## 11. Workflow

1. Engine check (0a); collect answers one question at a time (0b, Parts A–C).
2. Build the actual state (6a). If `reconciliation_required`, report the breached holdings first and stop new trades.
3. News scan (8-12 searches) -> regime (Risk-on / Neutral / Risk-off) with 3 cited facts, plus events in the next 14 days. Record every source in the ledger as you go (8a).
4. Candidates matching what the user wants to buy:
   - "Find ideas": a scan fitted to horizon and risk.
   - Tickers: the user's list.
   - Theme: the best names in it.
   - "Review": current holdings.
5. Boycott and Shariah screens for **every** candidate (sections 7, 7b). Keep the dropped names and their reasons for the NO BUY list.
6. Price data (section 4) from two quote sources, price history, and the ticker's other categories into the ledger; run `sources_check.py` (8a). Refresh anything not FRESH.
7. Signals (8b): rank the candidates; AVOID names go to the NO BUY list with their reason.
8. Levels (section 5), then the engine (6b or 6c) with `--sources-check`.
9. After each accepted idea, rebuild the **projected** state and size the next one against it. Stop when the amount, cash floor or risk limits are used up. It is fine to leave money in cash.
10. Gold/silver signal.
11. Re-run `sources_check.py` right before the output if more than a few minutes passed, then output (section 12): simple text, then the dashboard.
12. After the user places an order, offer to record it: `journal.py open` now, `fill` once they report the fill (Part D), then `journal.py reconcile`.

## 12. Output

### Order of the output (v5.0)

Text and dashboard follow the same order, built by the renderers from the engine files (never by hand):

1. **Colour key.** 🟢 good / can win · 🟡 wait / your call · 🔴 stop / can lose. On the dashboard blue is plain info, and every colour also carries a sign (`+ ! x i`) so it reads without colour.
2. **TODAY** (dashboard): one coloured answer: BUY X, YOUR CALL, or NO BUY TODAY. KEEP CASH (with the one-line why).
3. **DO THIS NOW**: numbered app steps for the recommended option. With no buy: keep cash, the closest idea and what would unblock it, when the US market next opens in the user's time, and what to watch. Then **ALSO FIX IN YOUR APP** (dashboard): a holding with no stop or past its stop, from the user's own state.
4. **YOUR CHOICES**: every idea as a lettered option with PAY / CAN LOSE / CAN WIN from the engine, its boycott and halal labels, plus KEEP CASH. One BEST PICK: a buy that is clean on both screens and passes the risk rules, else cash. In flag mode a failing name is marked YOUR CALL and is never the best pick.
5. **CHECKS**: boycott and halal result per idea with the proof (which list and link; methodology and the failed ratio).
6. Folded away under "More, if you want it": the user's money and holdings, the full numbers per idea, and sources. A no-buy page must still fit on one screen above the fold.

### Simple (default): plain "caveman" style

Short lines, short words, no jargon. Every number comes from the engine.

1. Write a **one-line** market summary, gold/silver line and events line yourself, in the same style ("MARKET: CALM. FED WAIT.", "GOLD: WAIT.", "WATCH: JOBS FRI. CPI TUE.").
2. Render the trade lines with the script, which copies the engine's numbers without recomputing them:

```
python3 "$SKILL_DIR/scripts/render_simple.py" --plans PLAN1.json PLAN2.json [--signals SIG_*.json] \
  --market "CALM. FED WAIT." --metals "WAIT." --events "JOBS FRI. CPI TUE." [--skipped "XYZ|why dropped"] --tz ZONE
```

Pass a plan file for **every** ticker you screened (tickers dropped before screening go in `--skipped`), including the ones that failed a screen, so each NO BUY prints. Every NO BUY and WAIT prints every reason: a plain `WHY:` line, the facts behind it (which boycott list, which Shariah ratio, which source is stale), a `FIX:` line, and the engine's full text. A NO BUY also prints `ALSO NEEDED:` lines for what would still be missing once the blocking reasons are fixed (sources, earnings date, signals, a live price). Never shorten or drop a reason.

Example (real engine output from the v4.8 tests: 10,000 USD account, balanced, medium hold, Bank al Etihad fees, AAOIFI and boycott screens in exclude mode, test fixtures for the company and sources):

```
RISK: BALANCED. HOLD: MEDIUM.
NYSE: OPEN. CLOSES 16:00 NEW YORK TIME.

BUY ABC
  PRICE 100.00 (LIMIT)  SHARES 9  COST 904.50 USD
  STOP 90.00  PLANNED LOSS AT STOP 98.55 USD
  LOSS CAN BE MORE. IF PRICE JUMPS DOWN: 138.85 USD
  SELL 4 AT 120.00  SELL 5 AT 130.00
  PROFIT IF BOTH HIT 219.85 USD (AFTER FEES)
  AFTER FIRST SELL: KEEP STOP 90.00. NEVER LOWER. CAN RAISE TO 101.01 (REST NO LOSS).
  FEE SCHEDULE: USER-PROVIDED, NOT VERIFIED. CHECK FEES IN YOUR APP.
  FEES: 9.90 USD IN AND OUT = 5.5% OF PROFIT AT FIRST TARGET
  EARNINGS: 2027-01-28 (84 DAYS).
  TREND: OK (SHORT AVERAGES NOT ALIGNED (MA3 > MA10 > MA21 FAILS): NO SHORT-TERM BREAKOUT ENTRY)
  HALAL: OK (SS-21)
  CHARITY AMOUNT: UNKNOWN (DATA MISSING)
  BOYCOTT: NOT ON LISTS
  SCREEN DATA: BOYCOTT LISTS CHECKED 2026-11-04. HALAL DATA FY2025 FILED 2026-02-20. MARKET CAP 2026-11-04.
  PRICE SEEN 2026-11-05T15:30:00-05:00 (LIVE, Nasdaq) PRICE 100.00. GOOD ONLY FOR THIS PRICE.
  PRICE FROM: Nasdaq 2026-11-05 15:30 + Yahoo Finance 2026-11-05 15:31 (MATCH)
  NUMBERS FROM: SEC EDGAR 10-Q FILED 2026-10-31
  CHART DATA FROM: Stooq READ 2026-11-05 15:20
  ANALYSTS FROM: StockAnalysis READ 2026-11-05 14:10
  CHECK PRICE IN APP FIRST.
  CHECK APP CAN DO STOP ORDER. IF NOT: SET ALERT, SELL BY HAND.

NO BUY XYZ
  WHY: COMPANY IS ON A BOYCOTT LIST.
    FOUND ON: OHCHR
    - listed by: ohchr
  FIX: NONE. SKIP IT.
  (ENGINE: boycott screen: excluded)
  WHY: NOT HALAL UNDER YOUR METHOD.
    METHOD: SS-21
    - over the limit: interest_debt
  FIX: NONE. SKIP IT.
  (ENGINE: Shariah screen: excluded)

SOURCES (CHECKED 2026-11-05 20:35 UTC):
- US Bureau of Labor Statistics [OFFICIAL] 2026-10-15: CPI https://www.bls.gov/news.release/cpi.nr0.htm
- Reuters [NEWS] 2026-11-05T12:10:00Z: Fed holds https://www.reuters.com/markets/us/fed-holds/
- CNBC [NEWS] 2026-11-05T12:20:00Z: Fed holds https://www.cnbc.com/2026/11/05/fed-holds.html

YOU DECIDE. YOU PLACE ORDER. NOT ADVICE.
```

Then add at most three short lines:
- why each buy (one line each)
- the one main risk
- sources: the renderer already prints the ledger's sources; add any you cited in these lines

Keep the safety lines even in the simplest output:
- "PLANNED LOSS AT STOP", never "MAX LOSS"
- "LOSS CAN BE MORE"
- the price time, source and market price
- "CHECK PRICE IN APP FIRST", and the stop-order check when stop support isn't confirmed
- any "NOT SCREENED" or "SOURCES NOT CHECKED" warning
- every NO BUY / WAIT reason, with its WHY and FIX lines
- "YOU DECIDE ... NOT ADVICE"


### Dashboard (default, after the simple text)

One self-contained HTML page from the same engine files, in simple words. It copies the engine's numbers and keeps every safety line; it never computes a level or a size.

```
python3 "$SKILL_DIR/scripts/render_dashboard.py" --plans PLAN1.json PLAN2.json \
  --state ACTUAL.json [--projected PROJECTED.json] \
  --market "CALM. FED WAIT." --metals "WAIT." --events "JOBS FRI. CPI TUE." \
  [--skipped "XYZ|why dropped"] [--note "NVDA: on AFSC list"] [--source "Title|https://..."] \
  --tz ZONE [--journal REPORT.json] [--money-plan MONEY_PLAN.json] [--analysis ANALYSIS.json] --title "Trade plan YYYY-MM-DD" --out dashboard.html
```

- Write `--market`, `--metals`, `--events` and every `--note` in short plain words (a 12-year-old should follow them). No jargon: say "price fell under its long average", not "below the 200-DMA".
- Pass every screened plan, including NO TRADE and WATCHLIST ones. The full numbers for each idea sit in a fold at the bottom; only the best pick is open.
- Pass `--projected` when more than one idea was accepted.
- **Check more (v5.3).** The page ends its choices with a "Check more" box: buttons for new ideas, the same ideas with live prices, each sector in `universe.json`, and a field for the user's own tickers. The first line shows whether the US market is open right now (worked out in the page from the NYSE calendar) with a "Follow the market now" button: its request asks for live prices on the holdings and the page's ideas, what changed since the page was made, and whether a plan is ready. A button writes a `quick:` request carrying the run's settings and copies it; the user pastes it in the chat. The page cannot run a check by itself, and it says so. Treat a pasted `quick:` request as a quick follow-up (fast path, rule 3).
- Publish the file as an artifact when the session can (otherwise send the file). Reuse the same file path within a session so the link updates. It is a snapshot: levels are valid only for the quote time shown.
- The page loads nothing external and escapes all text.

### Detailed (only when asked)

1. Profile, portfolio snapshot, quote timestamps and status.
2. Regime, the surprise chain for each release (observation and publication dates), and events in the next 14 days.
3. **Trade plan table:** Ticker | Asset class | Boycott status (sources, entity relationship) | Shariah outcomes and policy | Purification (USD, period, method) | Thesis | Buy limit(s) / tranches | Stop or review level | T1 (shares) | T2 | Shares | Order $ | Fees $ | Breakeven | Downside $ and bucket | Gap loss $ | Net R:R | Verdict and placement | Review date. T-bill ETFs get their own small table.
4. Holdings review (screens, status changes, purification due).
5. Projected portfolio after the plan: weights, sectors, risk buckets vs limits, cash vs floor, commitments, stress scenario.
6. Watchlist and NO TRADE list with reasons.
7. Bear case per idea; the fundamental exit for long-term ideas.
8. Tax checks (section 10).
9. Sources: the full ledger table (category, source, tier, URL, read at, published), with evidence labels and the check time.
10. Closing line: levels are valid only for the quoted price; re-check the live price before placing. The user decides and places trades.

## 13. Guardrails

- No guaranteed-return language. Every idea has a bear case, a downside figure and a gap scenario.
- A stop is a planned exit, not a guaranteed maximum loss. A long-term review level is not an exit.
- Never lower a protective stop after taking partial profit.
- Never invent prices, levels, fees or calculated numbers. Missing data means watchlist or NO TRADE.
- Never describe incomplete screening as clearance.
- Never edit `methodologies.json`, `brokers.json`, `sources.json` or any script during a session.
- The boycott and Shariah screens run on every idea. The user chooses exclude or flag only; never skip a screen, and never plan with `off`.
- Never report a number from a ledger entry that is not FRESH, and never cite a source that is not in the ledger.
- Never write NO BUY or WAIT without every reason.
- A Shariah result is a methodology-based screen, not a fatwa; the user decides doubtful cases.
- Not licensed financial, tax or religious advice.
