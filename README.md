# Safe US Stock Trading

A Claude skill that plans US stock, ETF and gold/silver trades for any investor on any broker. You say how much money and what you want to buy; it gives an exact **limit buy price, stop-loss and two sell targets**, sized to your own fees and risk level. Every idea is run through a **boycott screen** and a **Shariah (halal) screen**, every number comes from a **fresh, named, ranked source**, and every NO BUY tells you **why** and what would fix it.

> **Not financial, tax or religious advice.** The skill is research support. It never logs into a broker or places orders: you decide and place every trade yourself.

**Version 4.6** · 395 tests passing · money math independently verified to the cent · [verification record](AUDIT-v4.6.md)

## Status: ready for paper trading

The engine is verified. Whether the skill makes money is **not proven yet**: that needs about 20 closed trades in the built-in journal.

1. **Paper trade first.** Record each plan and simulated fill with `journal.py` until you have about 20 closed trades.
2. **Then go real, small.** One or two positions whose planned loss you're fine with. Reconcile the journal with your app after every fill.
3. **Scale up only if** `journal.py report` says "positive after costs and ahead of the benchmark". If not, simply holding a screened ETF is the better choice, and the report will say so.

## Quick start

**1. Install**

Claude apps: build the package and upload it in Claude's skill settings.

```bash
zip -r safe-us-stock-trading.skill safe-us-stock-trading -x '*/__pycache__/*'
```

Claude Code: copy the skill folder into your skills directory.

```bash
cp -r safe-us-stock-trading ~/.claude/skills/
```

Python 3.9+ standard library only; nothing to install.

**2. Verify**

```bash
python3 safe-us-stock-trading/scripts/run_checks.py
```

Exit code 0 means every file is present, all three registries are valid and all tests pass. The report also shows the NYSE clock and anything due to expire within 30 days. Claude runs this at the start of each session and falls back to watchlist-only mode if it fails.

**3. Ask Claude**, during NYSE hours:

- "What should I buy with $5,000? Long term, balanced."
- "Plan a medium-term trade on these tickers: …"
- "Review my holdings and tell me what to sell."
- "Should I move into gold now?"

The first time, it asks for your platform and fees, how each screen is applied (exclude or flag only), your Shariah methodology, your tax residency, and your holdings, cash and open orders.

### When to run it

Plans are only executable while the NYSE regular session is open (09:30–16:00 New York, 1:00 p.m. on early-close days). Outside it you get a conditional WAIT plan to re-run later.

| Your time zone | US winter time (Nov–Mar) | US summer time (Mar–Nov) |
|---|---|---|
| Amman / Riyadh (UTC+3) | 17:30 – 24:00 | 16:30 – 23:00 |
| Dubai (UTC+4) | 18:30 – 01:00 | 17:30 – 24:00 |
| London | 14:30 – 21:00 | 14:30 – 21:00 |

## What you get

