# safe-us-stock-trading v4.8: verification and treasury audit

**Date:** 2026-11-09 · **Scope:** the whole skill (SKILL.md and every script) · **Result:** all money figures independently confirmed to the cent; every control tested; 59 findings fixed across four review rounds; 412 tests passing.

This is research software. Nothing here means the skill makes money: that can only be shown by the trade journal over 20+ closed trades (section 8c of SKILL.md).

## 1. How it was verified

| Round | Who | Method | Findings fixed |
|---|---|---|---|
| Code review | Independent agent, not shown the author's reasoning | Read the v4.8 code, reproduced each defect by running it | 10 |
| End-to-end run | Author | Ran the documented workflow through the real command-line tools | 4 |
| Adversarial audit | Second independent agent | Tried to get a TRADE while breaking each promised rule; doc/code consistency; crashes | 15 + 2 from the author's own run |
| Treasury audit | Third independent agent (blind recomputation) + author (controls) | Rebuilt the money math from the written rules before reading the engine; tested controls | 5 |

Every finding has a regression test in `scripts/test_v48_mandatory.py` (or the older suites), so it can't return unnoticed.

## 2. Money math: independent recomputation

Calculator built from the written rules only (Decimal arithmetic), then compared with the engine.

| Area | Cases | Result |
|---|---|---|
| Stock/ETF sizing and plan figures (shares, every fee, planned loss, gap loss, breakevens, exit plan, R:R, fee check, cash for first order, later tranches, dividends) | 760 random plans, ~20,300 field comparisons | **PASS**: 0 differences over $0.005; share count is the true maximum in 760/760 (n+1 always breaks a limit) |
| T-bill funds (shares, fees, spread, income, net return, breakeven days, rate shock) | 50 | **PASS** |
| Portfolio chain (open, partial and sell orders; app reserves cash or not; plan 2 sized against plan 1's reservation) | 2-plan chain, both cash modes | **PASS**: reserved cash never counted twice; plan 2 = 26 shares vs 112 if sized against the unprojected state |
| Trade journal (split buys, partial fills, partial sells, fees, charity) | 30 trades | **PASS**: P&L equals the sum of cash flows to the cent |
| Purification | AAOIFI and index methods, hand-checked | **PASS** |

## 3. Controls tested

| Control | Test | Result |
|---|---|---|
| No order placement | Searched all scripts for network, broker and process calls | **PASS**: none; URL text parsing only |
| Order confirmation | Exact ticker, limit type, price and shares required; tried 4 mismatches × 2 stop settings | **PASS**: only the exact match is "ready" |
| Pre-trade limits | 35 single-rule breaches, 1,500 random combinations, 4,000 random plans | **PASS**: no TRADE broke a rule; no crash |
| Reconciliation with the app | Oversells, overfills, unknown status, negative cash, breached holdings | **PASS** after fixes (duplicate rows and order ids now rejected) |
| Journal vs app | `journal.py reconcile` compares open positions with the app's shares | **Added** in this audit |
| Audit trail | Plans record quote time/source, fee-schedule source, screen provenance, source ledger; journal stores a SHA-256 of each plan, broker, fee source, placement status, time | **PASS** after adding the journal fields |
| Output fidelity | Every $ amount in the simple output traced to the engine's JSON | **PASS** |
| Data freshness and source quality | Ranked source registry, freshness rules, price cross-check, expiry warnings | **PASS** |
| Tampering | Edited verdicts, expiry dates, signals, asset labels | **PASS**: refused (recomputed, not trusted) |

## 4. Treasury findings fixed in this audit

1. **Open risk on unfilled buy orders left out the buy fee** (understated by the pending fees; e.g. $84.60 shown vs $89.60 true). Fixed: the unpaid buy fee is now part of the pending loss.
2. **Displayed losses rounded to the nearest cent** (e.g. $99.405 shown as $99.40). Fixed: losses and costs now round **up**, profits **down**. The gates always used unrounded values, so share counts never changed.
3. **Charity (purification) rounded to the nearest cent**, which could underpay by half a cent. Fixed: always rounds up.
4. **Duplicate holding rows were accepted and doubled the position** (inflating portfolio value and every limit computed from it). Fixed: duplicates rejected; duplicate order ids too.
5. **Unverified fee schedule not shown to the user.** Fixed: every plan prints "FEE SCHEDULE: USER-PROVIDED, NOT VERIFIED" until the broker profile is verified.

## 5. Open items (not fixable in code)

| Item | Why it matters | What to do |
|---|---|---|
| Bank al Etihad fee profile is user-provided | Every fee and limit depends on it | Check against the bank's published tariff; then set `verified_source` |
| Broker fee rounding | The engine charges exact fees; a broker may round each fee up to the cent | Compare a real fill's fee with the plan |
| Forged inputs | Result files are recomputed from their recorded inputs; a file whose inputs were also forged is not detected | Treat files as your own records; never edit them |
| Dividend withholding rate | User-provided (30% without a US tax treaty; Jordan not found in the US treaty tables) | Confirm with a current IRS source or a tax adviser |
| Profitability | Untested | Paper trade and log ≥ 20 closed trades in the journal |
| Specialist review | Shariah methodology summaries and certificates are checked for structure, not religious correctness | Have a qualified scholar review the methodology registry |

## 6. Engine choices more conservative than the written rules

- A 1-share plan has a single exit at T1 (lower R:R than a split exit).
- Tranches below the $100 minimum order give NO TRADE instead of merging into one order.
- Extra gates: maximum stop distance, total open-risk limit, maximum positions, T-bill cap.
- Sell orders don't reduce a ticker's exposure until they fill.
