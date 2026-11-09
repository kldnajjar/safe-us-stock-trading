#!/usr/bin/env python3
"""v4.4 hardening tests for the v4.3 independent audit (H1, H2, M1, M2) plus randomized property tests:
ETF boycott weight domains, buy/sell order accounting, state sector-weight validation, and the bounded
quantity search checked against the original linear scan."""
import datetime as dt, json, os, random, subprocess, sys, time, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import size_trade as _st_v48  # noqa: E402
# v4.8: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v48_mandatory.py tests them switched on.
_st_v48.SCREENS_REQUIRED = _st_v48.SOURCES_REQUIRED = _st_v48.MARKET_CLOCK_REQUIRED = False
import boycott_screen as bs  # noqa: E402
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


def etf_ev(**w):
    src = lambda: dict(finding="no_match", checked_on="2026-11-04", url="https://example.org/s")
    ev = dict(ticker="ABC", isin="US0000000001", entity="ABC ETF", asset="etf", identity_resolved=True,
              sources=dict(ohchr=dict(src(), list_version="A/HRC/63/20"), bds=src(), afsc=src(), whoprofits=src(),
                           sec=dict(src(), israel_hq=False, material_israel_ops=False)),
              etf=dict(screened_weight_pct=100, excluded_weight_pct=0, flagged_weight_pct=0))
    ev["etf"].update(w)
    return ev


def status(**w):
    return bs.screen(etf_ev(**w), "2026-11-05")["status"]


class EtfBoycottWeights(unittest.TestCase):
    def test_valid_clean_fund(self):
        self.assertEqual(status(), "REVIEWED_NO_MATCH")

    def test_out_of_range_and_non_numeric(self):
        for bad in (dict(screened_weight_pct=150), dict(screened_weight_pct=-1), dict(excluded_weight_pct=-10),
                    dict(flagged_weight_pct=101), dict(excluded_weight_pct=float("nan")),
                    dict(screened_weight_pct=float("inf")), dict(flagged_weight_pct=True),
                    dict(excluded_weight_pct="0")):
            self.assertEqual(status(**bad), "UNVERIFIED", bad)

    def test_parts_cannot_exceed_screened(self):
        self.assertEqual(status(excluded_weight_pct=60, flagged_weight_pct=50), "UNVERIFIED")

    def test_partial_screening_unverified(self):
        self.assertEqual(status(screened_weight_pct=99.5), "UNVERIFIED")

    def test_valid_flagged_and_excluded_still_classified(self):
        self.assertEqual(status(flagged_weight_pct=3), "FLAGGED")
        self.assertEqual(status(excluded_weight_pct=2), "EXCLUDED")

    def test_random_domain(self):
        rnd = random.Random(7)
        for _ in range(300):
            w = dict(screened_weight_pct=rnd.choice([100, rnd.uniform(-50, 200)]),
                     excluded_weight_pct=rnd.uniform(-20, 120), flagged_weight_pct=rnd.uniform(-20, 120))
            valid = (w["screened_weight_pct"] == 100 and all(0 <= v <= 100 for v in w.values())
                     and w["excluded_weight_pct"] + w["flagged_weight_pct"] <= 100)
            if not valid:
                self.assertEqual(status(**w), "UNVERIFIED", w)
            else:
                self.assertIn(status(**w), ("EXCLUDED", "FLAGGED", "REVIEWED_NO_MATCH"), w)


HOLD = dict(ticker="AAA", asset="stock", shares=10, price=100, avg_cost=90, level=94, level_type="hard",
            sector_weights={"Tech": 1})


def order(**kw):
    o = dict(id="o1", ticker="AAA", asset="stock", side="buy", limit=100, shares=5, filled_shares=0,
             status="open", level=94, level_type="hard", sector_weights={"Tech": 1})
    o.update(kw)
    return o


