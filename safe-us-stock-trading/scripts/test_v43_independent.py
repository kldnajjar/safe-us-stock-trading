"""Additional independent safeguards for US Portfolio CFO v4.3.

These tests are intentionally designed to expose invalid inputs, order-side
misaccounting, and pathological share-sizing runtimes. Run alongside the
supplied suite. They do NOT modify the production scripts.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import size_trade as _st_v46  # noqa: E402
# v4.6: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v46_mandatory.py tests them switched on.
_st_v46.SCREENS_REQUIRED = _st_v46.SOURCES_REQUIRED = _st_v46.MARKET_CLOCK_REQUIRED = False
import boycott_screen as bs
import fees
import portfolio_state as ps


def good_etf_evidence():
    src = lambda: {"finding": "no_match", "checked_on": "2026-11-05", "url": "https://example.org/check"}
    return {"ticker": "ABC", "isin": "US0000000001", "entity": "ABC ETF", "asset": "etf",
            "identity_resolved": True, "related_entities": [],
            "sources": {"ohchr": dict(src(), list_version="A/HRC/63/20"),
                        "bds": src(), "afsc": src(), "whoprofits": src(),
                        "sec": dict(src(), israel_hq=False, material_israel_ops=False)},
            "etf": {"screened_weight_pct": 100, "excluded_weight_pct": 0, "flagged_weight_pct": 0}}


class AdditionalSafetyTests(unittest.TestCase):
    def test_etf_negative_excluded_weight_not_clear(self):
        ev = good_etf_evidence()
        ev["etf"]["excluded_weight_pct"] = -10
        self.assertEqual(bs.screen(ev, "2026-11-05")["status"], "UNVERIFIED")

    def test_etf_screened_weight_cannot_exceed_100(self):
        ev = good_etf_evidence()
        ev["etf"]["screened_weight_pct"] = 150
        self.assertEqual(bs.screen(ev, "2026-11-05")["status"], "UNVERIFIED")

    def test_existing_sector_weights_cannot_be_negative(self):
        fee = fees.broker_profile("bank-al-etihad-jo")[1]
        state = {"cash": 5000, "holdings": [
            {"ticker": "AAA", "asset": "stock", "shares": 25, "price": 100, "avg_cost": 100,
             "level": 99, "level_type": "hard", "sector_weights": {"Tech": -1}}], "orders": []}
        try:
            got = ps.build(state, fee=fee)
        except ValueError:
            return  # rejection at the state boundary is acceptable
        self.assertTrue(got.get("reconciliation_required") or
                        any("invalid" in w.lower() for w in got.get("warnings", [])),
                        "Invalid holding sector weight must not silently create negative portfolio exposure")

    def test_open_sell_order_must_not_reserve_buying_power(self):
        fee = fees.broker_profile("bank-al-etihad-jo")[1]
        state = {"cash": 9000,
                 "holdings": [{"ticker": "AAA", "asset": "stock", "shares": 10, "price": 100,
                               "avg_cost": 90, "level": 94, "level_type": "hard", "sector_weights": {"Tech": 1}}],
                 "orders": [{"id": "sell-aaa", "ticker": "AAA", "asset": "stock", "side": "sell",
                             "limit": 100, "shares": 5, "filled_shares": 0, "status": "open",
                             "level": 94, "level_type": "hard", "sector_weights": {"Tech": 1}}]}
        try:
            got = ps.build(state, fee=fee)
        except ValueError:
            return  # explicit rejection of unsupported sell orders is safe
        self.assertEqual(got["actual"]["open_order_commitments"], 0.0,
                         "An open sell order should not reserve cash as if buying shares")
        self.assertEqual(got["actual"]["ticker_exposure"]["AAA"], 1000.0,
                         "An open sell order should not increase stock exposure")

    def test_microprice_does_not_hang_whole_share_sizer(self):
        cmd = [sys.executable, os.path.join(HERE, "size_trade.py"),
               "--asset", "stock", "--ticker", "ABC", "--profile", "balanced",
               "--portfolio", "10000", "--cash", "10000", "--entry", "0.0001",
               "--stop", "0.000095", "--t1", "0.00012", "--t2", "0.00013",
               "--market-price", "0.0001", "--sector-weights", '{"Tech":1}',
               "--quote-status", "previous_close", "--boycott-mode", "off",
               "--shariah-mode", "off", "--broker", "bank-al-etihad-jo"]
        try:
            completed = subprocess.run(cmd, text=True, capture_output=True, timeout=2)
        except subprocess.TimeoutExpired:
            self.fail("whole-share sizing exceeded 2 seconds for a micro-priced security")
        self.assertEqual(completed.returncode, 0)
        self.assertIn(json.loads(completed.stdout)["verdict"], ("NO TRADE", "WATCHLIST"))


if __name__ == "__main__":
    unittest.main()
