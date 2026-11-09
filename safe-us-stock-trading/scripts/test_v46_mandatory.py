#!/usr/bin/env python3
"""v4.6 tests: mandatory boycott + Shariah screens, mandatory fresh sources, full NO BUY reasons,
the NYSE clock, the ledger helper, and the long-only signals from 151 Trading Strategies.
Gates are switched ON here."""
import copy, datetime as dt, json, math, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import size_trade as st  # noqa: E402
import sources_check as sc  # noqa: E402
import signals as sg  # noqa: E402
import render_simple as rs  # noqa: E402
import market_clock as mc  # noqa: E402
import ledger as lg  # noqa: E402
import journal as jn  # noqa: E402
import run_checks as rc  # noqa: E402
import portfolio_state as pst  # noqa: E402
import boycott_screen as bsc  # noqa: E402
from test_size_trade import run, bres, sres, write_json  # noqa: E402

NOW = dt.datetime(2026, 11, 5, 20, 35, tzinfo=dt.timezone.utc)
QT = "2026-11-05T15:30:00-05:00"   # 20:30 UTC, the quote the engine sizes against


def item(**kw):
    return kw


def ledger(**over):
    items = [
        item(category="quote", ticker="ABC", source="nasdaq", url="https://www.nasdaq.com/market-activity/stocks/abc",
             observed_at=QT, value=100.0, what="last trade"),
        item(category="quote", ticker="ABC", source="yahoo", url="https://finance.yahoo.com/quote/ABC",
             observed_at="2026-11-05T15:31:00-05:00", value=100.1),
        item(category="price_history", ticker="ABC", source="stooq", url="https://stooq.com/q/d/?s=abc.us",
             observed_at="2026-11-05T15:20:00-05:00", history_through="2026-11-05", what="MA, ATR"),
        item(category="earnings_date", ticker="ABC", source="nasdaq", url="https://www.nasdaq.com/market-activity/stocks/abc/earnings",
             observed_at="2026-11-05T15:00:00-05:00", event_date="2027-01-28"),
        item(category="fundamentals", ticker="ABC", source="sec_edgar", url="https://www.sec.gov/cgi-bin/browse-edgar?CIK=ABC",
             observed_at="2026-11-05T14:00:00-05:00", published_at="2026-10-31", form="10-Q", period_end="2026-09-27",
             latest_filing_checked_at="2026-11-05T14:00:00-05:00"),
        item(category="consensus", ticker="ABC", source="stockanalysis", url="https://stockanalysis.com/stocks/abc/forecast/",
             observed_at="2026-11-05T14:10:00-05:00"),
        item(category="macro_release", source="bls", url="https://www.bls.gov/news.release/cpi.nr0.htm",
             observed_at="2026-11-05T13:00:00-05:00", published_at="2026-10-15", next_release="2026-11-13", what="CPI"),
        item(category="news", source="reuters", url="https://www.reuters.com/markets/us/fed-holds/",
             observed_at="2026-11-05T13:05:00-05:00", published_at="2026-11-05T12:10:00Z", claim_id="fed-hold", what="Fed holds"),
        item(category="news", source="cnbc", url="https://www.cnbc.com/2026/11/05/fed-holds.html",
             observed_at="2026-11-05T13:06:00-05:00", published_at="2026-11-05T12:20:00Z", claim_id="fed-hold", what="Fed holds"),
    ]
    for i, patch in over.items():
        idx = int(i[1:])
        if patch is None:
            items[idx] = None
        else:
            items[idx] = dict(items[idx], **patch)
    return dict(items=[x for x in items if x is not None])


def check_file(led):
    return write_json(sc.check(led, now=NOW))


def full(**kw):
    """A fully screened, fully sourced stock plan. earnings= sets the ledger's earnings date too."""
    e = kw.pop("earnings", None)
    if e:
        kw.setdefault("sources_check", check_file(ledger(q3=dict(event_date=e))))
        kw.setdefault("next_earnings", e)
    base = dict(boycott_mode="exclude", boycott_result=bres(), shariah_mode="exclude", shariah_result=sres(),
                sources_check=check_file(ledger()), horizon="medium", stop=90, t1=120, t2=130,
                next_earnings="2027-01-28")
    base.update(kw)
    return run(**base)


class Gates(unittest.TestCase):
    def setUp(self):
        self._saved = (st.SCREENS_REQUIRED, st.SOURCES_REQUIRED, st.MARKET_CLOCK_REQUIRED, st.CLOCK, sc.CLOCK,
                       sc.load_registry)
        st.SCREENS_REQUIRED = st.SOURCES_REQUIRED = st.MARKET_CLOCK_REQUIRED = True
        st.CLOCK = sc.CLOCK = lambda: NOW
        real = self._saved[5]
        # the fixtures are pinned to 2026-11-05, before the registry's real verified_on date
        sc.load_registry = lambda path=None: dict(real(path), verified_on="2026-11-05")

    def tearDown(self):
        (st.SCREENS_REQUIRED, st.SOURCES_REQUIRED, st.MARKET_CLOCK_REQUIRED, st.CLOCK, sc.CLOCK,
         sc.load_registry) = self._saved


