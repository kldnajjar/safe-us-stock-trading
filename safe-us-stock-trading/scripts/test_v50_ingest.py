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


class ReadableSourcesOnly(unittest.TestCase):
    """A source we cannot read (robots block, paywall, login) is not part of the skill."""
    HERE = os.path.dirname(os.path.abspath(__file__))

    def text(self, *parts):
        with open(os.path.join(self.HERE, *parts)) as f:
            return f.read()

    def test_no_unreadable_source_in_skill_or_screen(self):
        skill, screen = self.text("..", "SKILL.md"), self.text("boycott_screen.py")
        for word in ("bl00d", "bloodmoney"):
            self.assertNotIn(word, skill.lower())
            self.assertNotIn(word, screen.lower())
        self.assertNotIn("| paywalled |", skill)
        self.assertIn("can't be read", skill)


class Robinhood(unittest.TestCase):
    def test_user_can_choose_the_robinhood_entity(self):
        from fees import broker_profile, load_brokers
        ids = [k for k, v in load_brokers()["brokers"].items() if not v.get("template")]
        self.assertEqual(ids[:4], ["bank-al-etihad-jo", "robinhood", "robinhood-uk", "robinhood-sg"])
        for bid in ("robinhood", "robinhood-uk", "robinhood-sg"):
            prof, fee = broker_profile(bid)
            self.assertEqual(fee(1500.0, 19), 0.0, bid)
            self.assertTrue(prof["verified_source"].startswith("https://"), bid)
        self.assertEqual(broker_profile("robinhood-uk")[0]["fx_pct"], 0.001)


class FirstRealRun(unittest.TestCase):
    """Findings from the first real v5.0 dashboard (2026-11-11), one test each."""

    def test_unverified_halal_is_cant_confirm_not_not_checked(self):
        sh = dict(mode="flag", screened=True, policy_decision="UNVERIFIED", reasons=["not verified from fund documents"])
        self.assertEqual(rs.halal_ref(sh)[0], "CAN'T CONFIRM")
        self.assertEqual(rs.halal_ref(dict(mode="flag", screened=False))[0], "NOT CHECKED")
        d = dict(t49.TRADE, shariah=sh)
        self.assertFalse(rs.is_clean(d))
        self.assertIsNone(rs.recommended_plan([d]))               # never the best pick

    def test_no_double_period_after_events(self):
        out = rs.render([], events="FED DEC 9. CPI DEC 10.")
        self.assertIn("RE-RUN ME AFTER: FED DEC 9. CPI DEC 10.\n", out)
        self.assertNotIn("..", out)

    def test_dashboard_prints_in_light_colours_and_lists_each_source_once(self):
        page = rd.render([t49.TRADE], sources=["BLS|https://www.bls.gov/cpi", "BLS again|https://www.bls.gov/cpi"])
        self.assertIn("@media print", page)
        self.assertIn("print-color-adjust:exact", page)
        self.assertEqual(page.count('href="https://www.bls.gov/cpi"'), 1)