```
RISK: BALANCED. HOLD: MEDIUM.
NYSE: OPEN. CLOSES 16:00 NEW YORK TIME.

BUY ABC
  PRICE 100.00 (LIMIT)  SHARES 9  COST $904.50
  STOP 90.00  PLANNED LOSS AT STOP $98.55
  LOSS CAN BE MORE. IF PRICE JUMPS DOWN: $138.85
  SELL 4 AT 120.00  SELL 5 AT 130.00
  PROFIT IF BOTH HIT $219.85 (AFTER FEES)
  AFTER FIRST SELL: KEEP STOP 90.00. NEVER LOWER. CAN RAISE TO 101.01 (REST NO LOSS).
  FEE SCHEDULE: USER-PROVIDED, NOT VERIFIED. CHECK FEES IN YOUR APP.
  FEES: $9.90 IN AND OUT = 5.5% OF PROFIT AT FIRST TARGET
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

(Real engine output from the test fixtures; a detailed report is available on request.)

## Features

**Planning**
- Asks how much money, what to buy (find ideas, your tickers, a theme, or a review of holdings), how long to hold (short / medium / long) and how much risk (safe / balanced / aggressive).
- Exact levels: limit entry (or 2–3 tranches), stop-loss or long-term review level, two targets, shares, every fee, planned loss, gap-down loss, fee-adjusted breakeven.
- Portfolio-wide limits: position size, sector caps (ETFs looked through), total open risk, a settled-cash floor, maximum positions. Each idea is sized against the previous ones.
- Any broker: percent, per-share, flat or commission-free fees, separate sell fees and FX, from `brokers.json`. With no fee schedule the engine returns NO TRADE.
- Gold/silver: a six-factor macro score, and physical metal trusts checked for Shariah structure.

**Screens (always on)**
- **Boycott:** UN OHCHR settlements database, BDS, AFSC Investigate, Who Profits and SEC filings, all checked within 30 days. The status is computed from the per-source evidence, never typed in.
- **Shariah:** AAOIFI SS-21, MSCI Islamic (Index and M-Series), S&P Shariah, Dow Jones Islamic, from a versioned registry. Purification is calculated in USD and always rounded up.
- You choose **exclude** (default: failing names are never planned) or **flag only** (screened and labelled; you decide). There is no "off".

**Sources (always fresh, always shown)**
- Ranked registry: tier 1 official (SEC, exchanges, Fed, BLS, BEA, Treasury, FRED, Cboe, CME), tier 2 wire and press (Reuters, AP, Bloomberg, FT, WSJ, CNBC…), tier 3 data sites (Yahoo, Stooq, StockAnalysis…).
- Every number is a ledger entry, checked for: the right source for that kind of data, a URL on that source's own site, freshness (a price at most 15 minutes old, filings checked the same day), the latest release, two price sources within 0.5% of each other, and two outlets or one official source per news claim.
- Company financials come only from SEC filings.

**Discipline**
- **Signals** from *151 Trading Strategies* (long-only): 12-1 momentum, earnings momentum (SUE), low volatility, multifactor rank, a 200-day trend filter and a broad-market filter. AVOID is refused, and short-term entries need a good trend.
- **Earnings:** short-term trades are not held through earnings unless you accept the gap risk. The earnings date must come from the source ledger.
- **Fees:** a short-term trade where fees eat more than 25% of the first target's profit is refused.
- **US dividend tax:** net yield after withholding (30% without a tax treaty).
- **NYSE clock:** holidays and early closes for 2026–2027.

**Record-keeping**
- **Journal:** paper and real trades kept apart; win rate, average R, totals after fees and charity, worst drop, and the result against a screened benchmark fund over the same days.
- **Reconcile:** the journal's open positions are checked against the shares your app shows.
- **Audit trail:** each journal entry stores a SHA-256 fingerprint of the plan, the broker, the fee source and the placement status.

## How a session runs

```
run_checks.py ─► questions ─► portfolio_state.py ─► news + macro ─► candidates
                                                                        │
       ┌────────────────────────────────────────────────────────────────┘
       ▼   for every candidate
  boycott_screen.py + shariah_screen.py ─► ledger.py add (each source) ─► ledger.py check
       ─► signals.py ─► size_trade.py ─► portfolio_state.py --plans (projected) ─► next idea
                                                                        │
                                                       render_simple.py ┘ ─► you place the order
                                                                              ─► journal.py open / fill / reconcile / report