class MandatoryScreens(Gates):
    def test_full_plan_trades(self):
        r = full()
        self.assertEqual(r["verdict"], "TRADE", r["reasons"])
        self.assertTrue(r["sources"]["ok"])
        self.assertTrue(r["boycott"]["screened"] and r["shariah"]["screened"])

    def test_boycott_off_refused(self):
        r = full(boycott_mode="off", boycott_result="")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("boycott screen is mandatory", " ".join(r["reasons"]))

    def test_shariah_off_refused(self):
        r = full(shariah_mode="off", shariah_result="")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("Shariah screen is mandatory", " ".join(r["reasons"]))

    def test_flag_mode_still_needs_a_result(self):
        r = full(boycott_mode="flag", boycott_result="")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("boycott screen not run", " ".join(r["reasons"]))
        r = full(shariah_mode="flag", shariah_result="")
        self.assertIn("Shariah screen not run", " ".join(r["reasons"]))

    def test_flag_mode_with_result_lets_excluded_through_with_label(self):
        r = full(boycott_mode="flag", boycott_result=bres(ohchr="match"))
        self.assertEqual(r["verdict"], "TRADE", r["reasons"])
        self.assertEqual(r["boycott"]["status"], "EXCLUDED")

    def test_cli_cannot_turn_screens_off(self):
        out = subprocess.run([sys.executable, os.path.join(HERE, "size_trade.py"), "--asset", "stock", "--ticker", "ABC",
                              "--profile", "balanced", "--portfolio", "10000", "--cash", "10000", "--entry", "100",
                              "--stop", "94", "--t1", "112", "--t2", "119", "--market-price", "100",
                              "--sector-weights", '{"Tech":1}', "--quote-status", "live", "--boycott-mode", "off",
                              "--shariah-mode", "off", "--broker", "bank-al-etihad-jo"],
                             capture_output=True, text=True, timeout=20)
        r = json.loads(out.stdout)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("mandatory", " ".join(r["reasons"]))

    def test_tbill_shariah_flag_needs_no_file_but_off_is_refused(self):
        tb = dict(asset="tbill", entry=None, stop=None, t1=None, t2=None, sector_weights=None, amount=2000, price=50,
                  yield_pct=4.0, expense_ratio_pct=0.1, duration_yrs=0.15, hold_months=6, spread_bps=2, market_price=50,
                  boycott_mode="exclude", boycott_result=bres(asset="tbill"), ticker="ABC",
                  sources_check=check_file(ledger(q0=dict(value=50.0), q1=dict(value=50.0))))
        r = run(**dict(tb, shariah_mode="off"))
        self.assertIn("Shariah screen is mandatory", " ".join(r["reasons"]))
        r = run(**dict(tb, shariah_mode="flag"))
        self.assertNotIn("Shariah screen not run", " ".join(r["reasons"]))


class Sources(Gates):
    def test_no_sources_is_watchlist(self):
        r = full(sources_check="")
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("sources not checked", " ".join(r["reasons"]))

    def test_stale_quote_source_is_watchlist(self):
        led = ledger(q0=dict(observed_at="2026-11-05T14:30:00-05:00"))   # 65 minutes before the clock
        r = full(sources_check=check_file(led))
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("STALE", " ".join(r["sources"]["problems"]))

    def test_staleness_rechecked_at_sizing_time(self):
        f = write_json(sc.check(ledger(), now=NOW - dt.timedelta(minutes=1)))   # fresh when written
        st.CLOCK = lambda: NOW + dt.timedelta(hours=2)                          # sized 2 h later
        self.assertEqual(sc.check(ledger(), now=NOW + dt.timedelta(hours=2))["ok"], False)
        r = full(sources_check=f, quote_time=QT)
        self.assertNotEqual(r["verdict"], "TRADE")

    def test_conflicting_prices(self):
        out = sc.check(ledger(q1=dict(value=103.0)), now=NOW)
        self.assertFalse(out["ok"])
        self.assertEqual({i["status"] for i in out["items"] if i["category"] == "quote"}, {"CONFLICT"})

    def test_single_price_source_is_a_warning_not_a_block(self):
        out = sc.check(ledger(q1=None), now=NOW)
        self.assertTrue(out["ok"])
        self.assertTrue(any("one source only" in w for w in out["warnings"]))

    def test_url_must_be_on_the_named_source(self):
        out = sc.check(ledger(q0=dict(url="https://finance.yahoo.com/quote/ABC")), now=NOW)
        self.assertEqual(out["items"][0]["status"], "BAD_SOURCE")

    def test_fundamentals_only_from_sec(self):
        out = sc.check(ledger(q4=dict(source="yahoo", url="https://finance.yahoo.com/quote/ABC/financials")), now=NOW)
        self.assertEqual(out["items"][4]["status"], "BAD_SOURCE")

    def test_fundamentals_need_a_fresh_edgar_check(self):
        out = sc.check(ledger(q4=dict(latest_filing_checked_at="2026-11-03T14:00:00-05:00")), now=NOW)
        self.assertEqual(out["items"][4]["status"], "STALE")

    def test_macro_release_superseded(self):
        out = sc.check(ledger(q6=dict(next_release="2026-11-04")), now=NOW)
        self.assertEqual(out["items"][6]["status"], "STALE")

    def test_future_dates_invalid(self):
        out = sc.check(ledger(q7=dict(published_at="2026-11-07T00:00:00Z")), now=NOW)
        self.assertEqual(out["items"][7]["status"], "INVALID")

    def test_single_source_news_warns(self):
        out = sc.check(ledger(q8=None), now=NOW)
        self.assertTrue(any("fed-hold" in w for w in out["warnings"]))

    def test_missing_category_for_horizon(self):
        r = full(sources_check=check_file(ledger(q4=None)))   # medium horizon needs fundamentals
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("no fresh source for fundamentals", " ".join(r["sources"]["problems"]))

    def test_market_price_must_be_a_ledger_quote(self):
        r = full(market_price=100.5, entry=100)
        self.assertNotEqual(r["verdict"], "TRADE")

    def test_registry_valid(self):
        self.assertTrue(sc.validate_registry(sc.load_registry()))


class Output(Gates):
    def test_no_buy_prints_every_reason_with_fix(self):
        r = full(boycott_result=bres(ohchr="match"), shariah_result=sres(interest_debt=900, total_debt=900))
        text = rs.render([r])
        self.assertIn("NO BUY ABC", text)
        self.assertIn("WHY: COMPANY IS ON A BOYCOTT LIST.", text)
        self.assertIn("FOUND ON: OHCHR", text)
        self.assertIn("WHY: NOT HALAL UNDER YOUR METHOD.", text)
        self.assertGreaterEqual(text.count("FIX:"), 2)
        self.assertIn("(ENGINE: ", text)

    def test_unknown_reason_still_printed_in_full(self):
        text = rs.render([dict(verdict="NO TRADE", ticker="ZZZ", reasons=["a brand new engine reason"])])
        self.assertIn("WHY: A BRAND NEW ENGINE REASON", text)

    def test_trade_prints_sources(self):
        text = rs.render([full()])
        self.assertIn("PRICE FROM: Nasdaq", text)
        self.assertIn("(MATCH)", text)
        self.assertIn("NUMBERS FROM: SEC EDGAR 10-Q FILED 2026-10-31", text)
        self.assertIn("SOURCES (CHECKED", text)
        self.assertIn("https://www.bls.gov/", text)
        self.assertIn("SCREEN DATA:", text)

    def test_wait_for_sources_lists_the_problem(self):
        led = ledger(q0=dict(observed_at="2026-11-05T14:30:00-05:00"))
        text = rs.render([full(sources_check=check_file(led))])
        self.assertIn("WHY: SOME DATA IS OLD, MISSING, OR SOURCES DISAGREE.", text)
        self.assertIn("STALE", text)


