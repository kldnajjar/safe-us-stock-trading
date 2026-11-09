#!/usr/bin/env python3
"""v4.3 policy tests: system-clock freshness, replay mode, market-price/entry gate, stop-order
capability, flag-mode SCREEN NOT RUN, FX only on conversion, certificate and market-cap dates
re-checked at trade time, and conditional WATCHLIST plans in the simple output."""
import datetime as dt, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import size_trade as _st_v48  # noqa: E402
# v4.8: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v48_mandatory.py tests them switched on.
_st_v48.SCREENS_REQUIRED = _st_v48.SOURCES_REQUIRED = _st_v48.MARKET_CLOCK_REQUIRED = False
import render_simple as rs  # noqa: E402
import shariah_screen as sh  # noqa: E402
import size_trade as st  # noqa: E402

CLOCK = dt.datetime(2026, 11, 5, 20, 35, tzinfo=dt.timezone.utc)
QT = "2026-11-05T15:30:00-05:00"          # 20:30Z, 5 minutes before CLOCK
_real = None


def setUpModule():
    global _real
    _real, st.CLOCK = st.CLOCK, (lambda: CLOCK)


def tearDownModule():
    st.CLOCK = _real


def trade(**kw):
    base = dict(asset="stock", ticker="ABC", isin="US0000000001", profile="balanced", horizon="short",
                portfolio=10000, cash=10000, entry=100, stop=94, t1=112, t2=119, market_price=100,
                sector_weights='{"Tech": 1}', quote_status="live", quote_time=QT, quote_source="Test feed",
                as_of="2026-11-05", broker="bank-al-etihad-jo", boycott_mode="off", shariah_mode="off")
    base.update(kw)
    argv = []
    for k, v in base.items():
        if v is None or v is False:
            continue
        argv += [f"--{k.replace('_', '-')}"] + ([] if v is True else [str(v)])
    return st.compute(st.build_parser().parse_args(argv))


def screen(**kw):
    base = dict(asset="stock", ticker="ABC", isin="US0000000001", entity="ABC Corp", business="permissible",
                as_of="2026-11-05", period="FY2025", data_published="2026-02-20", market_cap=1000,
                total_assets=1000, avg_market_cap_24m=1000, avg_market_cap_36m=1000, interest_debt=100,
                total_debt=100, cash=40, interest_deposits=10, interest_securities=10, receivables=60,
                nonpermissible_income=1, total_income=500, market_cap_date="2026-11-04")
    base.update(kw)
    argv = sum([[f"--{k.replace('_', '-')}", str(v)] for k, v in base.items() if v is not None], [])
    return sh.screen(sh.build_parser().parse_args(argv))


def at(minutes_before_clock):
    return (CLOCK - dt.timedelta(minutes=minutes_before_clock)).isoformat()


class ClockAndQuotes(unittest.TestCase):
    def test_baseline_trades(self):
        self.assertEqual(trade()["verdict"], "TRADE")

    def test_live_age_limit_is_15_minutes(self):
        self.assertEqual(trade(quote_time=at(14))["verdict"], "TRADE")
        r = trade(quote_time=at(16))
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("minutes old", " ".join(r["reasons"]))

    def test_delayed_age_limit_is_delay_plus_15(self):
        self.assertEqual(trade(quote_status="delayed", quote_delay_min=15, quote_time=at(29))["verdict"], "TRADE")
        self.assertEqual(trade(quote_status="delayed", quote_delay_min=15, quote_time=at(31))["verdict"], "WATCHLIST")

    def test_future_quote(self):
        self.assertEqual(trade(quote_time=at(-4))["verdict"], "TRADE")        # clock skew tolerance
        self.assertEqual(trade(quote_time=at(-30))["verdict"], "WATCHLIST")

    def test_as_of_must_be_today(self):
        self.assertEqual(trade(as_of="2026-11-06")["verdict"], "TRADE")       # one-day timezone tolerance
        r = trade(as_of="2026-11-03")
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("not today", " ".join(r["reasons"]))

    def test_replay_is_never_executable(self):
        r = trade(now="2026-11-05T20:31:00+00:00")
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("replay", " ".join(r["reasons"]))
        r = trade(as_of="2020-01-01", quote_time="2020-01-01T15:30:00-05:00", now="2020-01-01T20:31:00+00:00")
        self.assertEqual(r["verdict"], "WATCHLIST")

    def test_tbill_uses_same_clock(self):
        r = trade(asset="tbill", entry=None, stop=None, t1=None, t2=None, sector_weights=None, market_price=None,
                  amount=2000, price=50, yield_pct=4, duration_yrs=0.15, hold_months=6, quote_time=at(60))
        self.assertEqual(r["verdict"], "WATCHLIST")


