#!/usr/bin/env python3
"""Tests for every engine in the safe-us-stock-trading skill (v4.3). Run all checks with run_checks.py, or:
    python3 <skill_dir>/scripts/test_size_trade.py
"""
import io, json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import size_trade as _st_v48  # noqa: E402
# v4.8: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v48_mandatory.py tests them switched on.
_st_v48.SCREENS_REQUIRED = _st_v48.SOURCES_REQUIRED = _st_v48.MARKET_CLOCK_REQUIRED = False
import size_trade as st  # noqa: E402
import portfolio_state as ps  # noqa: E402
import shariah_screen as sh  # noqa: E402
import tempfile  # noqa: E402

fee = st.make_fee(0.005, 0.50, 30.0)
TECH = json.dumps({"Tech": 1.0})


# v4.3: freshness is checked against the system clock. These fixtures are dated 2026-11-05 15:30 ET,
# so the engine's clock is pinned 5 minutes after that quote for this module only.
_TEST_CLOCK = __import__("datetime").datetime(2026, 11, 5, 20, 35, tzinfo=__import__("datetime").timezone.utc)
_REAL_CLOCK = None


# The real command-line entry point (size_trade.main), run in a subprocess with the clock pinned.
PINNED_CLI = ("import sys, datetime as d; sys.path.insert(0, %r); import size_trade as s; s.SCREENS_REQUIRED = s.SOURCES_REQUIRED = s.MARKET_CLOCK_REQUIRED = False; "
              "s.CLOCK = lambda: d.datetime(2026, 11, 5, 20, 35, tzinfo=d.timezone.utc); "
              "sys.argv[0] = 'size_trade.py'; s.main(sys.argv[1:])" % os.path.dirname(os.path.abspath(__file__)))


def setUpModule():
    global _REAL_CLOCK
    import size_trade
    _REAL_CLOCK = size_trade.CLOCK
    size_trade.CLOCK = lambda: _TEST_CLOCK


def tearDownModule():
    import size_trade
    size_trade.CLOCK = _REAL_CLOCK


def run(**kw):
    base = dict(asset="stock", entry=100, stop=94, t1=112, t2=119, portfolio=10000, cash=10000,
                profile="balanced", quote_status="live", friction_bps=0, sector_weights=TECH,
                boycott_mode="off", shariah_mode="off", isin="US0000000001",
                broker="bank-al-etihad-jo", as_of="2026-11-05", ticker="ABC",
                quote_time="2026-11-05T15:30:00-05:00", quote_source="Yahoo Finance")
    if "market_price" not in kw:   # v4.3: market price from the same quote; default = the (first) entry
        tr = kw.get("tranches")
        base["market_price"] = float(tr.split(",")[0]) if tr else (kw.get("entry", base["entry"]) or None)
    base.update(kw)
    argv = []
    for k, v in base.items():
        if v is None:
            continue
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            argv.append(flag)
        else:
            argv += [flag, str(v)]
    return st.compute(st.build_parser().parse_args(argv))


def tbill(**kw):
    base = dict(asset="tbill", entry=None, stop=None, t1=None, t2=None, sector_weights=None,
                amount=2000, price=50, yield_pct=4.0, expense_ratio_pct=0.1, duration_yrs=0.15,
                hold_months=6, spread_bps=2, shariah_mode="off", market_price=50)
    base.update(kw)
    return run(**base)


class Fees(unittest.TestCase):
    def test_100_minimum(self):
        self.assertEqual(fee(100), 0.50)

    def test_6000_cap(self):
        self.assertAlmostEqual(fee(6000), 30.0)

    def test_above_6000_capped(self):
        self.assertEqual(fee(50000), 30.0)


class Sizing(unittest.TestCase):
    def test_reviewer_example(self):
        r = run()
        self.assertEqual(r["shares"], 10)
        self.assertEqual(r["downside"]["executable_stop_downside"], 69.70)

    def test_below_100_no_trade(self):
        r = run(portfolio=1000, cash=1000, profile="safe", entry=20, stop=19.5, t1=22, t2=23)
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_exactly_100(self):
        r = run(entry=100, stop=99, t1=106, t2=108, portfolio=700, cash=700, profile="aggressive")
        self.assertEqual(r["total_order_value"], 100.0)
        self.assertEqual(r["total_buy_fees"], 0.50)

    def test_stop_at_or_above_entry(self):
        self.assertEqual(run(stop=100)["verdict"], "NO TRADE")
        self.assertEqual(run(stop=105)["verdict"], "NO TRADE")

    def test_bad_targets(self):
        self.assertEqual(run(t1=120, t2=115)["verdict"], "NO TRADE")

    def test_open_risk_exhausted_combines_both_types(self):
        r = run(open_stop_risk=300, open_review_risk=300)
        self.assertIn("portfolio open-risk limit already used", r["reasons"])

    def test_cash_floor(self):
        r = run(cash=1050)
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_max_positions(self):
        self.assertIn("maximum number of stock/ETF positions reached", run(open_positions=8)["reasons"])

    def test_metal_not_counted_and_capped(self):
        r = run(asset="metal", sector_weights=None, open_positions=8, entry=300, stop=285, t1=330, t2=345)
        self.assertNotIn("maximum number of stock/ETF positions reached", r["reasons"])
        self.assertIn("metals allocation cap reached", run(asset="metal", sector_weights=None, metals_exposure=1500)["reasons"])

    def test_missing_sector_data_rejected(self):
        r = run(sector_weights=None)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("sector data missing", " ".join(r["reasons"]))

    def test_engine_error_fails_safe(self):
        self.assertEqual(run(sector_weights="{bad json")["verdict"], "NO TRADE")


class Sectors(unittest.TestCase):
    ETF = json.dumps({"Tech": 0.5, "Health": 0.3, "Energy": 0.2})

    def test_single_sector_cap_reached(self):
        r = run(portfolio_sectors=json.dumps({"Tech": 3000}))
        self.assertIn("sector cap reached: Tech", r["reasons"])

    def test_multi_sector_etf_limited_by_tightest_sector(self):
        # balanced sector cap $3,000. Tech room $500 at 50% weight -> ETF max $1,000
        r = run(asset="etf", entry=50, stop=48, t1=56, t2=60, sector_weights=self.ETF,
                portfolio_sectors=json.dumps({"Tech": 2500}))
        self.assertLessEqual(r["total_order_value"], 1000)
        self.assertLessEqual(r["projected_sector_exposure"]["Tech"], 3000)

    def test_every_projected_sector_within_cap(self):
        r = run(asset="etf", entry=50, stop=48, t1=56, t2=60, sector_weights=self.ETF,
                portfolio_sectors=json.dumps({"Health": 2800}))
        for v in r["projected_sector_exposure"].values():
            self.assertLessEqual(v, 3000)

    def test_weights_over_one_rejected(self):
        r = run(sector_weights=json.dumps({"Tech": 0.8, "Health": 0.5}))
        self.assertEqual(r["verdict"], "NO TRADE")