```

## Why you'll often see NO TRADE

Usually the rules are working, not a bug. In 7,200 realistic simulated setups (with Bank al Etihad's 0.5% fees), the main causes were:

| Cause | What happens | What helps |
|---|---|---|
| **Market closed** | Outside NYSE hours every plan is a WAIT | Run during the session (see the table above) |
| **Small account** | Whole shares only, a single stock is capped at 10% of the account (5% on Safe), and the minimum order is $100. Below ~$1,000 almost nothing fits; on Balanced the account must be at least 10× the share price | Use a screened ETF (35% cap), or a larger account |
| **Fees on short trades** | About 1% per round trip, and at least $2 profit after fees per $1 risked is required. With a 4% stop, a short trade needs about an 11% target | Prefer medium or long holds (they pass 60–70% of the time vs ~40% for short) |
| **Screens** | Strict boycott and Shariah screens remove many large US companies before sizing | Flag-only mode widens the pool, but you judge each flagged name |
| **Missing or stale data** | No fresh source, earnings date or trend check means WAIT, with what's missing listed | Refresh the sources and re-run |

NO TRADE is a valid outcome. With costs like these, trading less often usually keeps more money.

## Configuration

**Your broker.** Copy a template in `scripts/brokers.json` (`template-percent`, `template-per-share`, `template-flat`, `template-zero`), give it an id, fill in the schedule, remove `"template": true`, then run `run_checks.py`.
- Rates are fractions: `0.005` means 0.5%.
- Optional: a separate `sell` schedule and `fx_pct`. FX is charged only when currency is actually converted.
- Spread and slippage are separate (`--friction-bps`, default 5 per side).
- Keep personal fee schedules in `brokers.local.json` (git-ignored) and pass `--brokers`.
- Profiles are marked user-provided until `verified_source` is set, and every plan says so.

**Registries.** Maintainers edit these; the skill never edits them during a session.

| File | What | Re-check | Current |
|---|---|---|---|
| `methodologies.json` | Shariah thresholds, versions, purification method | every 120 days | verified 2026-11-05, due 2027-03-05 |
| `sources.json` | Accepted sources, tiers, freshness rules | every 180 days | verified 2026-11-09, due 2027-05-08 |
| `market_clock.py` | NYSE holidays and early closes | yearly | 2026–2027 from nyse.com |

`run_checks.py` warns 30 days before any of these goes stale. After they expire, the affected checks refuse to pass.

Shariah registry versions: AAOIFI SS-21; MSCI Islamic Index Series, May 2025; MSCI Islamic M-Series, May 2025; S&P Shariah, October 2026; Dow Jones Islamic Market, September 2026.

**Optional: faster data.** Claude's sandbox blocks most finance sites by default. Allowing `sec.gov`, `data.sec.gov`, `finance.yahoo.com` and `stooq.com` under Claude Settings > Capabilities cuts the manual lookups.

## Safety design

- **Every number comes from the scripts**, never from the model. An engine error means NO TRADE.
- **Nothing is executable unless:**
  - both screens have passed, from result files re-checked at trade time
  - every source is fresh
  - the NYSE is open and the quote is from the current session (at most 15 minutes old)
  - the entry is within 1% of the market price and every price is in whole cents
  - every limit holds: position, sector, open risk, cash floor and maximum positions
- **A plan stays provisional** until you confirm the exact order in your app (ticker, limit, price, shares) and how the stop will be handled.
- **Files are re-checked, not trusted:**
  - screen expiry is recomputed from each result's own date
  - boycott evidence must match the asset type and ISIN
  - signals are recomputed from the price rows recorded in the file
  - an edited plan verdict is refused everywhere downstream

  Forging a file's inputs as well isn't detected: this is a consistency check, not tamper-proofing.
- **Conservative money math:** losses and costs are rounded up, profits rounded down, breakevens rounded up and charity rounded up. Unfilled buy orders count their unpaid fee as risk. A stop is never lowered after taking partial profit.
- **Portfolio state is validated:** known asset types and order statuses only, whole-share quantities, no overselling, no duplicate holdings or order ids. A holding already under its stop blocks new trades until you reconcile it.
- **Personal files stay private:** portfolio state, plans, screens, source ledgers and the journal are git-ignored.

## Verification

v4.6 went through four rounds: an independent code review, an end-to-end run through the real tools, an adversarial audit that tried to break every rule, and a treasury audit that rebuilt the money math independently. 59 findings were fixed, each with a regression test. The independent recomputation matched every dollar figure to the cent across 760 random plans, 50 T-bill plans, a two-plan portfolio chain and 30 journal trades. The full record is in [AUDIT-v4.6.md](AUDIT-v4.6.md).

| Test file | Tests |
|---|---|
| `test_size_trade.py` (unit) | 170 |
| `test_audit_regressions.py` (v4.1 audit) | 16 |
| `test_integration.py` (command-line chain) | 21 |
| `test_v42_followup.py` (v4.2 audit) | 6 |
| `test_v43_policy.py` | 31 |
| `test_v43_independent.py` (v4.3 audit) | 5 |
| `test_v44_hardening.py` | 19 |
| `test_v44_independent_followup.py` (v4.4 audit) | 6 |
| `test_v45_hardening.py` | 17 |
| `test_v46_mandatory.py` (v4.6: all gates on, every review finding) | 104 |
| **Total, all passing** | **395** |

Test notes:
- Fixed-date fixtures pin the engine's clock to 2026-11-05 20:35 UTC inside the test process; the command line can't set the clock.
- The pre-v4.6 suites switch off the three v4.6 gates (screens, sources, market hours) with a short block at the top of each file, so each keeps testing the gate it was written for. `test_v46_mandatory.py` runs with every gate on.
- Older audit files keep their original wording. `test_v42_followup.py` and `test_v43_independent.py` still mention the old name `us-portfolio-cfo`. Part of `test_v44_independent_followup.py` was rebuilt from its audit report.

**Still outside what code can settle:**
- broker fees and fee rounding (check one real fill against its plan)
- US dividend withholding for your country
- specialist review of the Shariah methodology summaries and certificates
- whether the strategy is profitable (the journal decides)

## Repository layout

```
.
├── README.md
├── AUDIT-v4.6.md                  # verification and treasury audit record
├── .gitignore                     # keeps personal state, plans, ledgers and journals out of git
└── safe-us-stock-trading/         # the skill itself
    ├── SKILL.md                   # instructions Claude follows
    └── scripts/
        ├── run_checks.py          # files, registries, tests, NYSE clock, expiry warnings
        ├── size_trade.py          # sizing, fees and every gate (price trades and T-bill funds)
        ├── portfolio_state.py     # actual vs projected portfolio, orders, risk
        ├── boycott_screen.py      # boycott status computed from per-source evidence
        ├── shariah_screen.py      # Shariah screen, purification, result provenance
        ├── sources_check.py       # source-ledger freshness and accuracy check
        ├── ledger.py              # add / list / check / drop source entries
        ├── signals.py             # long-only signals (151 Trading Strategies)
        ├── market_clock.py        # NYSE session, holidays, early closes
        ├── journal.py             # trade journal, performance report, reconcile
        ├── render_simple.py       # plain-language output; full NO BUY reasons
        ├── fees.py                # broker cost models
        ├── brokers.json           # broker fee profiles and templates
        ├── methodologies.json     # Shariah rules registry
        ├── sources.json           # ranked source registry and freshness rules
        └── test_*.py              # 395 tests
```

## Credits

- `market_clock.py` is ported from [trader-skill](https://github.com/Jakeschincariol/trader-skill) (`trader-alerts/alerts.py`), Copyright (c) Jake Schincariol, MIT License. The source rules in SKILL.md section 8 (filed numbers first, headlines are leads, filings beat headlines) follow the same practice.
- `signals.py` implements formulas from Kakushadze & Serur, *151 Trading Strategies* (2018), SSRN 3247865.

## Disclaimer

For research and education only. Not investment, tax or religious advice. Fee schedules are user-provided unless marked verified. Methodology summaries may lag provider updates; the registry and fail-safe checks reduce that risk but don't remove it. Markets can gap through stops, and losses can exceed the planned amount. Past or simulated results don't guarantee future ones.