def price_rows(trend="up", last=100.0, end="2026-11-05", n=300, wiggle=0.004):
    drift = {"up": 0.0015, "down": -0.0015}[trend]
    raw, p = [], 1.0
    for i in range(n):
        p *= 1 + drift + wiggle * math.sin(i / 3.0)
        raw.append(p)
    k = last / raw[-1]
    d_end = dt.date.fromisoformat(end)
    return [dict(date=(d_end - dt.timedelta(days=n - 1 - i)).isoformat(), close=round(x * k, 4),
                 high=round(x * k * 1.01, 4), low=round(x * k * 0.99, 4)) for i, x in enumerate(raw)]


def sig_file(kind="ok", price=100.0, end="2026-11-05", ticker="ABC", edit=None):
    """A real signals.py result. kind: ok (uptrend, market up), avoid (downtrend), caution (uptrend, market down)."""
    rows = price_rows("down" if kind == "avoid" else "up", price, end)
    market = price_rows("down" if kind == "caution" else "up", 50.0, end)
    out = sg.one(ticker, rows, market)
    if edit:
        out.update(edit)
    return write_json(out)


class ProfitGates(Gates):
    def test_short_trade_through_earnings_blocked(self):
        r = full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file(), earnings="2026-11-20")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("inside the short-term holding window", " ".join(r["reasons"]))
        r = full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file(), earnings="2026-11-20", accept_earnings_gap=True)
        self.assertNotIn("inside the short-term holding window", " ".join(r["reasons"]))

    def test_medium_trade_near_earnings_warns(self):
        r = full(earnings="2026-12-10")
        self.assertEqual(r["verdict"], "TRADE", r["reasons"])
        self.assertTrue(any("earnings on 2026-12-10" in w for w in r["warnings"]))

    def test_missing_or_past_earnings_date_waits(self):
        r = full(next_earnings=None, sources_check=check_file(ledger(q3=dict(event_date=None))))
        self.assertIn("next earnings date not given", " ".join(r["reasons"] + r["sources"]["problems"]))
        r = full(earnings="2026-10-01")
        self.assertIn("has passed", " ".join(r["sources"]["problems"]))

    def test_earnings_date_must_match_the_ledger(self):
        # review finding 1: a made-up far-away date used to bypass the earnings gate
        r = full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file(),
                 sources_check=check_file(ledger(q3=dict(event_date="2026-11-10"))), next_earnings="2099-01-01")
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("does not match the earliest earnings date in the source ledger", " ".join(r["reasons"]))
        r = full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file(),
                 sources_check=check_file(ledger(q3=dict(event_date="2026-11-10"))), next_earnings=None)
        self.assertIn("inside the short-term holding window", " ".join(r["reasons"]))

    def test_earnings_window_uses_the_later_date(self):
        st.CLOCK = sc.CLOCK = lambda: NOW
        r = full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file(), earnings="2026-11-26",
                 as_of="2026-11-04", boycott_result=bres(as_of="2026-11-04"), shariah_result=sres(as_of="2026-11-04"))
        self.assertIn("inside the short-term holding window", " ".join(r["reasons"]))

    def test_fee_share_blocks_small_short_trades(self):
        # tiny target: costs ~1% round trip vs a 2.5% gross move -> > 25% of the profit
        r = full(horizon="short", entry=100, stop=99, t1=102.5, t2=103, next_earnings="2027-01-28",
                 profile="aggressive")
        self.assertIn("fees and spread take", " ".join(r["reasons"]))
        self.assertGreater(r.get("fee_check", {}).get("costs_pct_of_gross_profit", 100) if r.get("fee_check") else 100, 25)

    def test_fee_check_reported_on_trades(self):
        fc = full()["fee_check"]
        self.assertLess(fc["costs_pct_of_gross_profit"], 25)
        self.assertGreater(fc["round_trip_costs_at_t1"], 0)

    def test_signals_avoid_blocks_and_caution_limits_horizon(self):
        r = full(signals=sig_file("avoid"))
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("signals say avoid", " ".join(r["reasons"]))
        r = full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file("caution"))
        self.assertIn("no short-term entry", " ".join(r["reasons"]))
        r = full(signals=sig_file("caution"))
        self.assertEqual(r["verdict"], "TRADE", r["reasons"])

    def test_signals_must_match_and_be_fresh(self):
        self.assertIn("not ABC", " ".join(full(signals=sig_file(ticker="XYZ"))["reasons"]))
        self.assertIn("re-run signals.py", " ".join(full(signals=sig_file(end="2026-10-20"))["reasons"]))
        self.assertTrue(any("signals not run" in w for w in full()["warnings"]))

    def test_dividend_after_withholding(self):
        r = full(horizon="long", stop=85, t1=135, t2=150, dividend_yield_pct=3.0, dividend_withholding_pct=30)
        d = r["dividend"]
        self.assertEqual(d["net_yield_pct"], 2.1)
        self.assertAlmostEqual(d["est_annual_net"], round(r["total_order_value"] * 0.021, 2), places=2)
        self.assertTrue(any("US withholding" in w for w in r["warnings"]))
        self.assertIn("DIVIDEND: 3.00% -> 2.10% AFTER 30% US TAX", rs.render([r]))

    def test_output_explains_new_reasons(self):
        text = rs.render([full(signals=sig_file("avoid"))])
        self.assertIn("WHY: PRICE TREND IS DOWN (SIGNALS SAY AVOID).", text)
        text = rs.render([full(horizon="short", stop=96, t1=108, t2=112, signals=sig_file(), earnings="2026-11-20")])
        self.assertIn("WHY: EARNINGS COME BEFORE THIS SHORT TRADE WOULD END.", text)