class Tranches(unittest.TestCase):
    def test_each_tranche_has_own_fee_and_min(self):
        r = run(tranches="100,97,94", entry=None, stop=88, t1=115, t2=125,
                horizon="long", profile="aggressive")
        self.assertEqual(r["verdict"], "TRADE")
        for t in r["tranches"]:
            self.assertGreaterEqual(t["order_value"], 100)
            self.assertAlmostEqual(t["buy_fee"], fee(t["order_value"]), places=2)

    def test_first_order_plus_commitment_equals_total(self):
        r = run(tranches="100,97,94", entry=None, stop=88, t1=115, t2=125,
                horizon="long", profile="aggressive")
        total = r["total_order_value"] + r["total_buy_fees"]
        self.assertAlmostEqual(r["cash_for_first_order"] + r["commit_for_later_tranches"], total, places=2)

    def test_reviewer_reservation_example(self):
        # $10k settled, first $1,000 tranche executed -> cash $9,000; $2,000 reserved.
        # Available for OTHER ideas = 9,000 - 2,000 - floor(1,000) = 6,000 (not 4,000).
        r = run(cash=9000, committed=2000)
        self.assertEqual(r["cash_accounting"]["available_cash"], 6000)

    def test_tranche_below_100_rejected(self):
        r = run(tranches="50,49,48", entry=None, stop=46, t1=56, t2=60,
                portfolio=1500, cash=1500, profile="aggressive")
        self.assertEqual(r["verdict"], "NO TRADE")


class Lifecycle(unittest.TestCase):
    def test_one_share_no_partial(self):
        r = run(entry=900, stop=880, t1=960, t2=990, profile="aggressive")
        self.assertEqual(r["shares"], 1)
        self.assertFalse(r["partial_exit_plan"]["feasible"])

    def test_two_exit_orders_each_pay_commission(self):
        pe = run()["partial_exit_plan"]
        self.assertAlmostEqual(pe["sell_fee_t1"], fee(560), places=2)
        self.assertAlmostEqual(pe["sell_fee_t2"], fee(595), places=2)

    def test_gap_exceeds_planned(self):
        r = run()
        self.assertGreater(r["gap_scenario"]["loss"], r["downside"]["executable_stop_downside"])

    def test_rr_below_min(self):
        self.assertEqual(run(t1=104, t2=106)["verdict"], "NO TRADE")


class RiskLabels(unittest.TestCase):
    def test_long_goes_to_review_bucket(self):
        r = run(horizon="long")
        self.assertEqual(r["downside"]["executable_stop_downside"], 0.0)
        self.assertGreater(r["downside"]["long_term_review_level_downside"], 0)
        self.assertEqual(r["portfolio_open_risk_after"]["executable_stop"], 0.0)

    def test_medium_is_hard_stop(self):
        r = run(horizon="medium")
        self.assertGreater(r["downside"]["executable_stop_downside"], 0)

    def test_unquantified_warned(self):
        self.assertTrue(any("UNQUANTIFIED" in w for w in run(unquantified_holdings=2)["warnings"]))


class Quotes(unittest.TestCase):
    def test_delayed_is_provisional_trade(self):
        r = run(quote_status="delayed", quote_delay_min=15)
        self.assertEqual(r["verdict"], "TRADE")
        self.assertTrue(r["placement_status"].startswith("provisional"))

    def test_confirmation_matching_this_order_is_ready(self):
        r = run(confirm_order="ABC|limit|100|10", stop_orders="yes")
        self.assertTrue(r["placement_status"].startswith("ready to place"))

    def test_confirmation_for_different_order_stays_provisional(self):
        self.assertTrue(run(confirm_order="ABC|limit|99|10")["placement_status"].startswith("provisional"))
        self.assertTrue(run(confirm_order="XYZ|limit|100|10")["placement_status"].startswith("provisional"))
        self.assertTrue(run(confirm_order="ABC|limit|100|9")["placement_status"].startswith("provisional"))

    def test_previous_close_watchlist(self):
        self.assertEqual(run(quote_status="previous_close")["verdict"], "WATCHLIST")

    def test_unknown_watchlist(self):
        self.assertEqual(run(quote_status="unknown")["verdict"], "WATCHLIST")


class TBills(unittest.TestCase):
    def test_tbill_respects_cash_floor(self):
        # reviewer case: $10k portfolio, $3k cash, safe floor $2k -> max ~$1k, not $2k
        r = tbill(portfolio=10000, cash=3000, profile="safe")
        self.assertLessEqual(r["order_value"] + r["buy_fee"], 1000)

    def test_tbill_no_stock_rr_rule(self):
        r = tbill()
        self.assertEqual(r["verdict"], "TRADE")
        self.assertNotIn("net_rr_of_plan", r)
        self.assertGreater(r["expected_net_return"], 0)

    def test_tbill_short_hold_uneconomic(self):
        r = tbill(hold_months=0.25, amount=200, price=50)
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_tbill_rate_shock_reported(self):
        r = tbill()
        self.assertAlmostEqual(r["rate_shock_loss"]["loss"], r["order_value"] * 0.15 * 0.01, places=2)

    def test_tbill_missing_inputs(self):
        self.assertEqual(tbill(yield_pct=None)["verdict"], "NO TRADE")

    def test_sec_yield_does_not_deduct_expense_ratio_twice(self):
        sec = tbill(yield_basis="sec", expense_ratio_pct=0.5)
        gross = tbill(yield_basis="gross", expense_ratio_pct=0.5)
        self.assertEqual(sec["expense_ratio_cost"], 0.0)
        self.assertGreater(gross["expense_ratio_cost"], 0)
        self.assertGreater(sec["expected_net_return"], gross["expected_net_return"])

    def test_tbill_blocked_in_shariah_exclude_mode(self):
        r = tbill(shariah_mode="exclude")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("interest-bearing", r["reasons"][0])


