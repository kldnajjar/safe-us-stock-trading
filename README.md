# Safe US Stock Trading

A Claude skill that plans US stock, ETF and gold/silver trades for any investor on any broker. It asks how much money you want to trade and what you want to buy. Then it gives exact **buy, sell and stop-loss prices**, sized to your own fees and risk level, with news-driven market analysis, optional **boycott** and **Shariah (halal/haram)** screens, and a short plain-language output.

> **Not financial, tax or religious advice.** The skill is research support. You decide and place every trade yourself; it never logs into a broker or places orders.

## What it does

- **Asks first:** how much money, what to buy (find ideas / your tickers / a theme / review holdings), how long to hold (short / medium / long), and how much risk (safe / balanced / aggressive).
- **Any broker:** fee schedules live in `brokers.json` (percent, per-share, flat or commission-free, with optional separate sell fees and FX cost). There is no default fee schedule; without one the engine returns NO TRADE.
- **Exact levels:**
  - a limit buy price
  - a stop-loss (or a review level for long-term ideas)
  - two sell targets
  - share counts, every fee, the planned loss at the stop, and a gap-down scenario
- **Never lowers a stop** after taking partial profit.
- **Portfolio-wide limits:** position size, sector caps (ETFs looked through), total open risk, and a cash floor. Unquantified risk blocks new trades.
- **News from primary sources first:** Fed, BLS, BEA, Treasury, SEC EDGAR, World Gold Council. Then major outlets: BBC, Reuters, AP, Bloomberg, FT, WSJ, CNBC, The Economist, MarketWatch, Barron's, Yahoo Finance, Al Jazeera, The Guardian, Nikkei Asia. Releases are read against expectations, not by fixed rules.
- **Gold/silver signal:** a six-factor score; unknown factors lower confidence instead of counting as zero.
- **Optional screens, each the user's choice:**
  - **Boycott:** UN OHCHR settlements database, BDS, AFSC Investigate, Who Profits, SEC filings. The status is computed from source-by-source evidence (finding, date, link), never typed in.
  - **Shariah:** AAOIFI SS-21, MSCI Islamic (Index Series and M-Series), S&P Shariah, Dow Jones Islamic Market. Thresholds come from a versioned, sourced registry, with purification in USD.
- **Simple output by default:**

```
RISK: BALANCED. HOLD: SHORT.
MARKET: CALM. FED WAIT.
GOLD/SILVER: WAIT.

BUY ABC
  PRICE 100.00 (LIMIT)  SHARES 10  COST $1,005.00
  STOP 94.00  PLANNED LOSS AT STOP $70.67
  LOSS CAN BE MORE. IF PRICE JUMPS DOWN: $117.41
  SELL 5 AT 112.00  SELL 5 AT 119.00
  PROFIT IF BOTH HIT $143.15 (AFTER FEES)
  AFTER FIRST SELL: KEEP STOP 94.00. NEVER LOWER. CAN RAISE TO 101.11 (REST NO LOSS).
  HALAL: OK (SS-21)
  GIVE $0.10 TO CHARITY (FY2025)
  BOYCOTT: NOT ON LISTS
  PRICE SEEN 2026-11-05T15:30:00-05:00 (DELAYED 15M, Yahoo Finance) PRICE 100.00. GOOD ONLY FOR THIS PRICE.
  CHECK PRICE IN APP FIRST.
  CHECK APP CAN DO STOP ORDER. IF NOT: SET ALERT, SELL BY HAND.

NO BUY XYZ: boycott screen: excluded

YOU DECIDE. YOU PLACE ORDER. NOT ADVICE.
```

- **Dashboard every run:** `render_dashboard.py` turns the same engine files into one self-contained HTML page (portfolio, limits used, BUY / WAIT / NO BUY cards with reasons, holdings, sector exposure, sources), light and dark, phone-friendly. Numbers are copied from the engine, never recomputed.

## Repository layout

```
.
├── README.md
├── .gitignore
├── .github/workflows/checks.yml   # runs run_checks.py on every push / PR
└── safe-us-stock-trading/              # the skill itself
    ├── SKILL.md                   # instructions Claude follows
    └── scripts/
        ├── run_checks.py          # one command: files + registries + all tests
        ├── size_trade.py          # sizing, fees, gates, exits (price trades and T-bill funds)
        ├── portfolio_state.py     # actual vs projected portfolio, orders, risk buckets
        ├── shariah_screen.py      # Shariah screen and result files with provenance
        ├── boycott_screen.py      # boycott screen: status computed from per-source evidence
        ├── fees.py                # broker cost models
        ├── render_simple.py       # plain-language output, numbers copied from the engine
        ├── render_dashboard.py    # per-run HTML dashboard, numbers copied from the engine
        ├── methodologies.json     # Shariah rules registry (versioned, sourced, dated)
        ├── brokers.json           # broker fee profiles and templates
        ├── test_size_trade.py     # unit tests
        ├── test_audit_regressions.py  # 16 independent audit regression tests (v4.1 audit)
        ├── test_v42_followup.py   # 6 independent follow-up audit tests (v4.2 audit)
        ├── test_v43_policy.py     # clock, market price, stop capability, FX, certificate/market-cap dates
        ├── test_v43_independent.py  # 5 independent audit tests (v4.3 audit)
        ├── test_v44_hardening.py  # ETF weights, buy/sell orders, state weights, bounded sizing (randomized)
        ├── test_v44_independent_followup.py  # 6 independent audit tests (v4.4 audit)
        ├── test_v45_hardening.py  # worst-case Unclassified (randomized), cent grid, T-bill market, order states
        ├── test_dashboard.py      # dashboard: verbatim numbers, safety lines, escaping, self-contained
        └── test_integration.py    # full command-line chain across every asset type
```

