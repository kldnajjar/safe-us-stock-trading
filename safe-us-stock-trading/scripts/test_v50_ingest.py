#!/usr/bin/env python3
"""v5.0: ingest.py turns one browser result into CSVs, ledger entries and signals; text output marks."""
import datetime as dt, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest
import render_simple as rs
import render_dashboard as rd
import test_v49_actions as t49


def history(n=300, start=50.0):
    d, out, px = dt.date.today() - dt.timedelta(days=1), [], start + n * 0.05
    while len(out) < n:
        if d.weekday() < 5:
            out.append(f"{d.isoformat()},{px:.2f},{px + 0.5:.2f},{px - 0.5:.2f}")
            px -= 0.05
        d -= dt.timedelta(days=1)
    return ";".join(reversed(out))


class Ingest(unittest.TestCase):
    def test_quote_time(self):
        self.assertEqual(ingest.quote_time("Nov 9, 2026 10:45 AM ET"), "2026-11-09T10:45:00-05:00")
        self.assertEqual(ingest.quote_time("Jul 6, 2026 3:05 PM ET"), "2026-07-06T15:05:00-04:00")
        self.assertEqual(ingest.quote_time("Nov 10, 2026"), "2026-11-10T00:00:00-05:00")   # market closed: no clock
        self.assertIsNone(ingest.quote_time("soon"))

    def test_live_shaped_closed_market_data(self):
        """Shape seen live on 2026-11-11 with the market closed: date-only time, sub-cent price."""
        tmp = tempfile.mkdtemp()
        out = ingest.ingest(dict(tickers={"GLDM": dict(cls="etf", price="79.735", time="Nov 10, 2026", realtime=False,
                                                       h=history())}), os.path.join(tmp, "L.json"), "", tmp)
        self.assertTrue(out["GLDM"]["ok"])
        self.assertEqual(out["GLDM"]["price"], 79.735)
        self.assertNotEqual(out["GLDM"]["quote_ledger"], "FRESH")        # an old quote is never called fresh

    def test_rows_drop_garbage(self):
        self.assertEqual(len(ingest.rows_of("2026-01-02,1,2,0.5;bad;2026-13-40,1,1,1;2026-01-05,x,1,1")), 1)

    def test_end_to_end(self):
        tmp = tempfile.mkdtemp()
        now = ingest.now_ny().strftime("%b %d, %Y %I:%M %p ET")
        data = dict(tickers={"AAA": dict(cls="etf", price="64.95", time=now, realtime=True, h=history()),
                             "MKT": dict(cls="etf", price="64.95", time=now, realtime=True, h=history()),
                             "ZZZ": dict(error="not found on Nasdaq"),
                             "BAD": dict(cls="stocks", price="0", time=now, h=history(5))})
        out = ingest.ingest(data, os.path.join(tmp, "L.json"), "MKT", tmp)
        self.assertTrue(out["AAA"]["ok"] and out["MKT"]["ok"])
        self.assertEqual(out["AAA"]["rows"], 300)
        self.assertEqual(out["AAA"]["quote_ledger"], "FRESH")
        self.assertIn(out["AAA"]["hint"], ("OK", "CAUTION", "AVOID"))
        self.assertFalse(out["ZZZ"]["ok"]); self.assertFalse(out["BAD"]["ok"])
        with open(os.path.join(tmp, "AAA.csv")) as f:
            self.assertEqual(f.readline().strip(), "date,close,high,low")
        self.assertTrue(os.path.exists(os.path.join(tmp, "SIG_AAA.json")))
        with open(os.path.join(tmp, "L.json")) as f:
            led = json.load(f)
        self.assertEqual(len(led if isinstance(led, list) else led.get("entries", led.get("items", []))), 4)


    def test_ticker_cannot_escape_the_folder(self):
        tmp = tempfile.mkdtemp()
        out = ingest.ingest(dict(tickers={"../../EVIL": dict(cls="etf", price="1", time="x", h=history(3)),
                                          "OK1": "not a dict"}), os.path.join(tmp, "L.json"), "../x", tmp)
        self.assertTrue(all(not v["ok"] for v in out.values()))
        self.assertEqual(os.listdir(tmp), [])


TB = dict(verdict="TRADE", reasons=[], ticker="BIL", asset="tbill", profile="safe", placement_status="provisional",
          shares=10, order_value=915.0, buy_fee=4.58, expected_net_return=3.2, breakeven_holding_days=40,
          boycott=t49.TRADE["boycott"],
          shariah=dict(mode="flag", screened=True, policy_decision="EXCLUDED", reasons=["interest-bearing"]))