class Gates(unittest.TestCase):
    def test_boycott_excluded_blocks(self):
        self.assertEqual(run(boycott_mode="exclude", boycott_result=bres(ohchr="match"))["verdict"], "NO TRADE")

    def test_boycott_unverified_blocks(self):
        self.assertEqual(run(boycott_mode="exclude", boycott_result=bres(ohchr="unreachable"))["verdict"], "NO TRADE")

    def test_boycott_flagged_needs_acceptance(self):
        f = bres(material_israel_ops=True)
        self.assertEqual(run(boycott_mode="exclude", boycott_result=f)["verdict"], "NO TRADE")
        self.assertEqual(run(boycott_mode="exclude", boycott_result=f, accept_flagged=True)["verdict"], "TRADE")

    def test_excluded_result_blocks_in_exclude_mode(self):
        self.assertEqual(run(shariah_mode="exclude", shariah_result=sres(business="prohibited"))["verdict"], "NO TRADE")

    def test_excluded_allowed_when_mode_off(self):
        self.assertEqual(run(shariah_mode="off", shariah_result=sres(business="prohibited"))["verdict"], "TRADE")

    def test_requires_acceptance_needs_ok(self):
        f = sres(business="mixed")
        self.assertEqual(run(shariah_mode="exclude", shariah_result=f)["verdict"], "NO TRADE")
        self.assertEqual(run(shariah_mode="exclude", shariah_result=f, accept_shariah_review=True)["verdict"], "TRADE")

    def test_unverified_result_blocks(self):
        k = dict(BASE)
        del k["interest_deposits"]
        self.assertEqual(run(shariah_mode="exclude", shariah_result=sres(**{**k, "interest_deposits": None}))["verdict"],
                         "NO TRADE")

    def test_boycott_mode_off_ignores_result(self):
        self.assertEqual(run(boycott_mode="off", boycott_result=bres(ohchr="match"))["verdict"], "TRADE")


def write_json(obj):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(obj, f)
    f.close()
    return f.name


HOLD = dict(ticker="AAA", asset="stock", shares=10, avg_cost=90, price=100, level=94,
            level_type="hard", sector_weights={"Tech": 1})


def psb(state, plans=()):
    return ps.build(state, plans, fee)


class PortfolioState(unittest.TestCase):
    def test_breached_stop_is_flagged_not_negative(self):
        h = dict(HOLD, price=92)  # stop 94 is above price
        out = psb(dict(cash=5000, holdings=[h], orders=[]))
        self.assertTrue(out["reconciliation_required"])
        self.assertIn("AAA", out["actual"]["breached"])
        self.assertEqual(out["actual"]["executable_stop_downside"], 0.0)

    def test_breached_state_blocks_new_trades(self):
        out = psb(dict(cash=5000, holdings=[dict(HOLD, price=92)], orders=[]))
        r = run(state=write_json(out))
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("reconcile", r["reasons"][0])

    def test_no_level_is_unquantified(self):
        out = psb(dict(cash=5000, holdings=[dict(HOLD, level=None, level_type="none")], orders=[]))
        self.assertEqual(out["actual"]["unquantified"], ["AAA"])
        self.assertEqual(out["size_trade_args"]["unquantified_holdings"], 1)

    def test_hard_and_review_kept_separate(self):
        h2 = dict(HOLD, ticker="BBB", level_type="review")
        out = psb(dict(cash=5000, holdings=[HOLD, h2], orders=[]))
        d = 10 * 6 + fee(940)
        self.assertAlmostEqual(out["actual"]["executable_stop_downside"], d, places=2)
        self.assertAlmostEqual(out["actual"]["review_level_downside"], d, places=2)

    def test_partial_fill_commits_only_remaining_with_fee(self):
        o = dict(id="X-2", ticker="X", asset="stock", side="buy", limit=50, shares=6, status="partial", filled_shares=2)
        out = psb(dict(cash=5000, holdings=[], orders=[o]))
        self.assertAlmostEqual(out["actual"]["open_order_commitments"], 200 + fee(200), places=2)

    def test_cancelled_order_releases_cash(self):
        o = dict(id="X-3", ticker="X", asset="stock", side="buy", limit=50, shares=6, status="cancelled")
        out = psb(dict(cash=5000, holdings=[], orders=[o]))
        self.assertEqual(out["actual"]["open_order_commitments"], 0.0)

    def test_app_reserved_cash_not_double_counted(self):
        o = dict(id="X-4", ticker="X", asset="stock", side="buy", limit=50, shares=6, status="open")
        out = psb(dict(cash=5000, cash_includes_open_orders=True, holdings=[], orders=[o]))
        self.assertEqual(out["size_trade_args"]["committed"], 0.0)

    def test_small_remaining_order_warned(self):
        o = dict(id="X-5", ticker="X", asset="stock", side="buy", limit=40, shares=6, status="partial", filled_shares=4)
        out = psb(dict(cash=5000, holdings=[], orders=[o]))
        self.assertTrue(any("below the $100 minimum" in w for w in out["warnings"]))

    def test_plan_updates_projected_not_actual(self):
        state = dict(cash=10000, holdings=[], orders=[])
        plan = run()
        out = psb(state, [plan])
        self.assertEqual(out["actual"]["stock_etf_positions"], 0)
        self.assertEqual(out["projected"]["stock_etf_positions"], 1)
        self.assertEqual(out["actual"]["open_order_commitments"], 0.0)
        self.assertGreater(out["projected"]["commitments_incl_plans"], 1000)
        self.assertEqual(out["size_trade_args"]["open_positions"], 1)

    def test_cli_state_replaces_portfolio_and_cash(self):
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        state = write_json(psb(dict(cash=10000, holdings=[HOLD], orders=[])))
        out = subprocess.run([sys.executable, "-c", PINNED_CLI, "--asset", "stock",
                              "--profile", "balanced", "--quote-status", "live", "--ticker", "ABC",
                              "--boycott-mode", "off", "--shariah-mode", "off", "--as-of", "2026-11-05",
                              "--broker", "bank-al-etihad-jo", "--quote-time", "2026-11-05T15:30:00-05:00",
                              "--quote-source", "Yahoo Finance",
                              "--entry", "100", "--stop", "94", "--t1", "112", "--t2", "119",
                              "--sector-weights", TECH, "--state", state, "--market-price", "100"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout)["verdict"], "TRADE")

    def test_cli_without_state_or_cash_fails_safe(self):
        r = run(portfolio=None, cash=None)
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_state_feeds_engine(self):
        out = psb(dict(cash=10000, holdings=[HOLD], orders=[]))
        r = run(state=write_json(out))
        self.assertEqual(r["verdict"], "TRADE")
        self.assertEqual(r["limits"]["sector_room"]["Tech"], round(0.30 * 11000 - 1000, 2))