class MarketPrice(unittest.TestCase):
    def test_missing_market_price_is_watchlist(self):
        r = trade(market_price=None)
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("--market-price", " ".join(r["reasons"]))

    def test_entry_at_most_one_percent_above_market(self):
        self.assertEqual(trade(market_price=99.01)["verdict"], "TRADE")
        r = trade(market_price=98.9)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("above the market price", " ".join(r["reasons"]))

    def test_entry_below_market_is_a_pullback_limit(self):
        self.assertEqual(trade(market_price=103)["verdict"], "TRADE")

    def test_market_at_or_below_stop_is_broken_setup(self):
        r = trade(market_price=94, entry=94.5, stop=94)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("at or below the stop", " ".join(r["reasons"]))

    def test_every_tranche_checked(self):
        r = trade(entry=None, tranches="102,99,97", stop=96, market_price=100)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("above the market price", " ".join(r["reasons"]))
        self.assertEqual(trade(entry=None, tranches="101,99,98", stop=95, market_price=100)["verdict"], "TRADE")

    def test_market_price_must_be_positive(self):
        self.assertEqual(trade(market_price=-1)["verdict"], "NO TRADE")


class StopCapability(unittest.TestCase):
    OK = "ABC|limit|100|10"

    def test_unknown_stop_support_stays_provisional(self):
        r = trade(confirm_order=self.OK)
        self.assertTrue(r["placement_status"].startswith("provisional"))
        self.assertIn("stop-order support not confirmed", r["placement_status"])

    def test_stop_orders_yes_is_ready(self):
        r = trade(confirm_order=self.OK, stop_orders="yes")
        self.assertTrue(r["placement_status"].startswith("ready to place"))
        self.assertIn("place the stop order", r["placement_status"])

    def test_no_stop_orders_needs_manual_ack(self):
        self.assertTrue(trade(confirm_order=self.OK, stop_orders="no")["placement_status"].startswith("provisional"))
        r = trade(confirm_order=self.OK, stop_orders="no", manual_stop_ack=True)
        self.assertTrue(r["placement_status"].startswith("ready to place"))
        self.assertIn("price alert", r["placement_status"])

    def test_long_horizon_review_level_needs_no_stop_order(self):
        r = trade(horizon="long", confirm_order=self.OK)
        self.assertTrue(r["placement_status"].startswith("ready to place"), r["placement_status"])