class OrderSides(unittest.TestCase):
    def build(self, orders, holdings=(HOLD,)):
        return ps.build(dict(cash=9000, holdings=list(holdings), orders=orders), fee=FEE)

    def test_sell_reserves_nothing_and_adds_no_exposure(self):
        got = self.build([order(side="sell")])
        self.assertEqual(got["actual"]["open_order_commitments"], 0.0)
        self.assertEqual(got["actual"]["ticker_exposure"]["AAA"], 1000.0)
        self.assertEqual(got["actual"]["sector_exposure"]["Tech"], 1000.0)
        self.assertEqual(got["actual"]["shares_reserved_for_sale"], {"AAA": 5})
        self.assertEqual(got["size_trade_args"]["committed"], 0.0)
        self.assertEqual(got["actual"]["stock_etf_positions"], 1)

    def test_sell_keeps_holding_risk_until_executed(self):
        no_order = self.build([])
        with_sell = self.build([order(side="sell")])
        self.assertEqual(with_sell["actual"]["executable_stop_downside"], no_order["actual"]["executable_stop_downside"])

    def test_buy_still_reserves_and_adds_exposure(self):
        got = self.build([order(side="buy")])
        self.assertAlmostEqual(got["actual"]["open_order_commitments"], 500 + FEE(500, 5), places=2)
        self.assertEqual(got["actual"]["ticker_exposure"]["AAA"], 1500.0)

    def test_partial_sell_counts_remaining_shares(self):
        got = self.build([order(side="sell", shares=8, filled_shares=3, status="partial")])
        self.assertEqual(got["actual"]["shares_reserved_for_sale"], {"AAA": 5})

    def test_missing_or_unknown_side_rejected(self):
        for side in (None, "short", "BUY"):
            o = order()
            o["side"] = side
            if side is None:
                del o["side"]
            with self.assertRaises(ValueError):
                self.build([o])

    def test_selling_more_than_held_rejected(self):
        with self.assertRaises(ValueError):
            self.build([order(side="sell", shares=6), order(id="o2", side="sell", shares=5)])
        with self.assertRaises(ValueError):
            self.build([order(side="sell", ticker="ZZZ")])

    def test_cli_turns_bad_state_into_reconciliation(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.json")
            with open(p, "w") as f:
                json.dump(dict(cash=9000, holdings=[HOLD], orders=[order(side=None)]), f)
            out = subprocess.run([sys.executable, os.path.join(HERE, "portfolio_state.py"), "--input", p,
                                  "--broker", "bank-al-etihad-jo"], capture_output=True, text=True)
        r = json.loads(out.stdout)
        self.assertTrue(r["reconciliation_required"])
        self.assertIn("side", r["error"])


class StateSectorWeights(unittest.TestCase):
    def test_invalid_weights_rejected(self):
        for w in ({"Tech": -1}, {"Tech": 1.5}, {"Tech": 0.5}, {"Tech": float("nan")}, {"": 1}, ["Tech"],
                  {"Tech": True}, {"Tech": 0.7, "Health": 0.7}):
            with self.assertRaises(ValueError, msg=w):
                ps.build(dict(cash=5000, holdings=[dict(HOLD, sector_weights=w)], orders=[]), fee=FEE)
            with self.assertRaises(ValueError, msg=w):
                ps.build(dict(cash=5000, holdings=[], orders=[order(sector_weights=w, ticker="NEW")]), fee=FEE)

    def test_valid_weights_accepted(self):
        for w in ({"Tech": 1}, {"Tech": 0.5, "Health": 0.3, "Unclassified": 0.2}, {"Tech": 0.995}):
            out = ps.build(dict(cash=5000, holdings=[dict(HOLD, sector_weights=w)], orders=[]), fee=FEE)
            self.assertFalse(out["reconciliation_required"])
            self.assertTrue(all(v >= 0 for v in out["actual"]["sector_exposure"].values()))

    def test_missing_weights_still_warn(self):
        out = ps.build(dict(cash=5000, holdings=[dict(HOLD, sector_weights=None)], orders=[]), fee=FEE)
        self.assertTrue(any("no sector weights" in w for w in out["warnings"]))


def linear_best(k, plan, planned_loss, fee, cap, available, loss_limit, min_order, min_price):
    """The v4.3 linear scan, kept here as the reference."""
    best = None
    for n in range(k, int(cap // min_price) + 1):
        parts, buys = plan(n)
        if min(parts) < 1 or min(buys) < min_order or sum(buys) > cap:
            continue
        if sum(b + fee(b, q) for q, b in zip(parts, buys)) > available:
            continue
        if planned_loss(n) <= loss_limit:
            best = n
    return best


class BoundedSizing(unittest.TestCase):
    def test_matches_linear_scan(self):
        rnd = random.Random(11)
        models = [FEE, fees.make_fee_model(dict(model="zero")), fees.make_fee_model(dict(model="flat", flat=4.95)),
                  fees.make_fee_model(dict(model="per_share", per_share=0.005, min=1, max_pct=0.01)),
                  fees.make_fee_model(dict(model="percent", rate=0.002, min=2, max=8, fx_pct=0.003), convert=True)]
        for _ in range(400):
            fee = rnd.choice(models)
            k = rnd.choice([1, 1, 2, 3])
            top = rnd.uniform(1, 400)
            prices = sorted([round(top * (1 - 0.02 * i), 2) for i in range(k)], reverse=True)
            stop = round(prices[-1] * rnd.uniform(0.85, 0.99), 2)
            fr = rnd.choice([0, 0.0005, 0.001])
            cap, available = rnd.uniform(50, 6000), rnd.uniform(50, 6000)
            loss_limit, min_order = rnd.uniform(1, 200), rnd.choice([0, 0, 100, 250])

            def plan(n, prices=prices, k=k):
                parts = st.split_shares(n, k)
                return parts, [q * p for q, p in zip(parts, prices)]

            def planned_loss(n, plan=plan, fee=fee, fr=fr, stop=stop):
                parts, buys = plan(n)
                cost = sum(b + fee(b, q) + fr * b for q, b in zip(parts, buys))
                out = n * stop
                return cost - (out - fee(out, n, side="sell") - fr * out)
            args = (k, plan, planned_loss, fee, cap, available, loss_limit, min_order, min(prices))
            self.assertEqual(st.best_quantity(*args), linear_best(*args), args[4:])

    def test_sub_dollar_prices_rejected_fast(self):
        t0 = time.time()
        out = subprocess.run([sys.executable, os.path.join(HERE, "size_trade.py"), "--asset", "stock", "--ticker", "ABC",
                              "--profile", "balanced", "--portfolio", "10000", "--cash", "10000", "--entry", "0.5",
                              "--stop", "0.48", "--t1", "0.6", "--t2", "0.7", "--market-price", "0.5",
                              "--sector-weights", '{"Tech":1}', "--quote-status", "live", "--boycott-mode", "off",
                              "--shariah-mode", "off", "--broker", "bank-al-etihad-jo"],
                             capture_output=True, text=True, timeout=10)
        r = json.loads(out.stdout)
        self.assertEqual(r["verdict"], "NO TRADE")
        self.assertIn("sub-penny", " ".join(r["reasons"]))
        self.assertLess(time.time() - t0, 5)

    def test_huge_account_low_price_is_fast(self):
        """$2 ETF, $50M account: about 10 million candidate quantities for the old linear scan."""
        t0 = time.time()
        r = st.compute(st.build_parser().parse_args(
            ["--asset", "etf", "--ticker", "ABC", "--isin", "US0000000001", "--profile", "aggressive",
             "--portfolio", "50000000", "--cash", "50000000", "--entry", "2.00", "--stop", "1.90", "--t1", "2.40",
             "--t2", "2.60", "--market-price", "2.00", "--sector-weights", '{"Tech":1}', "--quote-status", "live",
             "--quote-time", "2026-11-05T15:30:00-05:00", "--quote-source", "Test", "--as-of", "2026-11-05",
             "--boycott-mode", "off", "--shariah-mode", "off", "--broker", "bank-al-etihad-jo"]))
        self.assertLess(time.time() - t0, 2)
        self.assertEqual(r["verdict"], "TRADE", r["reasons"])
        self.assertLessEqual(r["downside"]["executable_stop_downside"], 0.02 * 50000000)


if __name__ == "__main__":
    unittest.main()