def shariah(**kw):
    argv = []
    for k, v in kw.items():
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            argv.append(flag)
        else:
            argv += [flag, str(v)]
    return sh.screen(sh.build_parser().parse_args(argv))


TODAY = "2026-11-05"
# A clean company. Every balance-sheet item collected separately.
BASE = dict(asset="stock", ticker="ABC", isin="US0000000001", entity="ABC Corp", business="permissible", as_of=TODAY, period="FY2025", data_published="2026-02-20",
            market_cap=1000, total_assets=1000, avg_market_cap_24m=1000, avg_market_cap_36m=1000,
            interest_debt=100, total_debt=100, cash=40, interest_deposits=10, interest_securities=10,
            receivables=60, nonpermissible_income=1, total_income=500, market_cap_date="2026-11-04")


def res(**kw):
    return shariah(**dict(BASE, **kw))


def bevidence(ticker="ABC", asset="stock", ohchr="no_match", bds="no_match", afsc="no_match",
              whoprofits="no_match", israel_hq=False, material_israel_ops=False, checked_on="2026-11-04", **extra):
    src = lambda f: dict(finding=f, checked_on=checked_on, url="https://example.org/source")
    ev = dict(ticker=ticker, isin="US0000000001", entity="ABC Corp", asset=asset, identity_resolved=True,
              sources=dict(ohchr=dict(src(ohchr), list_version="A/HRC/63/20"), bds=src(bds), afsc=src(afsc),
                           whoprofits=src(whoprofits),
                           sec=dict(src("no_match"), israel_hq=israel_hq, material_israel_ops=material_israel_ops)))
    ev.update(extra)
    return ev


def bres(as_of="2026-11-05", strictness="strict", **kw):
    import boycott_screen as bs
    return write_json(bs.screen(bevidence(**kw), as_of, strictness))


def sres(**kw):
    """A real screening result written to a file, as size_trade.py expects."""
    k = {x: y for x, y in dict(BASE, **kw).items() if y is not None}
    return write_json(shariah(**k))


class Registry(unittest.TestCase):
    def test_every_entry_is_sourced_versioned_dated(self):
        reg = sh.load_registry()
        for mid, m in reg["methodologies"].items():
            cur = [v for v in m["versions"] if v.get("current")]
            self.assertEqual(len(cur), 1, mid)
            for v in m["versions"]:
                self.assertTrue(v["source"].startswith("https://"), mid)
                self.assertTrue(v["verified_on"])
                for r in v["ratios"]:
                    self.assertIn(r["comparator"], ("<", "<="))

    def test_no_thresholds_in_engine_source(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "shariah_screen.py")).read()
        for literal in ("0.3333", "0.33,", "0.49", "0.70", "0.46"):
            self.assertNotIn(literal, src)

    def test_version_mismatch_disables(self):
        r = res(methodology="sp", source_version_seen="S&P Shariah Indices Methodology, January 2027")
        self.assertEqual(r["screening_result"], "INSUFFICIENT_DATA")
        self.assertEqual(r["policy_decision"], "UNVERIFIED")

    def test_stale_registry_disables(self):
        self.assertEqual(res(as_of="2027-06-01")["policy_decision"], "UNVERIFIED")

    def test_missing_as_of_disables(self):
        self.assertEqual(shariah(**{k: v for k, v in BASE.items() if k != "as_of"})["policy_decision"], "UNVERIFIED")

    def test_disabled_entry_returns_unverified(self):
        import copy
        reg = copy.deepcopy(sh.load_registry())
        reg["methodologies"]["djim"]["versions"][0]["enabled"] = False
        a = sh.build_parser().parse_args(["--asset", "stock", "--methodology", "djim", "--as-of", TODAY,
                                          "--business", "permissible"])
        self.assertEqual(sh.screen(a, reg)["policy_decision"], "UNVERIFIED")

    def test_unknown_methodology(self):
        self.assertEqual(res(methodology="ftse")["policy_decision"], "UNVERIFIED")


class BusinessAndData(unittest.TestCase):
    def test_clean_passes_every_current_method(self):
        for m in ("aaoifi", "msci", "msci-m", "sp", "djim"):
            r = res(methodology=m)
            self.assertEqual(r["screening_result"], "PASS", m)
            self.assertEqual(r["policy_decision"], "PERMITTED", m)

    def test_prohibited_business(self):
        self.assertEqual(res(business="prohibited")["policy_decision"], "EXCLUDED")

    def test_mixed_business_needs_acceptance(self):
        self.assertEqual(res(business="mixed")["policy_decision"], "REQUIRES_ACCEPTANCE")

    def test_missing_input_is_unverified(self):
        k = dict(BASE)
        del k["interest_deposits"]
        self.assertEqual(shariah(**k)["policy_decision"], "UNVERIFIED")

    def test_provenance_required(self):
        k = dict(BASE)
        del k["data_published"]
        self.assertEqual(shariah(**k)["policy_decision"], "UNVERIFIED")


class Boundaries(unittest.TestCase):
    # AAOIFI SS-21 3/4/2: "does not exceed 30%" -> 30% passes, above fails
    def test_aaoifi_exactly_30_passes(self):
        self.assertEqual(res(interest_debt=300)["screening_result"], "PASS")

    def test_aaoifi_above_30_fails(self):
        self.assertEqual(res(interest_debt=300.01)["screening_result"], "FAIL")

    def test_aaoifi_deposits_separate_from_securities(self):
        # SS-21 3/4/3 counts interest-taking deposits; securities are a separate input
        self.assertEqual(res(interest_deposits=290, interest_securities=200)["screening_result"], "PASS")
        self.assertEqual(res(interest_deposits=310)["screening_result"], "FAIL")

    def test_aaoifi_income_5pct_boundary(self):
        self.assertEqual(res(nonpermissible_income=25)["screening_result"], "PASS")       # exactly 5%
        self.assertEqual(res(nonpermissible_income=25.01)["screening_result"], "FAIL")

    def test_sp_strict_less_than_30(self):
        new = dict(methodology="sp", previous_index_status="noncompliant", consecutive_periods=0)
        self.assertEqual(res(total_debt=300, **new)["screening_result"], "FAIL")    # 30% is not < 30%
        self.assertEqual(res(total_debt=299.9, **new)["screening_result"], "PASS")

    def test_djim_cash_test_exists(self):
        r = res(methodology="djim", cash=200, interest_deposits=60, interest_securities=50,
                previous_index_status="noncompliant")   # 31%
        self.assertEqual(r["screening_result"], "FAIL")

    def test_djim_has_no_receivables_test(self):
        r = res(methodology="djim", receivables=900)
        self.assertNotIn("receivables", " ".join(r["ratios"]))
        self.assertEqual(r["screening_result"], "PASS")

    def test_income_not_subject_to_buffer(self):
        r = res(methodology="sp", nonpermissible_income=26, previous_index_status="compliant")   # 5.2%
        self.assertEqual(r["screening_result"], "FAIL")