class LocalTimeAndClearNextStep(unittest.TestCase):
    """v5.1: times in the user's own zone; a no-buy page still says exactly what to do."""
    CLOSED = dict(verdict="NO TRADE", ticker="GLDM", asset="metal", profile="safe", horizon="medium",
                  tranches=[dict(price=78.0, shares=19)], reasons=["net reward:risk of the exit plan 1.6 is below"],
                  quote=dict(time="2026-11-11T04:32:00-05:00", status="previous_close", source="Nasdaq"),
                  market_clock=dict(open=False, reason="before the open", next_open_new_york="2026-11-11 09:30",
                                    now_new_york="2026-11-11T04:32-05:00"))

    def tearDown(self):
        rs.set_local("")

    def test_times_in_the_users_zone(self):
        self.assertTrue(rs.set_local("Asia/Amman"))
        self.assertEqual(rs.when("2026-11-11T04:32:00-05:00"), "WED 11 NOV 12:32 AMMAN TIME")
        self.assertEqual(rs.when("2026-07-06T15:05:00-04:00"), "MON 06 JUL 22:05 AMMAN TIME")
        self.assertEqual(rs.when("2026-11-05"), "2026-11-05")                    # a plain date stays a date
        self.assertTrue(rs.set_local("+03:00"))
        self.assertEqual(rs.when("2026-11-11T04:32:00-05:00"), "WED 11 NOV 12:32 UTC+03:00")

    def test_unknown_zone_keeps_the_engine_times(self):
        self.assertFalse(rs.set_local("Mars/Olympus"))
        self.assertEqual(rs.when("2026-11-11T04:32:00-05:00"), "2026-11-11T04:32:00-05:00")
        self.assertIn("NEW YORK TIME", rs.render([self.CLOSED], tz="Mars/Olympus"))

    def test_closed_market_step_and_local_open_time(self):
        out = rs.render([self.CLOSED], tz="Asia/Amman")
        self.assertIn("NEXT OPEN WED 11 NOV 17:30 AMMAN TIME (09:30 NEW YORK)", out)
        self.assertIn("US MARKET IS CLOSED NOW. IT OPENS WED 11 NOV 17:30 AMMAN TIME (09:30 NEW YORK). ASK ME AGAIN", out)
        page = rd.render([self.CLOSED], tz="Asia/Amman")
        self.assertIn("Prices from WED 11 NOV 12:32 AMMAN TIME", page)
        self.assertNotIn("2026-11-11T04:32:00-05:00", page)
        self.assertIn("What I looked at", page)
        self.assertIn("Why: <b>GLDM</b>", page)

    def test_without_a_zone_nothing_changes(self):
        out = rs.render([self.CLOSED])
        self.assertIn("NEXT OPEN 2026-11-11 09:30 NEW YORK TIME.", out)

    def test_account_todos_from_the_users_own_state(self):
        state = dict(actual=dict(unquantified=["NVDA"], breached=["XYZ"], holdings=[]))
        page = rd.render([self.CLOSED], state)
        self.assertIn("Also fix in your app", page)
        self.assertIn("NVDA HAS NO STOP. PICK A PRICE WHERE YOU WOULD SELL", page)
        self.assertIn("XYZ IS PAST ITS STOP", page)
        self.assertNotIn("Also fix in your app", rd.render([self.CLOSED], dict(actual=dict(holdings=[]))))


class BuyAtOrBelow(unittest.TestCase):
    """v5.1: when only the reward:risk gate fails, the engine names the price at which the same plan passes."""
    L = ["--profile", "safe", "--horizon", "medium", "--entry", "345.27", "--stop", "335.04", "--t1", "362.00",
         "--t2", "372.00", "--sector-weights", '{"Tech":1}', "--stop-orders", "yes"]

    @classmethod
    def setUpClass(cls):
        import portfolio_state as ps, test_integration as ti
        cls.ti, cls.tmp = ti, tempfile.mkdtemp()
        cls.sf = ti.jfile(ps.build(dict(cash=21000, cash_includes_open_orders=False, orders=[], holdings=[]),
                                   fee=ti.FEE), cls.tmp)

    def size(self, levels):
        return self.ti.size(self.tmp, self.sf, "AAPL", "US0378331005", "stock", levels)

    def at(self, price):
        return self.size([x if x != "345.27" else f"{price:.2f}" for x in self.L])

    def test_price_is_the_highest_cent_that_passes_the_full_engine(self):
        p = self.size(self.L)
        self.assertEqual(p["verdict"], "NO TRADE")
        h = p["buy_at_or_below"]
        self.assertLess(h["price"], 345.27)
        self.assertGreater(h["price"], 335.04)
        self.assertEqual(self.at(h["price"])["verdict"], "TRADE")
        above = self.at(h["price"] + 0.01)
        self.assertEqual(above["verdict"], "NO TRADE")
        self.assertIn("net reward:risk", above["reasons"][0])
        self.assertEqual((h["stop"], h["t1"], h["t2"]), (335.04, 362.0, 372.0))

    def test_no_price_when_blocked_for_any_other_reason(self):
        far_stop = self.size([x if x != "335.04" else "300.00" for x in self.L])
        self.assertEqual(far_stop["verdict"], "NO TRADE")
        self.assertNotIn("buy_at_or_below", far_stop)
        ok = self.at(338.00)
        self.assertEqual(ok["verdict"], "TRADE")
        self.assertNotIn("buy_at_or_below", ok)

    def test_output_says_the_price(self):
        p = self.size(self.L)
        px_ = f"{p['buy_at_or_below']['price']:,.2f}"
        out = rs.render([p])
        self.assertIn(f"IT PASSES AT {px_} OR LOWER (SAME STOP 335.04 AND TARGETS). SET A PRICE ALERT AT {px_}", out)
        self.assertNotIn("WAIT FOR A LOWER PRICE", out)
        self.assertIn(f"IT PASSES AT {px_} OR LOWER", rd.render([p]))


