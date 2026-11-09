#!/usr/bin/env python3
"""v4.5 hardening tests for the v4.4 audit: worst-case Unclassified sector exposure (randomized,
including a state -> sizing chain), the one-cent price grid, the T-bill market-price band and
wording, and strict working-order status/quantity validation."""
import datetime as dt, json, os, random, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import size_trade as _st_v46  # noqa: E402
# v4.6: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v46_mandatory.py tests them switched on.
_st_v46.SCREENS_REQUIRED = _st_v46.SOURCES_REQUIRED = _st_v46.MARKET_CLOCK_REQUIRED = False
import fees  # noqa: E402
import portfolio_state as ps  # noqa: E402
import size_trade as st  # noqa: E402

FEE = fees.broker_profile("bank-al-etihad-jo")[1]
CLOCK = dt.datetime(2026, 11, 5, 20, 35, tzinfo=dt.timezone.utc)
_real = None


def setUpModule():
    global _real
    _real, st.CLOCK = st.CLOCK, (lambda: CLOCK)


def tearDownModule():
    st.CLOCK = _real


def trade(**kw):
    base = dict(asset="stock", ticker="ABC", isin="US0000000001", profile="balanced", horizon="short",
                portfolio=10000, cash=10000, entry=100, stop=94, t1=112, t2=119, market_price=100,
                sector_weights='{"Tech": 1}', quote_status="live", quote_time="2026-11-05T15:30:00-05:00",
                quote_source="Test feed", as_of="2026-11-05", broker="bank-al-etihad-jo",
                boycott_mode="off", shariah_mode="off", friction_bps=0)
    base.update(kw)
    argv = []
    for k, v in base.items():
        if v is None:
            continue
        argv += [f"--{k.replace('_', '-')}"] + ([] if v is True else [str(v)])
    return st.compute(st.build_parser().parse_args(argv))


def tbill(**kw):
    return trade(**dict(dict(asset="tbill", ticker="TBIL", entry=None, stop=None, t1=None, t2=None,
                             sector_weights=None, amount=2000, price=50, market_price=50, yield_pct=4,
                             duration_yrs=0.15, hold_months=6), **kw))


class WorstCaseUnclassified(unittest.TestCase):
    def test_room_reduced_by_held_unclassified(self):
        r = trade(portfolio_sectors=json.dumps({"Unclassified": 2700}), cash=7300)
        self.assertEqual(r["limits"]["sector_room"]["Tech"], 300.0)
        self.assertLessEqual(r["total_order_value"], 300)
        self.assertTrue(any("no sector data" in w for w in r["warnings"]))

    def test_new_instrument_unclassified_weight_counts_everywhere(self):
        # Tech already $2,500 of a $3,000 cap; ETF is 50% Tech + 50% unknown -> up to 100% Tech worst case
        r = trade(asset="etf", sector_weights=json.dumps({"Tech": 0.5, "Unclassified": 0.5}),
                  portfolio_sectors=json.dumps({"Tech": 2500}))
        self.assertLessEqual(2500 + r["total_order_value"], 3000)

    def test_fully_unclassified_new_stock_checked_against_any_sector(self):
        r = trade(sector_weights=json.dumps({"Unclassified": 1}), portfolio_sectors=json.dumps({"Unclassified": 2950}))
        self.assertEqual(r["verdict"], "NO TRADE")            # only $50 of room: below the $100 minimum order
        r = trade(sector_weights=json.dumps({"Unclassified": 1}), portfolio_sectors=json.dumps({"Unclassified": 3000}))
        self.assertIn("sector cap reached: (any other sector)", " ".join(r["reasons"]))
        r = trade(sector_weights=json.dumps({"Unclassified": 1}), portfolio_sectors=json.dumps({"Tech": 2900}))
        self.assertLessEqual(2900 + r.get("total_order_value", 0), 3000)   # could be Tech

    def test_classified_portfolio_unchanged(self):
        r = trade(portfolio_sectors=json.dumps({"Tech": 1000, "Health": 2000}))
        self.assertEqual(r["limits"]["sector_room"], {"Tech": 2000.0})

    def test_random_no_assignment_breaks_a_cap(self):
        rnd = random.Random(5)
        sectors = ["Tech", "Health", "Energy"]
        for _ in range(150):
            port = {s: round(rnd.uniform(0, 2500), 2) for s in rnd.sample(sectors, rnd.randint(0, 3))}
            if rnd.random() < 0.7:
                port["Unclassified"] = round(rnd.uniform(0, 2500), 2)
            pick = rnd.sample(sectors, rnd.randint(1, 2))
            raw = [rnd.uniform(0.1, 1) for _ in pick] + ([rnd.uniform(0, 1)] if rnd.random() < 0.5 else [])
            names = pick + (["Unclassified"] if len(raw) > len(pick) else [])
            w = {n: x / sum(raw) for n, x in zip(names, raw)}
            r = trade(asset="etf", portfolio=10000, cash=10000, sector_weights=json.dumps(w),
                      portfolio_sectors=json.dumps(port), entry=20, stop=19, t1=23, t2=25, market_price=20)
            if r["verdict"] != "TRADE":
                continue
            v, cap = r["total_order_value"], 3000 + 1e-6
            held_u, new_u = port.get("Unclassified", 0), w.get("Unclassified", 0)
            for s in sectors:   # put ALL unclassified money (held and new) into s: the trade never pushes s over
                added = v * (w.get(s, 0) + new_u)
                if added > 0:
                    self.assertLessEqual(port.get(s, 0) + held_u + added, cap, (port, w, v, s))

    def test_state_to_sizing_chain(self):
        state = dict(cash=7300, orders=[], holdings=[dict(ticker="OLD", asset="stock", shares=27, price=100,
                                                          avg_cost=100, level=94, level_type="hard")])
        got = ps.build(state, fee=FEE)
        self.assertEqual(got["actual"]["sector_exposure"], {"Unclassified": 2700.0})
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            with open(p, "w") as f:
                json.dump(got, f)
            r = trade(state=p, portfolio=None, cash=None)
        self.assertLessEqual(2700 + r.get("total_order_value", 0), 3000)