class HistoricalVersions(unittest.TestCase):
    def test_sp_2023_vs_current(self):
        k = dict(methodology="sp", total_debt=315, previous_index_status="noncompliant")   # 31.5%
        self.assertEqual(res(**k)["screening_result"], "FAIL")
        old = res(version="S&P Shariah Indices Methodology, 2023 (leverage only)", **k)
        self.assertEqual(old["screening_result"], "PASS")

    def test_djim_2023_had_no_cash_test(self):
        old = res(methodology="djim", version="Dow Jones Islamic Market Indices Methodology, 2023 (leverage only)",
                  cash=400)
        self.assertNotIn("cash", old["ratios"])


class EntryRetention(unittest.TestCase):
    # MSCI Index Series May 2025: receivables+cash entry 46%, threshold 70%
    def test_msci_entry_ineligible_is_not_a_prohibition(self):
        r = res(methodology="msci", receivables=500)    # (500+40+10)/1000 = 55%
        self.assertEqual(r["screening_result"], "PASS")
        self.assertEqual(r["index_entry"], "INELIGIBLE")
        self.assertEqual(r["policy_decision"], "REQUIRES_ACCEPTANCE")

    def test_msci_existing_retained(self):
        r = res(methodology="msci", receivables=500, existing_holding=True)
        self.assertEqual(r["retention"], "RETAINED")
        self.assertEqual(r["index_entry"], "NOT_APPLICABLE")

    def test_msci_over_70_fails(self):
        self.assertEqual(res(methodology="msci", receivables=700)["screening_result"], "FAIL")

    def test_msci_m_49_threshold(self):
        self.assertEqual(res(methodology="msci-m", receivables=450)["screening_result"], "FAIL")   # 50%

    def test_msci_exit_buffer_zone(self):
        r = res(methodology="msci", total_debt=340, existing_holding=True)   # 34%
        self.assertEqual(r["screening_result"], "BORDERLINE")
        self.assertEqual(r["retention"], "UNKNOWN")
        self.assertEqual(res(methodology="msci", total_debt=360, existing_holding=True)["screening_result"], "FAIL")

    # S&P / DJIM: 2-point buffer, 3 consecutive periods
    def test_sp_compliant_inside_buffer_retained(self):
        r = res(methodology="sp", total_debt=310, existing_holding=True,
                previous_index_status="compliant", consecutive_periods=1)
        self.assertEqual(r["screening_result"], "BORDERLINE")
        self.assertEqual(r["retention"], "RETAINED")

    def test_sp_three_breaches_removed(self):
        r = res(methodology="sp", total_debt=310, existing_holding=True,
                previous_index_status="compliant", consecutive_periods=3)
        self.assertEqual(r["retention"], "REMOVAL_CONDITION_MET")
        self.assertEqual(r["policy_decision"], "EXCLUDED")

    def test_sp_above_buffer_immediate_fail(self):
        r = res(methodology="sp", total_debt=325, existing_holding=True, previous_index_status="compliant")
        self.assertEqual(r["screening_result"], "FAIL")

    def test_djim_previously_noncompliant_needs_three_passes(self):
        k = dict(methodology="djim", interest_debt=290, previous_index_status="noncompliant")   # 29%
        self.assertEqual(res(consecutive_periods=1, **k)["index_entry"], "INELIGIBLE")
        self.assertEqual(res(consecutive_periods=3, **k)["index_entry"], "ELIGIBLE")

    def test_unknown_history_in_buffer_needs_acceptance(self):
        r = res(methodology="djim", interest_debt=290)
        self.assertEqual(r["index_entry"], "UNKNOWN")
        self.assertEqual(r["policy_decision"], "REQUIRES_ACCEPTANCE")


class InternalMargin(unittest.TestCase):
    def test_margin_is_labelled_internal(self):
        r = res(interest_debt=280)   # 28% vs 30%
        self.assertEqual(r["screening_result"], "PASS")
        self.assertTrue(r["internal_policy_flags"])
        self.assertIn("internal policy", r["internal_policy_flags"][0])
        self.assertEqual(r["policy_decision"], "REQUIRES_ACCEPTANCE")

    def test_margin_can_be_disabled(self):
        self.assertEqual(res(interest_debt=280, internal_margin=0)["policy_decision"], "PERMITTED")


PUR = dict(nonpermissible_income=47e6, total_income=2e9, shares_outstanding=1.04e9, shares_held=1000,
           market_cap=1e10, total_assets=1e10, avg_market_cap_24m=1e10, avg_market_cap_36m=1e10,
           interest_debt=1e9, total_debt=1e9, cash=1e8, interest_deposits=1e8, interest_securities=1e8, receivables=1e8)


class Purification(unittest.TestCase):
    def test_aaoifi_attributable_usd(self):
        p = res(held_at_period_end="yes", **PUR)["purification"]
        self.assertEqual(p["status"], "DUE")
        self.assertAlmostEqual(p["amount_usd"], 45.20, places=2)   # v4.8: exact 45.19x, charity owed rounds UP
        self.assertEqual(p["period"], "FY2025")
        self.assertIn("3/4/6", p["method"])

    def test_aaoifi_due_without_dividend(self):
        self.assertEqual(res(held_at_period_end="yes", **PUR)["purification"]["status"], "DUE")

    def test_aaoifi_sold_before_period_end(self):
        p = res(held_at_period_end="no", **PUR)["purification"]
        self.assertEqual((p["status"], p["amount_usd"]), ("NOT DUE", 0.0))

    def test_missing_inputs_never_estimated(self):
        p = res(**PUR)["purification"]   # held_at_period_end missing
        self.assertEqual(p["status"], "UNAVAILABLE")
        self.assertNotIn("amount_usd", p)

    def test_index_dividend_method_usd(self):
        p = res(methodology="sp", dividend_per_share=0.5, dividends_count=4, **PUR)["purification"]
        self.assertAlmostEqual(p["amount_usd"], 0.5 * 4 * 1000 * (47e6 / 2e9), places=2)

    def test_index_method_missing_dividend_unavailable(self):
        self.assertEqual(res(methodology="sp", **PUR)["purification"]["status"], "UNAVAILABLE")

    def test_fund_level_purification_not_double_counted(self):
        p = res(held_at_period_end="yes", fund_purifies="yes", **PUR)["purification"]
        self.assertEqual((p["status"], p["amount_usd"]), ("NOT DUE", 0.0))