class AuditFixes(unittest.TestCase):
    """One test per finding of the v5.0 audit."""

    def test_tbill_is_an_option_never_a_step_and_never_engine_says_no(self):
        out = rs.render([TB, t49.TRADE])
        self.assertIn("PARK CASH: BUY 10 BIL", out)
        self.assertNotIn("BIL: ENGINE SAYS NO", out)
        steps = out[out.index("WHAT TO DO NOW:"):out.index("BUY GLDM\n")]
        self.assertNotIn("BIL", steps)
        self.assertIn("RECOMMENDED: A.", out)
        only = rs.render([TB])
        self.assertIn("DO NOTHING TODAY", only)
        self.assertIn("BIL: FAILED A CHECK OR PAYS INTEREST", only)
        page = rd.render([TB])
        self.assertIn("PARK CASH IN BIL", page)
        self.assertIn("YOUR CALL: BIL", page)

    def test_long_term_risk_is_the_review_level_loss_not_zero(self):
        lng = dict(t49.TRADE, ticker="LNG", horizon="long",
                   downside=dict(executable_stop_downside=0.0, long_term_review_level_downside=88.0))
        out = rs.render([lng])
        self.assertIn("RISK AT REVIEW LEVEL $88.00", out)
        self.assertNotIn("RISK $0.00", out)
        self.assertIn("Can lose $88.00", rd.render([lng]))

    def test_tranches_are_not_shown_as_one_price(self):
        multi = dict(t49.TRADE, ticker="MUL", tranches=[dict(price=78.0, shares=7), dict(price=76.0, shares=6),
                                                       dict(price=74.0, shares=6)])
        out = rs.render([multi])
        self.assertIn("BUY 19 MUL IN 3 STEPS FROM 78.00 DOWN TO 74.00", out)
        self.assertIn("3 LIMIT BUYS FOR MUL: 7 AT 78.00, 6 AT 76.00, 6 AT 74.00", out)
        self.assertIn("19 shares in 3 steps: 7 at 78.00, 6 at 76.00, 6 at 74.00", rd.render([multi]))

    def test_watchlist_is_wait_not_no(self):
        w = dict(t49.TRADE, ticker="WCH", verdict="WATCHLIST", reasons=["quote is 40 min old"],
                 placement_status="not placeable")
        out = rs.render([w])
        self.assertIn("\U0001F7E1 A. WCH: WAIT.", out)
        self.assertNotIn("WCH: ENGINE SAYS NO", out)

    def test_text_and_dashboard_use_the_same_letters_and_pick(self):
        plans = [t49.FLAGGED, TB, t49.TRADE]
        rows, rec = rs.option_rows(plans)
        page = rd.render(plans)
        for L, _t, _l, _ok, _dot, d in rows:
            name = "KEEP CASH" if d is None else d["ticker"]
            self.assertRegex(page, rf"<h3>{L}\. [A-Z ]*{name}")
        self.assertIs(rs.recommended_plan(plans), t49.TRADE)
        self.assertIs(rd.best_pick(plans), t49.TRADE)

    def test_skill_file_has_no_dollar_digit(self):
        import re
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "SKILL.md")) as f:
            self.assertEqual(re.findall(r"\$\d", f.read()), [], "the skill loader replaces $1 etc. with the user's words")

    def test_budget_below_minimum_order_says_so(self):
        import size_trade as st
        self.assertIn("the amount set for this trade", [p for p, _w, _f in rs.EXPLAIN if "amount set" in p][0])
        a = st.build_parser().parse_args(["--asset", "stock", "--profile", "safe", "--quote-status", "live",
                                          "--boycott-mode", "flag", "--shariah-mode", "flag", "--budget", "-5"])
        self.assertTrue(any("--budget" in b for b in st.validate_inputs(a)))


class Marks(unittest.TestCase):
    def test_text_marks(self):
        out = rs.render([t49.FLAGGED, t49.TRADE])
        self.assertIn("\U0001F7E2 GLDM:", out)
        self.assertIn("\U0001F534 XYZ:", out)
        self.assertIn("\U0001F7E2 A. BUY 19 GLDM", out)
        self.assertIn("\U0001F7E1 B. BUY 10 XYZ", out)


if __name__ == "__main__":
    unittest.main()
