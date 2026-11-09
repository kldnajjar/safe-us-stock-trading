# Changelog

All notable changes to this project. Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow the skill's own numbering.

## [Unreleased]

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
