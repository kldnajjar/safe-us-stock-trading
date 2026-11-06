#!/usr/bin/env python3
"""v4.6 dashboard tests: the HTML page runs on the real engine chain, copies numbers verbatim,
keeps every safety line, escapes untrusted text, and never loads anything external."""
import json, os, re, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import portfolio_state as ps  # noqa: E402
import render_dashboard as rd  # noqa: E402
import test_integration as ti  # noqa: E402

LEVELS = ["--profile", "safe", "--horizon", "short", "--entry", "345.27", "--stop", "335.04",
          "--t1", "375.00", "--t2", "395.00", "--sector-weights", '{"Tech":1}', "--stop-orders", "yes"]


class Dashboard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        st = dict(cash=21000, cash_includes_open_orders=False, orders=[],
                  holdings=[dict(ticker="NVDA", asset="stock", shares=10, avg_cost=180, price=200, level=150,
                                 level_type="hard", sector_weights={"Tech": 1})])
        cls.state = ps.build(st, fee=ti.FEE)
        sf = ti.jfile(cls.state, cls.tmp)
        cls.trade = ti.size(cls.tmp, sf, "AAPL", "US0378331005", "stock", LEVELS)
        cls.watch = ti.size(cls.tmp, sf, "ABCD", "US0000000002", "stock", LEVELS + ["--quote-status", "previous_close"])
        bad = [x if x != "335.04" else "320.00" for x in LEVELS]
        cls.no = ti.size(cls.tmp, sf, "TSM", "US8740391003", "stock", bad)
        cls.page = rd.render([cls.no, cls.watch, cls.trade], cls.state, market="Calm", events="CPI Tue")

    def test_verdicts_as_expected(self):
        self.assertEqual((self.trade["verdict"], self.watch["verdict"], self.no["verdict"]),
                         ("TRADE", "WATCHLIST", "NO TRADE"))

    def test_numbers_copied_verbatim(self):
        t = self.trade
        for v in (t["stop_level"], t["t1_level"], t["t2_level"], t["fee_adjusted_breakeven_price"]):
            self.assertIn(f"{v:,.2f}", self.page)
        for v in (t["downside"]["executable_stop_downside"], t["gap_scenario"]["loss"],
                  t["partial_exit_plan"]["combined_net_profit"], t["cash_accounting"]["available_cash"],
                  self.state["actual"]["portfolio_value"]):
            self.assertIn(f"${v:,.2f}", self.page)

    def test_safety_lines_present(self):
        for s in ("PLANNED LOSS AT STOP", "LOSS CAN BE MORE", "NEVER LOWER", "CHECK PRICE IN APP FIRST",
                  "Good only for this price", "IF READY LATER, PLAN IS:", "NOT READY", rd.SAFETY_FOOTER):
            self.assertIn(s.lower(), self.page.lower(), s)
        self.assertNotIn("MAX LOSS", self.page.upper())

    def test_trade_card_first_and_no_trade_reason_shown(self):
        self.assertLess(self.page.index("AAPL"), self.page.index("TSM"))
        self.assertIn(rd.e(self.no["reasons"][0]), self.page)

    def test_no_buy_banner_when_nothing_trades(self):
        page = rd.render([self.watch, self.no], self.state)
        self.assertIn("NO BUY TODAY", page)
        self.assertNotIn("NO BUY TODAY", self.page)

    def test_screen_not_run_is_loud(self):
        d = dict(self.trade, boycott=dict(mode="flag", screened=False),
                 warnings=["SCREEN NOT RUN: boycott flag mode without a result file"])
        page = rd.render([d], self.state)
        self.assertIn("BOYCOTT: NOT CHECKED. SCREEN NOT RUN.", page)
        self.assertNotIn("Boycott: Not on lists", page)

    def test_reconciliation_banner(self):
        st = dict(self.state, reconciliation_required=True)
        self.assertIn("No new trades until", rd.render([self.no], st))

    def test_untrusted_text_escaped(self):
        evil = "<script>alert(1)</script>"
        d = dict(self.no, ticker=evil, reasons=[evil])
        page = rd.render([d], None, market=evil, notes=[evil], sources=[f"{evil}|javascript:alert(1)"])
        self.assertNotIn("<script", page.lower())
        self.assertNotIn("javascript:", page)

    def test_self_contained(self):
        self.assertIsNone(re.search(r"<(script|link|img|iframe)\b", self.page, re.I))
        self.assertNotIn("@import", self.page)

    def test_minimal_plan_does_not_crash(self):
        page = rd.render([{"verdict": "NO TRADE", "reasons": ["engine error"]}])
        self.assertIn("engine error", page)

    def test_cli_writes_file(self):
        files = [ti.jfile(x, self.tmp) for x in (self.trade, self.state)]
        out = os.path.join(self.tmp, "d.html")
        rd.main(["--plans", files[0], "--state", files[1], "--out", out])
        with open(out) as f:
            self.assertTrue(f.read().startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