class FlagModeNotRun(unittest.TestCase):
    def test_boycott_flag_without_result(self):
        r = trade(boycott_mode="flag")
        self.assertEqual(r["verdict"], "TRADE")
        self.assertFalse(r["boycott"]["screened"])
        self.assertTrue(any(w.startswith("SCREEN NOT RUN: boycott") for w in r["warnings"]))
        text = rs.render([r])
        self.assertIn("BOYCOTT: NOT CHECKED. SCREEN NOT RUN.", text)
        self.assertIn("NOT SCREENED FOR BOYCOTT", text)

    def test_shariah_flag_without_result(self):
        r = trade(shariah_mode="flag")
        self.assertFalse(r["shariah"]["screened"])
        self.assertIn("HALAL: NOT CHECKED. SCREEN NOT RUN.", rs.render([r]))

    def test_shariah_flag_with_valid_result_is_screened(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                json.dump(screen(), f)
            r = trade(shariah_mode="flag", shariah_result=p)
        self.assertTrue(r["shariah"]["screened"])
        self.assertFalse(any("SCREEN NOT RUN" in w for w in r["warnings"]))


class FxOnlyOnConversion(unittest.TestCase):
    CUSTOM = dict(broker=None, fee_model="percent", fee_rate=0.005, fee_min=0.5, fee_max=30, fx_pct=0.002)

    def test_usd_to_usd_pays_no_fx(self):
        r = trade(**self.CUSTOM)
        self.assertFalse(r["assumptions"]["fx_conversion_charged"])
        self.assertAlmostEqual(r["tranches"][0]["buy_fee"], 5.0, places=2)

    def test_conversion_pays_fx(self):
        r = trade(account_currency="JOD", **self.CUSTOM)
        self.assertTrue(r["assumptions"]["fx_conversion_charged"])
        self.assertAlmostEqual(r["tranches"][0]["buy_fee"], 5.0 + 0.002 * r["tranches"][0]["order_value"], places=2)
        self.assertNotEqual(r["verdict"], "TRADE")       # FX on both sides drops R:R below 2.0 here
        w = trade(account_currency="JOD", t1=115, t2=125, **self.CUSTOM)
        self.assertEqual(w["verdict"], "WATCHLIST", w["reasons"])   # v4.4: no FX-rate model yet
        self.assertIn("exchange-rate", " ".join(w["reasons"]))

    def test_broker_profile_currency_is_the_account_default(self):
        self.assertFalse(trade()["assumptions"]["fx_conversion_charged"])


class ShariahDates(unittest.TestCase):
    def test_market_cap_date_required_for_market_cap_methods(self):
        for m in ("aaoifi", "msci-m", "sp", "djim"):
            r = screen(methodology=m, market_cap_date=None)
            self.assertEqual(r["policy_decision"], "UNVERIFIED", m)

    def test_total_assets_method_does_not_need_it(self):
        self.assertNotEqual(screen(methodology="msci", market_cap_date=None)["policy_decision"], "UNVERIFIED")

    def test_market_cap_rechecked_at_trade_time(self):
        res = screen(market_cap_date="2026-11-04")
        self.assertEqual(sh.validate_result(res, "ABC", "2026-11-20", expected_asset="stock",
                                            isin="US0000000001")[0], "PERMITTED")
        pol, why = sh.validate_result(res, "ABC", "2026-12-15", expected_asset="stock", isin="US0000000001")
        self.assertEqual(pol, "UNVERIFIED")
        self.assertIn("fresh market cap", " ".join(why))

    def test_certificate_needs_https_evidence(self):
        base = dict(asset="etf-certified", ticker="ABC", as_of="2026-11-05", certifier="Board X",
                    certificate_date="2026-03-01")
        self.assertEqual(sh.screen(sh.build_parser().parse_args(
            sum([[f"--{k.replace('_', '-')}", v] for k, v in base.items()], [])))["policy_decision"], "UNVERIFIED")
        ok = dict(base, certificate_url="https://example.org/cert")
        self.assertEqual(sh.screen(sh.build_parser().parse_args(
            sum([[f"--{k.replace('_', '-')}", v] for k, v in ok.items()], [])))["policy_decision"], "PERMITTED")

    def test_certificate_rechecked_at_trade_time(self):
        args = ["--asset", "etf-certified", "--ticker", "ABC", "--as-of", "2026-11-05", "--certifier", "Board X",
                "--certificate-date", "2025-11-01", "--certificate-url", "https://example.org/cert"]
        res = sh.screen(sh.build_parser().parse_args(args))
        self.assertEqual(res["policy_decision"], "PERMITTED")
        self.assertEqual(sh.validate_result(res, "ABC", "2026-11-05", expected_asset="etf-certified")[0], "PERMITTED")
        self.assertEqual(sh.validate_result(res, "ABC", "2026-12-20", expected_asset="etf-certified")[0], "UNVERIFIED")

    def test_metal_with_bad_certificate_is_not_permitted(self):
        r = sh.screen(sh.build_parser().parse_args(
            ["--asset", "metal", "--metal-structure", "physical", "--allocated", "yes", "--ownership-rights", "yes",
             "--spot-settlement", "yes", "--no-lending", "yes", "--as-of", "2026-11-05", "--certifier", "Board X",
             "--certificate-date", "2099-01-01", "--certificate-url", "https://example.org/c"]))
        self.assertEqual(r["policy_decision"], "UNVERIFIED")


class ConditionalOutput(unittest.TestCase):
    def test_watchlist_shows_conditional_plan(self):
        text = rs.render([trade(quote_time=at(60))])
        self.assertIn("WAIT ABC\n  WHY: PRICE IS TOO OLD.", text)   # v4.8: full reason + fix
        self.assertIn("(ENGINE: live quote is 60 minutes old", text)
        self.assertIn("IF READY LATER, PLAN IS:", text)
        self.assertIn("STOP 94.00", text)
        self.assertIn("NOT READY. GET LIVE PRICE. RUN AGAIN.", text)
        self.assertIn("NO BUY TODAY", text)

    def test_trade_reminds_about_stop_capability(self):
        self.assertIn("CHECK APP CAN DO STOP ORDER", rs.render([trade()]))
        self.assertNotIn("CHECK APP CAN DO STOP ORDER", rs.render([trade(stop_orders="yes")]))


if __name__ == "__main__":
    unittest.main()