Only Python 3.9+ standard library is needed; there are no dependencies to install.

## Install

**Claude apps (upload):** build the package and upload it in Claude's skill settings.

```bash
zip -r safe-us-stock-trading.skill safe-us-stock-trading -x '*/__pycache__/*'
```

**Claude Code:** copy or symlink the skill folder into your skills directory.

```bash
cp -r safe-us-stock-trading ~/.claude/skills/
```

## Verify

```bash
python3 safe-us-stock-trading/scripts/run_checks.py
```

This prints a JSON report and exits with code 0 only if every file is present, both registries pass schema validation, and every test passes. The skill runs this itself at the start of each session and falls back to watchlist-only mode if it fails. The same check runs in GitHub Actions on every push.

## Use

Ask Claude something like:

- "What stocks should I buy with $5,000? Long term, balanced."
- "Plan a short-term trade on these tickers: …"
- "Review my holdings and tell me what to sell."
- "Should I move into gold now?"

The first time, it asks for your platform and fee schedule, which screens you want, your tax residency, and your current holdings, cash and open orders.

## Configuration

### Add your broker

Copy a template in `safe-us-stock-trading/scripts/brokers.json` (`template-percent`, `template-per-share`, `template-flat`, `template-zero`), give it a new id, fill in your schedule, remove `"template": true`, then run `run_checks.py`.

- **Rates are fractions:** `0.005` means 0.5%. The engine rejects 0.1 or more as a likely mistake.
- **Optional extras:** a separate `sell` schedule, and `fx_pct` for currency conversion. FX is charged only when the instrument's currency differs from the account currency (`--account-currency`, else the profile's `currency`), so a USD account buying US stocks pays no phantom FX. There's no exchange-rate model yet, so a cross-currency account gets research-only plans.
- **Spread and slippage are applied separately** (`--friction-bps`, default 5 per side).

To keep a personal fee schedule out of public commits, put it in `brokers.local.json` (git-ignored, same format) and pass it with `--brokers path/to/brokers.local.json`.

### Shariah methodology registry

`methodologies.json` is the only source of Shariah thresholds. Each entry records:
- provider and document version
- effective date and official source URL
- the date it was verified
- exact ratios, denominators and comparators
- entry, threshold and exit buffers, and any multi-period rule
- the purification method
- retrieval evidence

The screen returns UNVERIFIED when:
- the provider publishes a version the registry doesn't list
- an entry is older than `max_age_days`
- an entry is disabled

To update it:
1. Read the provider's new methodology document.
2. Edit the entry, or add the new version and mark the old one `historical_only`.
3. Record what you compared in `evidence`. An alternate edition goes in `equivalent_versions` only after every rule has been compared; titles alone are not enough.
4. Run `run_checks.py`.

The skill never edits this file during a session.

Registry as verified on 2026-11-05:

| Methodology | Version |
|---|---|
| AAOIFI | SS-21 |
| MSCI Islamic Index Series | May 2025 |
| MSCI Islamic M-Series | May 2025 |
| S&P Shariah | October 2026 (effective 2026-09-21) |
| Dow Jones Islamic Market | September 2026 (effective 2026-09-18) |

## Safety design