class Metals(unittest.TestCase):
    ALL_YES = dict(asset="metal", metal_structure="physical", allocated="yes", ownership_rights="yes",
                   spot_settlement="yes", no_lending="yes")

    def test_allocation_alone_is_not_enough(self):
        r = shariah(asset="metal", metal_structure="physical", allocated="yes")
        self.assertEqual(r["policy_decision"], "UNVERIFIED")

    def test_verified_structure_without_certificate_needs_acceptance(self):
        self.assertEqual(shariah(**self.ALL_YES)["policy_decision"], "REQUIRES_ACCEPTANCE")

    def test_verified_and_certified_permitted(self):
        r = shariah(**dict(self.ALL_YES, certifier="Board X", certificate_date="2026-06-01",
                           certificate_url="https://example.org/cert", as_of=TODAY))
        self.assertEqual(r["policy_decision"], "PERMITTED")

    def test_lending_fails(self):
        self.assertEqual(shariah(**dict(self.ALL_YES, no_lending="no"))["policy_decision"], "EXCLUDED")

    def test_futures_fail(self):
        self.assertEqual(shariah(asset="metal", metal_structure="futures")["policy_decision"], "EXCLUDED")


class OtherProducts(unittest.TestCase):
    def test_tbill_excluded(self):
        self.assertEqual(shariah(asset="tbill")["policy_decision"], "EXCLUDED")

    def test_certified_etf_needs_board_and_date(self):
        self.assertEqual(shariah(asset="etf-certified", certifier="Board X")["policy_decision"], "UNVERIFIED")
        r = shariah(asset="etf-certified", certifier="Board X", certificate_date="2026-03-01",
                    certificate_url="https://example.org/cert", as_of=TODAY)
        self.assertEqual(r["policy_decision"], "PERMITTED")
        self.assertIn("boycott", r["boycott_note"])


class CombinedGates(unittest.TestCase):
    def test_both_pass(self):
        self.assertEqual(run(shariah_mode="exclude", shariah_result=sres())["verdict"], "TRADE")

    def test_boycott_blocks_even_if_shariah_permitted(self):
        r = run(boycott_mode="exclude", boycott_result=bres(bds="match"), shariah_mode="exclude", shariah_result=sres())
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_shariah_blocks_even_if_boycott_clear(self):
        r = run(shariah_mode="exclude", shariah_result=sres(business="prohibited"))
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_both_reasons_reported(self):
        r = run(boycott_mode="exclude", shariah_mode="exclude")
        self.assertEqual(len([x for x in r["reasons"] if "screen" in x]), 2)


class Provenance(unittest.TestCase):
    def test_no_result_file_blocks(self):
        r = run(shariah_mode="exclude")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("no --shariah-result", r["reasons"][0])

    def test_typed_verdict_is_not_an_option(self):
        import contextlib
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            st.build_parser().parse_args(["--asset", "stock", "--profile", "safe", "--quote-status", "live",
                                          "--boycott-mode", "off", "--shariah-mode", "exclude",
                                          "--shariah-policy", "permitted"])

    def test_ticker_mismatch_rejected(self):
        r = run(shariah_mode="exclude", shariah_result=sres(ticker="XYZ"))
        self.assertIn("not ABC", " ".join(r["reasons"]))

    def test_expired_result_rejected(self):
        r = run(shariah_mode="exclude", shariah_result=sres(), as_of="2027-03-01")
        self.assertIn("expired", " ".join(r["reasons"]))

    def test_tampered_fingerprint_rejected(self):
        d = shariah(**BASE)
        d["rule_fingerprint"] = "0" * 64
        r = run(shariah_mode="exclude", shariah_result=write_json(d))
        self.assertIn("fingerprint", " ".join(r["reasons"]))

    def test_hand_edited_verdict_rejected_by_recomputation(self):
        d = shariah(**dict(BASE, interest_debt=400))   # 40% debt: FAIL under AAOIFI
        self.assertEqual(d["policy_decision"], "EXCLUDED")
        d["policy_decision"] = "PERMITTED"            # only the verdict is edited; schema left intact
        d["screening_result"] = "PASS"
        r = run(shariah_mode="exclude", shariah_result=write_json(d))
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("recomputation", " ".join(r["reasons"]))

    def test_untouched_result_passes_recomputation(self):
        self.assertEqual(sh.recompute(shariah(**BASE)), [])

    def test_inputs_ticker_must_match(self):
        d = shariah(**BASE)
        d["inputs"]["ticker"] = "OTHER"
        r = run(shariah_mode="exclude", shariah_result=write_json(d))
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_integrity_wording_is_honest(self):
        self.assertIn("does not prove", shariah(**BASE)["integrity"])

    def test_historical_version_result_rejected(self):
        f = sres(methodology="sp", version="S&P Shariah Indices Methodology, 2023 (leverage only)",
                 previous_index_status="compliant")
        r = run(shariah_mode="exclude", shariah_result=f)
        self.assertIn("historical", " ".join(r["reasons"]))

    def test_identity_required(self):
        r = res(isin=None) if False else shariah(**{k: v for k, v in BASE.items() if k != "isin"})
        self.assertEqual(r["policy_decision"], "UNVERIFIED")

    def test_result_carries_provenance(self):
        r = res()
        for k in ("schema", "ticker", "isin", "entity", "methodology", "rule_fingerprint", "as_of", "expires_on"):
            self.assertTrue(r.get(k), k)
        self.assertEqual(r["data"]["period"], "FY2025")

    def test_valid_result_summary_in_plan(self):
        r = run(shariah_mode="exclude", shariah_result=sres())
        self.assertEqual(r["shariah"]["policy_decision"], "PERMITTED")
        self.assertEqual(r["shariah"]["validation"], ["valid"])