class CentGrid(unittest.TestCase):
    def test_off_grid_levels_rejected(self):
        for kw in (dict(entry=100.004, market_price=100), dict(stop=94.005), dict(t1=112.001), dict(t2=119.009),
                   dict(entry=None, tranches="100,99.005,98", stop=95)):
            r = trade(**kw)
            self.assertEqual(r["verdict"], "NO TRADE", kw)
            self.assertIn("one-cent grid", " ".join(r["reasons"]), kw)

    def test_on_grid_floats_accepted(self):
        for kw in (dict(entry=100.1, market_price=100.1, stop=94.17, t1=112.07, t2=119.29),
                   dict(entry=33.33, market_price=33.33, stop=31.67, t1=37.33, t2=39.99)):
            self.assertEqual(trade(**kw)["verdict"], "TRADE", kw)

    def test_market_price_may_be_any_quote(self):
        self.assertEqual(trade(market_price=100.0049)["verdict"], "TRADE")

    def test_tbill_price_on_grid(self):
        self.assertEqual(tbill(price=50.005, market_price=50)["verdict"], "NO TRADE")


class TbillMarket(unittest.TestCase):
    def test_band(self):
        self.assertEqual(tbill()["verdict"], "TRADE")
        self.assertEqual(tbill(price=50.5)["verdict"], "TRADE")
        r = tbill(price=50.51)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("above the market price", " ".join(r["reasons"]))
        self.assertEqual(tbill(price=150)["verdict"], "NO TRADE")

    def test_missing_market_price_is_watchlist(self):
        r = tbill(market_price=None)
        self.assertEqual(r["verdict"], "WATCHLIST")
        self.assertIn("--market-price", " ".join(r["reasons"]))

    def test_wording_has_no_stop(self):
        n = tbill()["shares"]
        ready = tbill(confirm_order=f"TBIL|limit|50|{n}")["placement_status"]
        self.assertTrue(ready.startswith("ready to place"), ready)
        self.assertIn("no stop applies", ready)
        self.assertIn("interest rates", ready)
        prov = tbill()["placement_status"]
        self.assertIn("no stop applies", prov)
        self.assertNotIn("stop, where used", prov)

    def test_still_watchlist_on_stale_quote(self):
        self.assertEqual(tbill(quote_time="2026-11-05T14:00:00-05:00")["verdict"], "WATCHLIST")


def order(**kw):
    o = dict(id="o", ticker="AAA", asset="stock", side="buy", limit=100, shares=10, filled_shares=0,
             status="open", level=90, level_type="hard", sector_weights={"Tech": 1})
    o.update(kw)
    return {k: v for k, v in o.items() if v is not None}


class OrderStates(unittest.TestCase):
    def build(self, *orders):
        return ps.build(dict(cash=10000, holdings=[], orders=list(orders)), fee=FEE)

    def test_rejected(self):
        bad = [dict(status="unspecified"), dict(status=None), dict(status="OPEN"), dict(shares=0), dict(shares=-5),
               dict(shares=2.5), dict(shares=True), dict(filled_shares=-1), dict(filled_shares=1.5),
               dict(filled_shares=float("nan")), dict(status="partial", filled_shares=15),
               dict(status="open", filled_shares=3), dict(status="partial", filled_shares=0),
               dict(status="partial", filled_shares=10), dict(status="filled", filled_shares=11)]
        for kw in bad:
            with self.assertRaises(ValueError, msg=kw):
                self.build(order(**kw))

    def test_accepted(self):
        self.assertAlmostEqual(self.build(order())["actual"]["open_order_commitments"], 1000 + FEE(1000, 10), places=2)
        self.assertAlmostEqual(self.build(order(status="partial", filled_shares=4))["actual"]["open_order_commitments"],
                               600 + FEE(600, 6), places=2)
        for kw in (dict(status="filled", filled_shares=10), dict(status="filled", filled_shares=None),
                   dict(status="cancelled", filled_shares=3)):
            self.assertEqual(self.build(order(**kw))["actual"]["open_order_commitments"], 0.0, kw)

    def test_bad_state_reaches_sizing_as_no_trade(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                json.dump(dict(cash=10000, holdings=[], orders=[order(status="unspecified")]), f)
            out = subprocess.run([sys.executable, os.path.join(HERE, "portfolio_state.py"), "--input", p,
                                  "--broker", "bank-al-etihad-jo"], capture_output=True, text=True)
            sp = os.path.join(d, "state.json")
            with open(sp, "w") as f:
                f.write(out.stdout)
            r = trade(state=sp, portfolio=None, cash=None)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("unknown status", " ".join(r["reasons"]))


if __name__ == "__main__":
    unittest.main()
