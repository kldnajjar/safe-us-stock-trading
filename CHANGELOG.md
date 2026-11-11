# Changelog

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the skill's own numbering.

## [Unreleased]

### v5.2: a money plan for the whole amount

- `money_plan.py`: from the user's own state and risk level, the safety cash to keep, dated steps for putting the money in (the user chooses how many), the most allowed per kind of thing (gold fund, broad fund, single company), and what to fix first. It names no stock and promises nothing; each step means "run the skill that day".
- Dashboard section "Your money plan: when, and what kind", with times in the user's zone.
- 458 tests pass.

### v5.1: times in your own time zone; a no-buy page that still tells you what to do

- `--tz ZONE` on both renderers (IANA name such as `Asia/Amman`, or an offset such as `+03:00`): every time is shown in the user's zone with New York in brackets ("WED 11 NOV 17:30 AMMAN TIME (09:30 NEW YORK)"); no raw timestamps. The skill takes the zone from the session or from the country the user chose.
- No-buy pages: the answer carries its one-line why; the steps say when the US market next opens in the user's time; **ALSO FIX IN YOUR APP** lists a holding with no stop or past its stop; the page is headed "What I looked at"; money, holdings and full numbers are folded under "More, if you want it"; the colour key moved below the checks.
- **"It passes at X or lower".** When the only blocker is profit too small for the risk, the engine finds the highest entry price (same stop and targets) at which the plan passes every gate, and the output says it: "IT PASSES AT 340.87 OR LOWER ... SET A PRICE ALERT". No price is shown when anything else is wrong.
- Printing: folded sections are opened on paper / PDF.
- **A "no buy" has to be earned.** The run now prices 3 to 4 candidates of different kinds (always at least one single company), shows screen-failing names as YOUR CALL options in flag mode instead of skipping them, asks before running on a closed market, and ends with the plain reason for a no-buy.
- **Honest odds.** Each plan shows how many of 100 such trades must reach the targets to break even ("nobody can promise that").
- **"Is this making you money?"** box on the dashboard from the trade journal: no record yet, too few trades to know, not working, behind just holding the fund, or working so far, with the money made or lost after fees.
- 453 tests pass.

### v5.0: simple, colour-coded dashboard; one-call data intake; one-card run

**Changed**
- **Dashboard rebuilt in simple words.** Order: TODAY (one coloured answer) → DO THIS NOW → YOUR CHOICES (PAY / CAN LOSE / CAN WIN per option, BEST PICK or YOUR CALL) → CHECKS (boycott and halal with proof links) → YOUR MONEY → full numbers in folds → sources.
- **Colour always means the same thing** and carries a sign so it reads without colour: green `+` good / can win, yellow `!` wait / your call, red `x` stop / can lose, blue `i` info. Risk meters turn yellow and red as they fill; gains are green and losses red.
- Text output opens with the colour key and marks every check and option line with 🟢 🟡 🔴.
- SKILL.md opens with an eight-step run card; rules list fixed to five.