class RegistryValidation(unittest.TestCase):
    def _reg(self):
        import copy
        return copy.deepcopy(sh.load_registry())

    def test_bad_comparator_rejected(self):
        reg = self._reg()
        reg["methodologies"]["aaoifi"]["versions"][0]["ratios"][0]["comparator"] = "<<"
        with self.assertRaises(ValueError):
            sh.validate_registry(reg)

    def test_threshold_out_of_range_rejected(self):
        reg = self._reg()
        reg["methodologies"]["msci"]["versions"][0]["ratios"][0]["threshold"] = 33.33
        with self.assertRaises(ValueError):
            sh.validate_registry(reg)

    def test_two_current_versions_rejected(self):
        reg = self._reg()
        reg["methodologies"]["sp"]["versions"][1]["current"] = True
        with self.assertRaises(ValueError):
            sh.validate_registry(reg)

    def test_invalid_registry_file_gives_unverified(self):
        reg = self._reg()
        reg["methodologies"]["aaoifi"]["versions"][0]["source"] = "ftp://x"
        path = write_json(reg)
        r = shariah(**dict(BASE, registry=path))
        self.assertEqual(r["policy_decision"], "UNVERIFIED")
        self.assertIn("registry invalid", r["reasons"][0])

    def test_equivalent_version_accepted(self):
        reg = self._reg()
        reg["methodologies"]["msci"]["versions"][0]["equivalent_versions"] = ["MSCI Islamic Index Series Methodology, July 2025"]
        a = sh.build_parser().parse_args(sum([[f"--{k.replace('_', '-')}", str(v)] for k, v in
                                              dict(BASE, methodology="msci",
                                                   source_version_seen="MSCI Islamic Index Series Methodology, July 2025").items()], []))
        self.assertEqual(sh.screen(a, reg)["screening_result"], "PASS")

    def test_fingerprint_changes_with_rules(self):
        reg = self._reg()
        v = reg["methodologies"]["djim"]["versions"][0]
        before = sh.fingerprint(v)
        v["ratios"][0]["threshold"] = 0.31
        self.assertNotEqual(before, sh.fingerprint(v))


class Brokers(unittest.TestCase):
    def test_no_fee_schedule_is_no_trade(self):
        r = run(broker=None)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("fee schedule", r["reasons"][0])

    def test_template_rejected(self):
        self.assertEqual(run(broker="template-percent")["verdict"], "NO TRADE")

    def test_unknown_broker_rejected(self):
        self.assertEqual(run(broker="nope")["verdict"], "NO TRADE")

    def test_min_order_from_profile(self):
        r = run()
        self.assertEqual(r["broker"], "Bank al Etihad (Jordan) app, US stocks")

    def test_per_share_model(self):
        import fees
        f = fees.make_fee_model(dict(model="per_share", per_share=0.005, min=1.0, max_pct=0.01))
        self.assertEqual(f(1000, 100), 1.0)          # 0.50 -> min 1.00
        self.assertAlmostEqual(f(50000, 1000), 5.0)   # 1000 x 0.005
        self.assertAlmostEqual(f(50, 10000), 0.5)     # capped at 1% of value

    def test_flat_and_zero_models(self):
        import fees
        self.assertEqual(fees.make_fee_model(dict(model="flat", flat=4.95))(10000, 10), 4.95)
        self.assertEqual(fees.make_fee_model(dict(model="zero"))(10000, 10), 0.0)

    def test_custom_fee_model_cli(self):
        r = run(broker=None, fee_model="flat", fee_flat=1.0, entry=50, stop=48, t1=56, t2=60)
        self.assertEqual(r["verdict"], "TRADE")
        self.assertEqual(r["total_buy_fees"], 1.0)

    def test_incomplete_custom_model_rejected(self):
        self.assertEqual(run(broker=None, fee_model="percent", fee_rate=0.01)["verdict"], "NO TRADE")

    def test_zero_fee_broker_changes_rr(self):
        a = run(t1=104, t2=106)["verdict"]
        b = run(broker=None, fee_model="zero", friction_bps=0, t1=104, t2=106)
        self.assertEqual(a, "NO TRADE")
        self.assertNotEqual(b["net_rr_of_plan"], None)


class UnquantifiedRisk(unittest.TestCase):
    def test_blocks_without_assumption(self):
        r = run(unquantified_holdings=1, unquantified_value=2000)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("unquantified", r["reasons"][0])

    def test_allowed_with_conservative_assumption(self):
        r = run(unquantified_holdings=1, unquantified_value=2000, unquantified_loss_pct=20)
        self.assertEqual(r["verdict"], "TRADE")
        self.assertTrue(any("assumed 20" in w for w in r["warnings"]))

    def test_assumption_consumes_open_risk(self):
        r = run(unquantified_holdings=1, unquantified_value=3000, unquantified_loss_pct=20)   # $600 = full 6%
        self.assertEqual(r["verdict"], "NO TRADE")

    def test_state_counts_breached_as_unquantified(self):
        out = psb(dict(cash=5000, holdings=[dict(HOLD, price=92)], orders=[]))
        self.assertEqual(out["size_trade_args"]["unquantified_value"], 920.0)


class SimpleOutput(unittest.TestCase):
    def test_numbers_copied_verbatim(self):
        import render_simple as rs
        d = run(confirm_order="ABC|limit|100|10")
        text = rs.render([d], market="calm")
        self.assertIn("BUY ABC", text)
        self.assertIn("PRICE 100.00 (LIMIT)", text)
        self.assertIn(f"PLANNED LOSS AT STOP ${d['downside']['executable_stop_downside']:,.2f}", text)
        self.assertNotIn("MAX LOSS", text)
        self.assertIn("STOP 94.00", text)
        self.assertIn("SELL 5 AT 112.00", text)
        self.assertIn("MARKET: CALM", text)
        self.assertIn("NOT ADVICE", text)

    def test_no_trade_and_watchlist_lines(self):
        import render_simple as rs
        text = rs.render([run(boycott_mode="exclude", boycott_result=bres(ohchr="match")),
                          run(quote_status="previous_close")])
        self.assertIn("NO BUY ABC\n  WHY: COMPANY IS ON A BOYCOTT LIST.", text)   # v4.8: full reason
        self.assertIn("FOUND ON: OHCHR", text)
        self.assertIn("FIX: NONE. SKIP IT.", text)
        self.assertIn("(ENGINE: boycott screen: excluded", text)
        self.assertIn("WAIT ABC", text)
        self.assertIn("NO BUY TODAY", text)

    def test_long_term_says_review_not_stop(self):
        import render_simple as rs
        text = rs.render([run(horizon="long")])
        self.assertIn("REVIEW IF BELOW 94.00 (NOT AUTO SELL)", text)

    def test_charity_line(self):
        import render_simple as rs
        f = sres(nonpermissible_income=1, shares_outstanding=100, shares_held=10, held_at_period_end="yes")
        text = rs.render([run(shariah_mode="exclude", shariah_result=f)])
        self.assertIn("HALAL: OK", text)
        self.assertIn("GIVE $0.10 TO CHARITY (FY2025)", text)