class HonestOdds(unittest.TestCase):
    """v5.1: the page shows the odds a plan needs and whether the plans have actually made money."""

    def test_engine_gives_the_needed_win_rate_rounded_up(self):
        import size_trade as st
        res = dict(asset="stock", tranches=[1], downside=dict(executable_stop_downside=71.10),
                   partial_exit_plan=dict(feasible=True, combined_net_profit=287.41))
        self.assertEqual(st.needed_win_rate(res), 19.9)            # 71.10 / 358.51 = 19.83% -> up
        self.assertIsNone(st.needed_win_rate(dict(asset="tbill", tranches=[1])))
        self.assertIsNone(st.needed_win_rate(dict(asset="stock", tranches=[1], downside={})))

    def test_real_plan_carries_it_and_the_output_says_it(self):
        p = BuyAtOrBelow.setUpClass() or BuyAtOrBelow("at").at(338.00)
        self.assertEqual(p["verdict"], "TRADE")
        n = p["needed_win_rate_pct"]
        self.assertTrue(0 < n < 100)
        self.assertIn(f"ODDS YOU NEED: OF 100 TRADES LIKE THIS, MORE THAN {n:g} MUST REACH THE TARGETS", rs.render([p]))
        self.assertIn("nobody can promise that", rd.render([p]))

    def test_results_box_never_flatters(self):
        none = rd.render([t49.TRADE])
        self.assertIn("Is this making you money?", none)
        self.assertIn("NO RECORD YET", none)
        few = rd.render([t49.TRADE], journal=dict(verdict="too few closed trades to judge (3; need at least 20)",
                                                 closed_trades=3, total_pnl=42.5, win_rate_pct=66.7, total_fees=30.1))
        self.assertIn("TOO FEW TRADES TO KNOW", few)
        self.assertIn("+$42.50", few)
        bad = rd.render([t49.TRADE], journal=dict(verdict="not working: results are not above zero after costs",
                                                 closed_trades=25, total_pnl=-310.0, win_rate_pct=32.0, total_fees=240.0))
        self.assertIn("NOT WORKING", bad)
        self.assertIn("-$310.00", bad)
        behind = rd.render([t49.TRADE], journal=dict(
            verdict="profitable but behind simply holding the benchmark fund", closed_trades=22, total_pnl=120.0,
            win_rate_pct=45.0, total_fees=200.0, benchmark=dict(available=True, skill_minus_benchmark=-80.0)))
        self.assertIn("LESS THAN JUST HOLDING THE FUND", behind)
        self.assertIn("-$80.00", behind)


class Marks(unittest.TestCase):
    def test_text_marks(self):
        out = rs.render([t49.FLAGGED, t49.TRADE])
        self.assertIn("\U0001F7E2 GLDM:", out)
        self.assertIn("\U0001F534 XYZ:", out)
        self.assertIn("\U0001F7E2 A. BUY 19 GLDM", out)
        self.assertIn("\U0001F7E1 B. BUY 10 XYZ", out)


if __name__ == "__main__":
    unittest.main()