**Added**
- `browser_fetch.js` + `ingest.py`: one browser call returns the quote and a year of daily prices for every ticker; one command writes the price files, ledgers them and runs the signals.
- **Readable sources only.** A source that blocks reading (robots rule, paywall, login) is not used or cited. bl00d.money was tried and removed because it refuses automated readers; the paywalled outlets (Bloomberg, FT, WSJ, The Economist, Barron's, Nikkei Asia) left the news list.
- **Robinhood: the user chooses the account** (United States, United Kingdom or Singapore; each has its own verified profile). The skill never assumes the US one.
- Dashboard says "NO STOP SET" and "PAST ITS STOP" in place of UNQUANTIFIED / BREACHED.
- `test_v50_ingest.py` (18 tests). 442 tests pass.

**Fixed (first real v5.0 run, 2026-11-11)**
- Dashboard printed or saved as PDF from dark mode came out pale grey: print now forces the light colours, keeps chip and bar colours, and avoids splitting cards across pages.
- A halal check that ran but could not be proven said "NOT CHECKED"; it now says "CAN'T CONFIRM".
- Step numbers sat on the box edge; double period after the events line; the same source listed twice.

**Fixed (v5.0 self-audit, 2026-11-11; one test each)**
- A T-bill fund was listed as "ENGINE SAYS NO" while the steps told the user to buy it, even when not halal. It is now its own option ("PARK CASH", your call) and never appears in the steps.
- Long-term ideas showed "RISK $0.00"; they now show the loss at the review level.
- Plans bought in tranches were shown as one order at the first price; options, steps and dashboard now list every step.
- A WAIT (watchlist) idea was shown as a red "ENGINE SAYS NO"; it is now a yellow WAIT.
- Text and dashboard could letter the options differently; both now use one function, so letters and the pick always match.
- SKILL.md: a dollar sign followed by a digit was replaced by the user's words when the skill loaded ("Under want,000"). Amounts are now written "1,000 USD"; a test guards it.
- `--budget` below the app's minimum order now says so (it blamed the cash floor).
- `ingest.py`: ticker names are validated before they become file names; New York time comes from the engine's own clock (no tz database needed).

### v4.9: clear options, flag labels with references, budget cap, Robinhood

**Added**
- Every output opens with **SCREENS** (boycott and halal result per idea, each with its reference: list and link, or methodology and failed ratio), **YOUR OPTIONS** (lettered, with engine numbers, plus KEEP CASH and one RECOMMENDED letter: a clean option that passes the risk rules, else cash) and **WHAT TO DO NOW** (app steps for the recommended option). Text and dashboard.
- Flag mode now shows failing names as labelled options ("ON BOYCOTT LIST / NOT HALAL (FLAG ONLY: YOU DECIDE)" with references); the recommendation never goes to a flagged name.
- `--budget` on `size_trade.py` caps the order cost (with buy fees) at the user's amount; limits still use the whole portfolio.
- `robinhood` broker profile: commission-free US stocks and ETFs, verified 2026-11-09.
- `--skipped "TICKER|why"` on both renderers; plans blocked only by never-run screens are listed once under SKIPPED instead of a red NO BUY.
- SKILL.md: fast path, screen-before-show rule, one account per trade, AFSC fund search for ETF look-through, output order.

**Changed**
- A Shariah REQUIRES_ACCEPTANCE result is labelled "HALAL IF YOU ACCEPT".

### v4.8: mandatory screens, fresh cited sources, full NO BUY reasons, journal, audited

**Changed (breaking for the question flow)**
- Boycott and Shariah screens are **mandatory**: the engine refuses `off`, flag mode needs a real result file, and question B4/B5 offer only Exclude (default) or Flag only. The Shariah methodology and interest-on-cash questions are always asked.
- Every NO BUY / WAIT (text and dashboard) prints **all** reasons in plain words, the facts behind them, a fix, the engine text, and "ALSO NEEDED" lines.

**Added**
- Source ledger: `sources.json` (ranked registry: official > wire/press > data sites, freshness rules per data type), `sources_check.py`, `ledger.py`. The engine re-checks the ledger at sizing time; stale, conflicting or off-site sources mean WATCHLIST. Plans and the dashboard show where every number came from.
- `market_clock.py` (ported from trader-skill, MIT): executable only in the NYSE regular session, quote from the current session, 2026–2027 holidays and early closes.
- `signals.py`: long-only signals from *151 Trading Strategies* (momentum, SUE, low volatility, multifactor rank, trend and dual-momentum filters), recomputed by the engine from the recorded prices. AVOID refused; short-term entries need a good trend.
- Gates: earnings date from the ledger (earliest wins; short-term trades not held through earnings unless accepted); short-term trades refused when fees eat >25% of the first target's profit; dividends after US withholding.
- `journal.py`: paper/real trade journal, performance report vs a benchmark, `reconcile` against the app, audit trail (plan SHA-256, broker, fee source).
- `run_checks.py`: expiry warnings for the Shariah registry, source registry and NYSE calendar.
- `AUDIT-v4.8.md`: four-round verification record.

**Fixed (59 findings from an independent code review, an end-to-end run, an adversarial audit and a treasury audit)**
- Bypasses closed: fake earnings date, edited signals, edited screen expiry, ETF boycott relabel, edited plan verdict, related-ticker max-positions trick, sector-name aliases, company sized as metal, pre-open quote, unknown asset types, duplicate holdings/orders, projected state depending on plan order.
- Money: pending buy orders now count their unpaid fee as risk; losses/costs round up, profits down, charity up.
- Crashes on bad price files and inputs now fail cleanly; the metal Shariah screen's `--metal-structure` is documented.
- 412 tests (all gates on in `test_v48_mandatory.py`; older suites isolate their own gate).

### Changed (v4.7)
- The whole flow asks **one question per message**: setup (trade, account, portfolio) and every question that comes up during the run (sector, flagged screens, earnings gap risk, manual stop, live price, order match, fills). Each question has a progress tag, picker options where the answers are fixed, a safe default for "not sure", and is skipped when already answered. Unattended runs use the defaults, stay WATCHLIST-only and list the open questions.

### Added
- MIT `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, issue and PR templates.
- GitHub Actions workflow that runs `run_checks.py` on Python 3.9 (Ubuntu 24.04) and 3.13 (latest Ubuntu) for every push and PR.

### Fixed
- Dashboard crashed when a holding had no stop (`UNQUANTIFIED`) or was past it (`BREACHED`); those rows now show the status and a CHECK badge, and the open-risk tile says real risk is unknown instead of implying $0. Regression test added (303 tests).

### Changed
- README rewritten: quick start, how it works, dashboard preview, configuration, safety design, roadmap.

## [4.6] - 2026-11-06

### Added
- `render_dashboard.py`: per-run, self-contained HTML dashboard (portfolio, limits used, BUY / WAIT / NO BUY cards with reasons, holdings, sector exposure, notes, sources). Numbers copied from the engine; all text escaped; nothing external loaded; light/dark; phone-friendly.
- `test_dashboard.py`: 11 tests (verbatim numbers, safety lines, escaping, self-contained page, CLI). 302 tests total.
- `SKILL.md` section 12: dashboard is a default output step after the simple text.

## [4.5] - 2026-11-05

Fixes all six findings from the independent v4.4 code audit.

| Finding | Fix |
|---|---|
| H1: a holding with no sector data could hide a sector-cap breach | Counted as Unclassified and placed worst case (in whichever sector the buy touches); also applies to an ETF's own Unclassified weight |
| H2: T-bill limit price wasn't checked against the market | `--market-price` required (missing → WATCHLIST); limit more than 1% above it → NO TRADE |
| M1: fractional-cent prices were accepted | Every entry, tranche, stop, target and T-bill limit must be on the cent grid; never rounded |
| M2: overfilled orders silently disappeared | Whole-number `shares` > 0 and 0 ≤ `filled_shares` ≤ `shares`, consistent with status; otherwise an error |
| M3: unknown order status treated as open | Status must be open, partial, filled or cancelled; otherwise an error |
| L1: T-bill confirmation mentioned a stop | T-bill wording says no stop applies and points to rate risk |

## [4.4]
- Fixed the v4.3 audit: ETF boycott weights, buy/sell orders, state sector weights, bounded (binary-search) sizing.

## [4.3]
- Fixed the v4.2 follow-up: system-clock quote freshness, required market price, stop-order capability, flag-mode labelling, FX only on real conversion.

## [4.2]
- Fixed the v4.1 audit (16 regression tests).

## Earlier
- Renamed from `us-portfolio-cfo` (US Portfolio CFO) to `safe-us-stock-trading`.

## Test notes carried from earlier releases
- Fixed-date fixtures run with the engine's clock pinned to 2026-11-05 20:35 UTC, inside the test process only. The command line can't set the clock.
- The reconstructed header of `test_audit_regressions.py` passes `--market-price` and `--market-cap-date`, both now required.
- `test_v42_followup.py` and `test_v43_independent.py` are auditor-supplied and kept exactly as supplied; their opening comments still use the old name.
- The first part of `test_v44_independent_followup.py` didn't arrive. Its header, the sector-cap test and the start of the first T-bill test were rebuilt from the audit report; the rest is the auditor's text, unchanged. It uses the real clock.