class Checks(unittest.TestCase):
    def test_run_checks_validates_files(self):
        import subprocess
        here = os.path.dirname(os.path.abspath(__file__))
        outp = subprocess.run([sys.executable, os.path.join(here, "run_checks.py"), "--no-tests"],
                              capture_output=True, text=True)
        self.assertEqual(outp.returncode, 0, outp.stdout + outp.stderr)
        rep = json.loads(outp.stdout)
        self.assertTrue(rep["registry"]["valid"])
        self.assertIn("bank-al-etihad-jo", rep["brokers"]["profiles"])


class ReferenceCases(unittest.TestCase):
    """Independent hand calculations (0.5% commission, min $0.50, max $30; no friction)."""

    def test_reviewer_reference_trade(self):
        r = run(friction_bps=0)
        # buy 10 x 100 = 1000 (fee 5.00); stop 10 x 94 = 940 (fee 4.70)
        self.assertAlmostEqual(r["downside"]["executable_stop_downside"], 1000 + 5.00 - (940 - 4.70), places=2)
        # sell 5 x 112 = 560 (fee 2.80); sell 5 x 119 = 595 (fee 2.975)
        expected = (560 - 2.80) + (595 - 2.975) - (1000 + 5.00)
        self.assertAlmostEqual(r["partial_exit_plan"]["combined_net_profit"], expected, delta=0.006)

    def test_render_matches_engine_exactly(self):
        import render_simple as rs
        r = run(friction_bps=0)
        text = rs.render([r])
        self.assertIn(f"PROFIT IF BOTH HIT ${r['partial_exit_plan']['combined_net_profit']:,.2f}", text)
        self.assertIn("PLANNED LOSS AT STOP $69.70", text)


class StopAfterT1(unittest.TestCase):
    def test_stop_never_lowered(self):
        st_ = run()["partial_exit_plan"]["stop_after_t1"]
        self.assertEqual(st_["keep_at_least"], 94)
        if st_["optional_raise_to"] is not None:
            self.assertGreater(st_["optional_raise_to"], 94)

    def test_raise_level_is_remaining_position_breakeven(self):
        pe = run()["partial_exit_plan"]
        self.assertGreater(pe["remaining_position_breakeven"], 100)          # above entry, includes fees
        self.assertEqual(pe["stop_after_t1"]["optional_raise_to"], pe["remaining_position_breakeven"])

    def test_whole_trade_breakeven_is_information_only(self):
        pe = run()["partial_exit_plan"]
        self.assertLess(pe["whole_trade_breakeven_after_t1"], 94)          # the old, wrong "stop"
        self.assertIn("NOT a stop", pe["whole_trade_note"])

    def test_render_never_suggests_lower_stop(self):
        import render_simple as rs
        text = rs.render([run()])
        self.assertIn("KEEP STOP 94.00. NEVER LOWER.", text)
        self.assertNotIn("MOVE STOP TO 90", text)


class FeeUnits(unittest.TestCase):
    def test_percent_written_as_percent_rejected(self):
        import fees
        with self.assertRaises(ValueError):
            fees.make_fee_model(dict(model="percent", rate=0.5, min=0.5, max=30))

    def test_cli_percent_mistake_is_no_trade(self):
        r = run(broker=None, fee_model="percent", fee_rate=0.5, fee_min=0.5, fee_max=30)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("looks like a percent", r["reasons"][0])

    def test_separate_sell_schedule(self):
        import fees
        f = fees.make_fee_model(dict(model="zero", sell=dict(model="flat", flat=2.0)))
        self.assertEqual(f(1000, 10, side="buy"), 0.0)
        self.assertEqual(f(1000, 10, side="sell"), 2.0)

    def test_fx_cost_both_sides_when_converting(self):
        import fees
        f = fees.make_fee_model(dict(model="zero", fx_pct=0.002), convert=True)
        self.assertAlmostEqual(f(1000, 10), 2.0)
        self.assertAlmostEqual(f(1000, 10, side="sell"), 2.0)

    def test_no_phantom_fx_without_conversion(self):
        import fees
        self.assertEqual(fees.make_fee_model(dict(model="zero", fx_pct=0.002))(1000, 10), 0.0)

    def test_zero_commission_still_has_friction(self):
        r = run(broker=None, fee_model="zero", friction_bps=5)
        self.assertGreater(r["downside"]["executable_stop_downside"], 10 * (100 - 94))


class QuoteProvenance(unittest.TestCase):
    def test_missing_quote_time_is_watchlist(self):
        r = run(quote_time="")
        self.assertEqual(r["verdict"], "WATCHLIST")

    def test_delayed_needs_stated_delay(self):
        self.assertEqual(run(quote_status="delayed")["verdict"], "WATCHLIST")
        self.assertEqual(run(quote_status="delayed", quote_delay_min=45)["verdict"], "WATCHLIST")
        self.assertEqual(run(quote_status="delayed", quote_delay_min=15)["verdict"], "TRADE")

    def test_live_is_still_provisional_until_app_check(self):
        self.assertTrue(run()["placement_status"].startswith("provisional"))

    def test_render_shows_quote_and_profile(self):
        import render_simple as rs
        text = rs.render([run(quote_status="delayed", quote_delay_min=15)])
        self.assertIn("RISK: BALANCED. HOLD: SHORT.", text)
        self.assertIn("PRICE SEEN 2026-11-05T15:30:00-05:00 (DELAYED 15M, Yahoo Finance) PRICE 100.00", text)
        self.assertIn("GOOD ONLY FOR THIS PRICE", text)       # v4.3: no "next session" promise


class TBillShariahModes(unittest.TestCase):
    def test_exclude_blocks(self):
        self.assertEqual(tbill(shariah_mode="exclude")["verdict"], "NO TRADE")

    def test_flag_allows_with_warning(self):
        r = tbill(shariah_mode="flag")
        self.assertEqual(r["verdict"], "TRADE")
        self.assertTrue(any("Shariah flag" in w for w in r["warnings"]))

    def test_flag_shown_in_simple_output(self):
        import render_simple as rs
        self.assertIn("HALAL: NO (INTEREST)", rs.render([tbill(shariah_mode="flag")]))

    def test_off_no_warning(self):
        self.assertFalse(any("Shariah" in w for w in tbill(shariah_mode="off")["warnings"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