- Every number in a trade plan comes from the scripts, never estimated by the model. An engine error means NO TRADE.
- **Inputs are validated:** numbers must be finite and positive or non-negative; sector weights must lie between 0 and 1 and total 1; dates can't be in the future or stale.
- **Caps count everything in a ticker:** each stock or ETF cap includes current holdings, open orders and planned buys in that ticker, plus related share classes.
- **Stops are checked:** a stop further below any entry than the profile and horizon allow is rejected, and a stop is never lowered after partial profit.
- **Breakevens include every exit cost** and are rounded up to the cent.
- A trade stays **provisional** until you confirm the exact order (ticker, type, limit price, shares) in your own app.
- Screen modes are required arguments, never silently defaulted.
- Boycott and Shariah verdicts must come from result files that match the ticker, asset type and ISIN, haven't expired, and give the same verdict when recomputed from their recorded evidence or inputs. This is a consistency check, not tamper-proofing.
- **Freshness is checked against the system clock**, not a date you pass. `--as-of` must be today, a live quote at most 15 minutes old, a delayed quote at most its stated delay (20 minutes max) plus 15 minutes. Anything else is a watchlist entry with a conditional plan. `--now` replays a past moment for research and is never executable.
- **Levels are tied to the market:** `--market-price` from the same quote is required; an entry more than 1% above it, or a market price at or below the stop, is NO TRADE.
- **Only a matching limit order confirms a plan**, and a short/medium plan is marked ready only when the stop can be handled (`--stop-orders yes`, or a manual stop the user accepts).
- **Flag-mode screens without a result file are labelled SCREEN NOT RUN**, never "screened".
- **Portfolio state is validated:** every working order states buy or sell and a known status (open/partial/filled/cancelled) with consistent whole-share quantities; sell orders reserve no cash and add no exposure, and can't exceed the shares held; sector weights must be valid. Bad state is an error, never silently counted.
- **Unclassified sector money is worst case:** holdings with no sector data, and any "Unclassified" weight, count against every sector a new buy touches, so missing data can't hide a sector-cap breach.
- **Cent grid:** every order and level price must be a whole number of cents; off-grid prices are NO TRADE, never rounded.
- **T-bill funds** need a market price from the same quote too; a limit more than 1% above it is NO TRADE.
- **ETF boycott weights** must be 0–100%, 100% screened, with excluded + flagged no more than screened.
- **Sizing is bounded:** prices under $1 are rejected, and the share quantity is found by binary search (checked against the old linear scan on 400 random cases), so a huge account or a low price can't stall it.
- **Shariah dates are checked twice:** a market-cap date (required for market-cap methodologies, at most 31 days old) and a certificate date (at most 400 days old, with an https link) are re-checked when the trade is sized.
- Portfolio state, plans and screening files are git-ignored because they can contain personal holdings.

## Audit status

v4.5 fixes all six findings from the independent v4.4 code audit (2026-11-05):

| Finding | Fix |
|---|---|
| H1: a holding with no sector data could hide a sector-cap breach | Counted as Unclassified, which the engine places worst case (in whichever sector the buy touches); also applies to an ETF's own Unclassified weight |
| H2: T-bill limit price wasn't checked against the market | `--market-price` required (missing → WATCHLIST); limit more than 1% above it → NO TRADE |
| M1: fractional-cent prices were accepted | Every entry, tranche, stop, target and T-bill limit must be on the cent grid; never rounded |
| M2: overfilled orders silently disappeared | Whole-number `shares` > 0 and 0 ≤ `filled_shares` ≤ `shares`, consistent with status; otherwise an error |
| M3: unknown order status treated as open | Status must be open, partial, filled or cancelled; otherwise an error |
| L1: T-bill confirmation mentioned a stop | T-bill wording says no stop applies and points to rate risk |

Earlier rounds: v4.4 fixed the v4.3 audit (ETF boycott weights, sell orders, state sector weights, bounded sizing); v4.3 the v4.2 follow-up (system-clock quotes, market price, stop capability, flag mode, FX); v4.2 the v4.1 audit.

| Test file | Tests |
|---|---|
| `test_size_trade.py` (unit) | 170 |
| `test_audit_regressions.py` (v4.1 audit) | 16 |
| `test_integration.py` | 21 |
| `test_v42_followup.py` (v4.2 audit, unchanged) | 6 |
| `test_v43_policy.py` | 31 |
| `test_v43_independent.py` (v4.3 audit, unchanged) | 5 |
| `test_v44_hardening.py` | 19 |
| `test_v44_independent_followup.py` (v4.4 audit) | 6 |
| `test_v45_hardening.py` | 17 |
| `test_dashboard.py` (v4.6) | 11 |
| **Total, all passing** | **302** |

Test setup notes:
- Fixed-date fixtures run with the engine's clock pinned to 2026-11-05 20:35 UTC, inside the test process only. The command line can't set the clock.
- The reconstructed header of `test_audit_regressions.py` passes `--market-price` and `--market-cap-date`, both now required.
- The skill was renamed from `us-portfolio-cfo` (US Portfolio CFO) to `safe-us-stock-trading`. The auditor-supplied `test_v42_followup.py` and `test_v43_independent.py` still mention the old name in their opening comment; they're kept exactly as supplied.
- The first part of `test_v44_independent_followup.py` didn't arrive. Its header, the sector-cap test and the start of the first T-bill test were rebuilt from the audit report; the rest is the auditor's text, unchanged. It uses the real clock, not a pinned one.

Still open, and outside what code can settle:
- **Specialist review:** registry checks validate structure, not whether the Shariah methodology summaries or an issuer's certificate are correct.
- **Evidence is a research record:** a boycott evidence file records what was found and where; it doesn't prove the source was read correctly.
- **External confirmation:** methodology versions, data freshness, broker fees, tax treatment and order types.
- **Supervised paper trading** across several sessions: stale and after-hours quotes, partial fills, cancellations, corporate actions.

Until you've done the paper trading, treat plans as research and keep confirming every order in your app.

## Disclaimer

For research and education only. Not investment, tax or religious advice. Fee schedules are user-provided unless marked verified. Methodology summaries may lag provider updates; the registry and fail-safe checks reduce but don't eliminate that risk. Markets can gap through stops, and losses can exceed the planned amount.