class Journal(Gates):
    def plan(self):
        return full()

    def test_round_trip_scored_after_fees_and_charity(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        p = self.plan()
        t = jn.open_trade(j, p, paper=True, tid="ABC-1")
        jn.add_fill(j, "ABC-1", "buy", 9, 100.0, 4.50, "2026-11-06")
        jn.add_fill(j, "ABC-1", "sell", 4, 120.0, 2.40, "2026-12-01")
        self.assertEqual(t["status"], "open")
        jn.add_fill(j, "ABC-1", "sell", 5, 130.0, 3.25, "2027-01-10")
        t["purification_paid"] = 0.40
        self.assertEqual(t["status"], "closed")
        c = jn.score(t)
        expected = (4 * 120 - 2.40) + (5 * 130 - 3.25) - (9 * 100 + 4.50) - 0.40
        self.assertAlmostEqual(c["pnl"], round(expected, 2))
        self.assertAlmostEqual(c["r"], round(expected / p["downside"]["executable_stop_downside"], 3))

    def test_report_metrics_benchmark_and_small_sample_verdict(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        for i, (buy, sell) in enumerate([(100, 110), (100, 95), (100, 120)]):
            jn.open_trade(j, self.plan(), tid=f"T{i}")
            jn.add_fill(j, f"T{i}", "buy", 9, float(buy), 4.5, "2026-11-06")
            jn.add_fill(j, f"T{i}", "sell", 9, float(sell), 4.5, "2026-12-06")
        bench = [dict(date="2026-11-06", close=50.0), dict(date="2026-12-06", close=51.0)]
        r = jn.report(j, bench)
        self.assertEqual((r["closed_trades"], r["win_rate_pct"]), (3, 66.7))
        self.assertAlmostEqual(r["total_pnl"], round(9 * 10 + 9 * -5 + 9 * 20 - 6 * 4.5, 2))
        self.assertAlmostEqual(r["benchmark"]["benchmark_pnl"], round(3 * (904.5 * 0.02), 2))
        self.assertIn("too few closed trades", r["verdict"])
        self.assertGreater(r["max_drawdown_usd"], 0)

    def test_guards(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        with self.assertRaises(jn.JournalError):
            jn.open_trade(j, dict(full(), verdict="WATCHLIST"))
        jn.open_trade(j, self.plan(), tid="X")
        jn.add_fill(j, "X", "buy", 5, 100.0, 1.0, "2026-11-06")
        with self.assertRaises(jn.JournalError):
            jn.add_fill(j, "X", "sell", 6, 100.0, 1.0, "2026-11-07")     # no short selling
        with self.assertRaises(jn.JournalError):
            jn.add_fill(j, "X", "buy", 1, -5.0, 1.0, "2026-11-07")
        self.assertEqual(jn.report(j)["verdict"], "no closed trades yet")

    def test_paper_and_real_kept_apart(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        for tid, paper in (("P", True), ("R", False)):
            jn.open_trade(j, self.plan(), paper=paper, tid=tid)
            jn.add_fill(j, tid, "buy", 9, 100.0, 4.5, "2026-11-06")
            jn.add_fill(j, tid, "sell", 9, 110.0 if paper else 90.0, 4.5, "2026-11-20")
        self.assertGreater(jn.report(j, which="paper")["total_pnl"], 0)
        self.assertLess(jn.report(j, which="real")["total_pnl"], 0)


class Expiry(unittest.TestCase):
    def test_warns_30_days_before(self):
        items, warnings = rc.expiry_report(dt.date(2027, 2, 10))
        shariah = [x for x in items if x["item"].startswith("Shariah")]
        self.assertTrue(all(x["status"] == "expires soon" for x in shariah))
        self.assertTrue(any("re-verify" in w for w in warnings))

    def test_expired_and_ok(self):
        items, _ = rc.expiry_report(dt.date(2028, 1, 2))
        self.assertEqual(next(x for x in items if x["item"] == "NYSE holiday calendar")["status"], "expired")
        items, warnings = rc.expiry_report(dt.date(2026, 11, 9))
        self.assertEqual(warnings, [])

    def test_stale_source_registry_blocks_check(self):
        out = sc.check(ledger(), now=dt.datetime(2027, 6, 1, 15, 0, tzinfo=dt.timezone.utc))
        self.assertTrue(any("sources.json last verified" in b for b in out["blocking"]))

    def test_future_registry_date_blocks_check(self):
        reg = dict(sc.load_registry(), verified_on="2027-01-01")
        self.assertTrue(any("in the future" in b for b in sc.check(ledger(), reg=reg, now=NOW)["blocking"]))


class ReviewRegressions(Gates):
    """One test per finding of the independent v4.6 review (and four from the end-to-end run)."""

    def test_f2_each_wait_reason_explained_separately(self):
        led = ledger(q0=dict(observed_at="2026-11-05T14:30:00-05:00"), q3=dict(event_date=None))  # stale quote, no date
        r = full(horizon="short", stop=96, t1=110, t2=115, sources_check=check_file(led), next_earnings=None)
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertGreaterEqual(len(r["reasons"]), 3)       # sources, earnings and signals stay separate reasons
        text = rs.render([r])
        self.assertIn("WHY: SOME DATA IS OLD, MISSING, OR SOURCES DISAGREE.", text)
        self.assertIn("WHY: NEXT EARNINGS DATE NOT CHECKED.", text)
        self.assertIn("WHY: TREND NOT CHECKED. SHORT TRADES NEED IT.", text)

    def test_f3_short_selling_state_error_not_called_price_under_1(self):
        self.assertEqual(rs.explain("portfolio state error: sell order exceeds shares held: short selling is not supported")[0],
                         "YOUR HOLDINGS DATA HAS AN ERROR.")
        self.assertEqual(rs.explain("prices under $1.00 are not supported")[0], "PRICE UNDER $1. NOT SUPPORTED.")

    def test_f4_patterns_now_match(self):
        self.assertIn("AT OR UNDER ITS STOP", rs.explain("a holding is at or below its stop/review level: reconcile it")[0])
        self.assertIn("GOLD/SILVER", rs.explain("metals allocation cap reached")[0])
        self.assertEqual(rs.explain("--sector-weights is required for stocks and ETFs (sector data missing)")[0],
                         "SECTOR DATA MISSING.")
        self.assertEqual(rs.explain("--as-of (today's date) is required for an executable plan")[0],
                         "TODAY'S DATE MISSING.")

    def _closed(self, j, tid, buy, sell, shares=9, planned_shares=None):
        p = full()
        if planned_shares:
            p = dict(p, shares=planned_shares)
        jn.open_trade(j, p, tid=tid)
        jn.add_fill(j, tid, "buy", shares, float(buy), 4.5, "2026-11-06")
        jn.add_fill(j, tid, "sell", shares, float(sell), 4.5, "2026-12-06")

    def test_f5_verdict_needs_positive_dollars(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        for i in range(20):    # many small R wins with one big-dollar loser on a large partial-free position
            self._closed(j, f"W{i}", 100, 101)
        self._closed(j, "L", 100, 60, shares=9)
        r = jn.report(j)
        if r["total_pnl"] <= 0:
            self.assertIn("not working", r["verdict"])

    def test_f5_negative_total_with_positive_r_is_not_positive(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        for i in range(19):
            self._closed(j, f"S{i}", 100, 103, shares=1, planned_shares=1)    # tiny wins, big R (1 share)
        self._closed(j, "BIG", 100, 80, shares=9)                             # one large loss in dollars
        r = jn.report(j)
        self.assertLess(r["total_pnl"], 0)
        self.assertIn("not working", r["verdict"])

    def test_f6_benchmark_unavailable_is_said(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        for i in range(20):
            self._closed(j, f"T{i}", 100, 110)
        r = jn.report(j, [dict(date="2030-01-01", close=1.0)])
        self.assertFalse(r["benchmark"]["available"])
        self.assertIn("benchmark unavailable", r["verdict"])
        self.assertIn("BENCHMARK: NO PRICES", jn.text(r))

    def test_f7_r_scales_with_partial_fill(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        p = full()
        jn.open_trade(j, p, tid="P")
        stop = p["stop_level"]
        jn.add_fill(j, "P", "buy", 2, 100.0, 0.5, "2026-11-06")
        jn.add_fill(j, "P", "sell", 2, stop, 0.5, "2026-11-10")
        c = jn.score(j["trades"][0])
        self.assertLess(c["r"], -0.8)      # about -1R for the shares actually bought, not -0.2

    def test_f8_and_mine_ledger_ids_never_collide(self):
        path = os.path.join(tempfile.mkdtemp(), "L.json")
        add = lambda url, src_extra=(): lg.main(["add", "--ledger", path, "--category", "quote", "--ticker", "ABC",
                                                 "--url", url, "--value", "100", "--observed-at", QT, *src_extra])
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            add("https://www.nasdaq.com/a")
            add("https://finance.yahoo.com/quote/ABC")
            lg.main(["drop", "--ledger", path, "--id", "ABC-quote-1"])
            add("https://stooq.com/q/?s=abc.us")
            lg.main(["add", "--ledger", path, "--category", "news", "--url", "https://www.reuters.com/x",
                     "--published-at", "2026-11-05", "--claim-id", "c"])
        with open(path) as f:
            ids = [x["id"] for x in json.load(f)["items"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("ABC-quote-3", ids)
        self.assertIn("news-1", ids)

    def test_f9_market_down_also_applies_to_unknown(self):
        s = sg.one("NEW", series(n=150, drift=0.002), market_rows=series(drift=-0.002))
        self.assertEqual(s["hint"], "CAUTION")

    def test_f9_short_term_needs_signals(self):
        r = full(horizon="short", stop=96, t1=110, t2=115)
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("short-term entries need the trend check", " ".join(r["reasons"]))

    def test_f10b_date_only_times_rejected(self):
        out = sc.check(ledger(q2=dict(observed_at="2026-11-05")), now=NOW)
        self.assertEqual(out["items"][2]["status"], "INVALID")
        out = sc.check(ledger(q4=dict(latest_filing_checked_at="2026-11-05")), now=NOW)
        self.assertEqual(out["items"][4]["status"], "INVALID")

    def test_f10c_boolean_price_rejected(self):
        self.assertEqual(sc.check(ledger(q0=dict(value=True)), now=NOW)["items"][0]["status"], "INVALID")

    def test_mine_no_buy_shows_also_needed(self):
        r = full(boycott_result=bres(ohchr="match"), sources_check="")
        self.assertEqual(r["verdict"], "NO TRADE")
        text = rs.render([r])
        self.assertIn("ALSO NEEDED: SOURCES NOT CHECKED.", text)

    def test_mine_signals_price_must_be_near_market(self):
        r = full(signals=sig_file(price=60.0))
        self.assertIn("wrong ticker or wrong price file", " ".join(r["reasons"]))
        r = full(signals=sig_file(price=94.0))
        self.assertEqual(r["verdict"], "TRADE", r["reasons"])
        self.assertTrue(any("from the market price" in w for w in r["warnings"]))

    def test_mine_journal_id_uses_plan_date(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        self.assertTrue(jn.open_trade(j, full())["id"].startswith("ABC-2026-11-05-"))


def edited(path, **changes):
    with open(path) as f:
        d = json.load(f)
    d.update(changes)
    return write_json(d)


class SecondAuditRegressions(Gates):
    """One test per finding of the second (adversarial) audit, plus two from the full verification run."""

    def test_a1_edited_signals_refused(self):
        avoid = sig_file("avoid")
        self.assertIn("signals say avoid", " ".join(full(signals=avoid)["reasons"]))
        for change in (dict(hint="OK", flags=[]), dict(history_through="2099-01-01"), dict(price=None)):
            r = full(signals=edited(avoid, **change))
            self.assertEqual(r["verdict"], "NO TRADE", change)
            self.assertIn("does not match a recomputation", " ".join(r["reasons"]))
        with open(avoid) as f:
            d = json.load(f)
        d.pop("inputs")
        self.assertIn("no usable recorded prices", " ".join(full(signals=write_json(d))["reasons"]))

    def test_a1_future_price_history_refused(self):
        r = full(signals=sig_file(end="2026-11-20"))
        self.assertIn("after today", " ".join(r["reasons"]))

    def test_a2_screen_expiry_recomputed_not_read(self):
        old_b = bres(as_of="2026-09-01", checked_on="2026-09-01")
        r = full(boycott_result=edited(old_b, expires_on="2099-12-31"))
        self.assertIn("boycott result expired on 2026-10-01", " ".join(r["reasons"]))
        old_s = sres(as_of="2026-07-01", methodology="msci")
        r = full(shariah_result=edited(old_s, expires_on="2099-12-31"))
        self.assertIn("Shariah result expired on 2026-10-01", " ".join(r["reasons"]))
        r = full(shariah_result=edited(sres(), as_of="2026-11-04"))
        self.assertIn("does not match its recorded inputs", " ".join(r["reasons"]))

    def test_a3_boycott_asset_must_match_evidence(self):
        res = json.loads(open(bres()).read())
        res["asset"] = "etf"                      # evidence was for a stock: no ETF look-through was done
        st_, why = bsc.validate_result(res, "ABC", "etf", "US0000000001", "2026-11-05")
        self.assertEqual(st_, "UNVERIFIED")
        self.assertIn("gathered for asset type 'stock'", why[0])

    def test_a4_earliest_earnings_date_always_applies(self):
        led = ledger()
        led["items"].append(dict(category="earnings_date", ticker="ABC", source="yahoo",
                                 url="https://finance.yahoo.com/quote/ABC/earnings",
                                 observed_at="2026-11-05T15:00:00-05:00", event_date="2027-02-01"))
        led["items"][3]["event_date"] = "2026-11-16"
        f = check_file(led)
        r = full(horizon="short", stop=96, t1=110, t2=115, signals=sig_file(), sources_check=f, next_earnings="2027-02-01")
        self.assertIn("earliest earnings date", " ".join(r["reasons"]))
        r = full(horizon="short", stop=96, t1=110, t2=115, signals=sig_file(), sources_check=f, next_earnings=None)
        self.assertIn("inside the short-term holding window", " ".join(r["reasons"]))
        self.assertTrue(any("sources disagree on the earnings date" in w for w in r["warnings"]))

    def _state(self, holdings):
        return write_json(pst.build(dict(cash=10000, holdings=holdings, orders=[]), fee=st.make_fee(0.005, 0.5, 30)))

    def test_a5_related_tickers_do_not_unlock_max_positions(self):
        hold = [dict(ticker=f"H{i}", asset="stock", shares=1, avg_cost=100, price=100, level=95, level_type="hard",
                     sector_weights={f"S{i}": 1}) for i in range(8)]
        state = self._state(hold)
        r = full(state=state, portfolio=None, cash=None, related_tickers="H0")
        self.assertIn("maximum number of stock/ETF positions", " ".join(r["reasons"]))

    def test_a6_sector_alias_merged(self):
        a = st.build_parser().parse_args(["--asset", "stock", "--profile", "balanced", "--quote-status", "live",
                                          "--boycott-mode", "exclude", "--shariah-mode", "exclude",
                                          "--sector-weights", '{"technology ": 1}',
                                          "--portfolio-sectors", '{"Technology": 2900}'])
        w, ps, probs = st.parse_sector_weights(a)
        self.assertEqual((w, ps, probs), ({"Technology": 1.0}, {"Technology": 2900.0}, []))

    def test_a7_unknown_asset_rejected(self):
        with self.assertRaises(ValueError):
            pst.build(dict(cash=1000, holdings=[dict(ticker="X", asset="Stock", shares=1, avg_cost=1, price=1)],
                           orders=[]), fee=st.make_fee(0.005, 0.5, 30))

    def test_a8_projected_state_independent_of_plan_order(self):
        p1, p2 = full(), full(ticker="ABC", sector_weights=json.dumps({"Health": 1.0}))
        p2 = dict(p2, ticker="XYZ", tranches=[dict(p2["tranches"][0], price=50.0)])
        state = dict(cash=10000, holdings=[], orders=[])
        fee = st.make_fee(0.005, 0.5, 30)
        a = pst.build(state, [p1, p2], fee=fee)["projected"]["sector_exposure"]
        b = pst.build(state, [p2, p1], fee=fee)["projected"]["sector_exposure"]
        self.assertEqual(a, b)
        with self.assertRaises(ValueError):
            pst.build(state, [p1, p1], fee=fee)

    def test_a9_company_cannot_be_sized_as_metal(self):
        r = full(asset="metal", isin="", sector_weights=None)
        self.assertIn("a company is a stock", " ".join(r["reasons"]))

    def test_a10_edited_verdict_refused_downstream(self):
        wl = full(quote_status="previous_close")
        fake = dict(wl, verdict="TRADE")
        self.assertNotIn("\nBUY ABC", rs.render([fake]))
        self.assertIn("THIS PLAN FILE WAS CHANGED AFTER THE ENGINE MADE IT.", rs.render([fake]))
        with self.assertRaises(jn.JournalError):
            jn.open_trade(dict(schema=jn.SCHEMA, trades=[]), fake)
        with self.assertRaises(ValueError):
            pst.build(dict(cash=10000, holdings=[], orders=[]), [fake], fee=st.make_fee(0.005, 0.5, 30))

    def test_a11_stale_as_of_does_not_extend_screens(self):
        st.CLOCK = sc.CLOCK = lambda: dt.datetime(2026, 11, 9, 20, 35, tzinfo=dt.timezone.utc)
        old = bres(as_of="2026-10-09", checked_on="2026-10-09")      # valid through 2026-11-08
        a = st.build_parser().parse_args(["--asset", "stock", "--ticker", "ABC", "--isin", "US0000000001",
                                          "--profile", "balanced", "--quote-status", "live", "--as-of", "2026-11-08",
                                          "--boycott-mode", "exclude", "--boycott-result", old,
                                          "--shariah-mode", "exclude"])
        summary, block = st.boycott_check(a)
        self.assertIn("expired", " ".join(block))

    def test_a12_pre_open_quote_refused_after_open(self):
        st.CLOCK = sc.CLOCK = lambda: dt.datetime(2026, 11, 5, 14, 31, tzinfo=dt.timezone.utc)   # 09:31 New York
        a = st.build_parser().parse_args(["--asset", "stock", "--profile", "balanced", "--quote-status", "live",
                                          "--boycott-mode", "exclude", "--shariah-mode", "exclude",
                                          "--quote-time", "2026-11-05T09:20:00-05:00", "--quote-source", "Nasdaq",
                                          "--as-of", "2026-11-05"])
        self.assertIn("before today's open", st.quote_check(a))

    def test_a13_unknown_calendar_year_not_executable(self):
        st.CLOCK = sc.CLOCK = lambda: dt.datetime(2028, 1, 4, 15, 0, tzinfo=dt.timezone.utc)
        a = st.build_parser().parse_args(["--asset", "stock", "--profile", "balanced", "--quote-status", "live",
                                          "--boycott-mode", "exclude", "--shariah-mode", "exclude",
                                          "--quote-time", "2028-01-04T09:55:00-05:00", "--quote-source", "Nasdaq",
                                          "--as-of", "2028-01-04"])
        self.assertIn("holiday list not loaded", st.quote_check(a))

    def test_a14_journal_fills_in_order(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        jn.open_trade(j, full(), tid="T")
        with self.assertRaises(jn.JournalError):
            jn.add_fill(j, "T", "sell", 1, 100.0, 0.5, "2026-11-08")         # first fill must be a buy
        jn.add_fill(j, "T", "buy", 5, 100.0, 0.5, "2026-11-12")
        with self.assertRaises(jn.JournalError):
            jn.add_fill(j, "T", "sell", 5, 110.0, 0.5, "2026-11-08")         # before the buy

    def test_a15_bad_inputs_fail_cleanly(self):
        import contextlib, io
        d = tempfile.mkdtemp()
        empty, nocol, notsig, lst = (os.path.join(d, n) for n in ("e.csv", "n.csv", "x.json", "l.json"))
        open(empty, "w").write("date,close\n")
        open(nocol, "w").write("date,price\n2026-11-05,1\n")
        open(notsig, "w").write('{"a": 1}')
        open(lst, "w").write("[1, 2]")
        for argv in (["one", "--ticker", "A", "--prices", empty], ["one", "--ticker", "A", "--prices", nocol],
                     ["one", "--ticker", "A", "--prices", nocol, "--eps", "1,2,x"], ["rank", "--signals", notsig]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(sg.main(argv), 1, argv)
            self.assertIn("error", out.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                mc.main(["--at", "garbage"])
            with self.assertRaises(SystemExit):
                rs.main(["--plans", lst])
        with self.assertRaises(ValueError):
            lg.load(lst)

    def test_v1_source_warnings_stay_with_their_ticker(self):
        led = ledger()
        led["items"].append(dict(category="quote", ticker="ZZZ", source="nasdaq", url="https://www.nasdaq.com/zzz",
                                 observed_at=QT, value=10.0))
        r = full(sources_check=check_file(led))
        self.assertFalse(any(w.startswith("ZZZ:") for w in r["warnings"]))

    def test_v2_metal_structure_documented(self):
        with open(os.path.join(HERE, "..", "SKILL.md")) as f:
            self.assertIn("--metal-structure physical", f.read())


class TreasuryControls(Gates):
    """Controls found in the treasury audit."""

    H = dict(ticker="AAA", asset="stock", shares=10, avg_cost=100, price=110, level=100, level_type="hard",
             sector_weights={"Tech": 1})

    def test_duplicate_holding_rows_rejected(self):
        with self.assertRaises(ValueError):
            pst.build(dict(cash=5000, holdings=[self.H, self.H], orders=[]), fee=st.make_fee(0.005, 0.5, 30))

    def test_duplicate_order_ids_rejected(self):
        o = dict(id="o1", ticker="BBB", asset="stock", side="buy", limit=50, shares=1, status="open", filled_shares=0,
                 sector_weights={"Health": 1})
        with self.assertRaises(ValueError):
            pst.build(dict(cash=5000, holdings=[], orders=[o, o]), fee=st.make_fee(0.005, 0.5, 30))

    def test_unverified_fee_schedule_shown(self):
        self.assertIn("FEE SCHEDULE: USER-PROVIDED, NOT VERIFIED.", rs.render([full()]))

    def test_charity_rounds_up(self):
        import shariah_screen as shs
        self.assertEqual(shs.cents_up(0.741), 0.75)
        self.assertEqual(shs.cents_up(2.25), 2.25)
        self.assertEqual(shs.cents_up(2.2500000001), 2.25)

    def test_journal_audit_trail_and_reconcile(self):
        j = dict(schema=jn.SCHEMA, trades=[])
        p = full()
        t = jn.open_trade(j, p, tid="R1")
        self.assertEqual(len(t["audit"]["plan_sha256"]), 64)
        self.assertEqual(t["audit"]["fee_schedule"], "user-provided")
        jn.add_fill(j, "R1", "buy", 9, 100.0, 4.5, "2026-11-06")
        ok = jn.reconcile(j, dict(holdings=[dict(ticker="ABC", shares=9)]))
        self.assertTrue(ok["ok"])
        brk = jn.reconcile(j, dict(holdings=[dict(ticker="ABC", shares=7), dict(ticker="ZZZ", shares=3)]))
        self.assertFalse(brk["ok"])
        self.assertEqual({r["ticker"]: r["difference"] for r in brk["rows"]}, {"ABC": -2, "ZZZ": 3})


class MarketClock(Gates):
    def at(self, iso):
        return mc.status(dt.datetime.fromisoformat(iso.replace("Z", "+00:00")))

    def test_regular_session(self):
        self.assertTrue(self.at("2026-11-05T20:35:00Z")["open"])

    def test_holiday_weekend_hours(self):
        self.assertIn("Thanksgiving", self.at("2026-11-26T15:00:00Z")["reason"])
        self.assertEqual(self.at("2026-11-07T15:00:00Z")["reason"], "weekend")
        self.assertEqual(self.at("2026-11-09T13:07:00Z")["reason"], "before the open")
        self.assertEqual(self.at("2026-11-05T21:05:00Z")["reason"], "after the close")

    def test_early_close_and_next_open(self):
        s = self.at("2026-11-27T18:30:00Z")             # 13:30 New York, after the 13:00 early close
        self.assertFalse(s["open"])
        self.assertEqual(s["next_open_new_york"], "2026-11-30 09:30")

    def test_dst_switch(self):
        self.assertTrue(self.at("2026-03-09T13:45:00Z")["open"])     # 09:45 EDT after the March 8 switch
        self.assertFalse(self.at("2026-03-06T14:15:00Z")["open"])    # 09:15 EST before it

    def test_unknown_year_warns(self):
        self.assertIn("warning", self.at("2028-01-03T15:00:00Z"))

    def test_calendar_matches_nyse_page(self):
        self.assertEqual(len([d for d in mc.NYSE_HOLIDAYS if d.startswith("2026")]), 10)
        self.assertEqual(len([d for d in mc.NYSE_HOLIDAYS if d.startswith("2027")]), 10)

    def test_engine_waits_when_closed(self):
        thanksgiving = dt.datetime(2026, 11, 26, 15, 5, tzinfo=dt.timezone.utc)
        st.CLOCK = sc.CLOCK = lambda: thanksgiving
        r = full(as_of="2026-11-26", quote_time="2026-11-26T10:00:00-05:00")
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("NYSE is closed now (NYSE holiday: Thanksgiving Day", " ".join(r["reasons"]))
        text = rs.render([r])
        self.assertIn("NYSE: CLOSED (NYSE HOLIDAY: THANKSGIVING DAY). NEXT OPEN 2026-11-27 09:30", text)
        self.assertIn("WHY: US MARKET IS CLOSED NOW.", text)

    def test_open_market_line(self):
        self.assertIn("NYSE: OPEN. CLOSES 16:00 NEW YORK TIME.", rs.render([full()]))


class LedgerHelper(Gates):
    def run_cli(self, *args):
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = lg.main(list(args))
        out = buf.getvalue()
        return code, (json.loads(out) if out.lstrip().startswith("{") else out)

    def setUp(self):
        super().setUp()
        self.path = os.path.join(tempfile.mkdtemp(), "LEDGER.json")

    def read(self):
        with open(self.path) as f:
            return json.load(f)

    def test_add_recognises_source_and_checks_it(self):
        code, r = self.run_cli("add", "--ledger", self.path, "--category", "quote", "--ticker", "abc",
                               "--url", "https://www.nasdaq.com/market-activity/stocks/abc", "--value", "100",
                               "--observed-at", QT)
        self.assertEqual((code, r["status"], r["source"], r["tier"]), (0, "FRESH", "Nasdaq", 1))
        item = self.read()["items"][0]
        self.assertEqual((item["source"], item["ticker"]), ("nasdaq", "ABC"))

    def test_unknown_site_rejected(self):
        code, r = self.run_cli("add", "--ledger", self.path, "--category", "news", "--url",
                               "https://randomblog.example/post", "--published-at", "2026-11-05", "--claim-id", "x")
        self.assertEqual(code, 1)
        self.assertFalse(r["added"])

    def test_wrong_category_flagged_immediately(self):
        code, r = self.run_cli("add", "--ledger", self.path, "--category", "fundamentals", "--ticker", "ABC",
                               "--url", "https://finance.yahoo.com/quote/ABC/financials", "--published-at",
                               "2026-10-31", "--form", "10-Q", "--period-end", "2026-09-27",
                               "--latest-filing-checked-at", "now")
        self.assertEqual((code, r["status"]), (1, "BAD_SOURCE"))

    def test_same_page_replaces_and_now_fills_times(self):
        args = ["add", "--ledger", self.path, "--category", "consensus", "--ticker", "ABC",
                "--url", "https://stockanalysis.com/stocks/abc/forecast/"]
        self.run_cli(*args)
        self.run_cli(*args)
        items = self.read()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["observed_at"], NOW.isoformat(timespec="seconds"))

    def test_built_ledger_feeds_the_engine(self):
        for it in ledger()["items"]:
            args = ["add", "--ledger", self.path, "--category", it["category"], "--url", it["url"],
                    "--observed-at", it["observed_at"]]
            for k, v in it.items():
                if k not in ("category", "url", "observed_at", "source"):
                    args += ["--" + k.replace("_", "-"), str(v)]
            self.run_cli(*args)
        out = os.path.join(os.path.dirname(self.path), "SOURCES_CHECK.json")
        code, _ = self.run_cli("check", "--ledger", self.path, "--out", out)
        self.assertEqual(code, 0)
        self.assertEqual(full(sources_check=out)["verdict"], "TRADE")


def series(n=300, start=50.0, drift=0.001, wiggle=0.01):
    rows, p = [], start
    d0 = dt.date(2025, 8, 1)
    for i in range(n):
        p *= 1 + drift + wiggle * math.sin(i / 3.0)
        rows.append(dict(date=(d0 + dt.timedelta(days=i)).isoformat(), close=round(p, 4),
                         high=round(p * 1.01, 4), low=round(p * 0.99, 4)))
    return rows


class Signals(unittest.TestCase):
    def test_uptrend_ok(self):
        s = sg.one("UP", series(drift=0.002))
        self.assertTrue(s["trend_filter_pass"])
        self.assertGreater(s["momentum_12_1"], 0)
        self.assertEqual(s["hint"], "OK")
        self.assertIsNotNone(s["atr14"])

    def test_downtrend_avoid(self):
        s = sg.one("DN", series(drift=-0.002))
        self.assertEqual(s["hint"], "AVOID")
        self.assertIn("downtrend", " ".join(s["flags"]))

    def test_market_filter_down_cautions(self):
        s = sg.one("UP", series(drift=0.002), market_rows=series(drift=-0.002))
        self.assertEqual(s["market_regime"]["state"], "DOWN")
        self.assertEqual(s["hint"], "CAUTION")

    def test_momentum_skips_last_month(self):
        rows = series(n=260, drift=0.0, wiggle=0.0)
        for r in rows[-21:]:
            r["close"] = 500.0          # a last-month spike must not count (12-1 skip)
        self.assertAlmostEqual(sg.momentum_12_1([r["close"] for r in rows])[0], 0.0, places=6)

    def test_sue(self):
        eps = [2.0, 1.5, 1.4, 1.3, 1.0, 1.0, 1.1, 1.0, 0.9, 1.0, 1.0, 1.0]
        ue = [eps[k] - eps[k + 4] for k in range(8)]
        import statistics
        self.assertAlmostEqual(sg.sue(eps), ue[0] / statistics.stdev(ue))
        self.assertIsNone(sg.sue(eps[:11]))

    def test_pivot(self):
        p = sg.pivot([dict(date="2026-11-05", close=100.0, high=102.0, low=98.0)])
        self.assertEqual((p["center"], p["resistance"], p["support"]), (100.0, 102.0, 98.0))

    def test_short_history_is_unknown_not_guessed(self):
        s = sg.one("NEW", series(n=60))
        self.assertIsNone(s["sma"]["ma200"])
        self.assertIn("200-day MA", s["missing"])
        self.assertEqual(s["hint"], "UNKNOWN")

    def test_avoid_signal_prints_no_buy_with_why(self):
        text = rs.render([], signals=[sg.one("DN", series(drift=-0.002))])
        self.assertIn("NO BUY DN\n  WHY: DOWNTREND", text)
        self.assertIn("FIX: WAIT UNTIL PRICE IS BACK ABOVE ITS 200-DAY AVERAGE.", text)

    def test_rank_prefers_momentum_and_low_vol_and_sorts_avoid_last(self):
        a = sg.one("A", series(drift=0.003, wiggle=0.005))
        b = sg.one("B", series(drift=0.001, wiggle=0.02))
        c = sg.one("C", series(drift=-0.002))
        r = sg.rank([b, c, a])
        self.assertEqual([x["ticker"] for x in r["ranking"]], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
