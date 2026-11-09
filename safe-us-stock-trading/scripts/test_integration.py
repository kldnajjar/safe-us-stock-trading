#!/usr/bin/env python3
"""Integration and v4.2 regression tests: the real command-line chain across every asset type,
consecutive trades against the projected state, tranches, existing holdings, pending orders,
partial fills, cancellations, order confirmation, and both screens bound to the instrument."""
import json, os, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import size_trade as _st_v46  # noqa: E402
# v4.6: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v46_mandatory.py tests them switched on.
_st_v46.SCREENS_REQUIRED = _st_v46.SOURCES_REQUIRED = _st_v46.MARKET_CLOCK_REQUIRED = False
import boycott_screen as bs  # noqa: E402
import fees  # noqa: E402
import portfolio_state as ps  # noqa: E402
import shariah_screen as sh  # noqa: E402

AS_OF = "2026-11-05"
QT = "2026-11-05T15:30:00-05:00"
FEE = fees.broker_profile("bank-al-etihad-jo")[1]


# size_trade.py checks quotes against the system clock. These fixtures are fixed-date, so the real
# command-line entry point (main) runs in a subprocess with the clock pinned 5 minutes after QT.
PINNED = ("import sys, datetime as d; sys.path.insert(0, %r); import size_trade as s; s.SCREENS_REQUIRED = s.SOURCES_REQUIRED = s.MARKET_CLOCK_REQUIRED = False; "
          "s.CLOCK = lambda: d.datetime(2026, 11, 5, 20, 35, tzinfo=d.timezone.utc); "
          "sys.argv[0] = 'size_trade.py'; s.main(sys.argv[1:])" % HERE)


def cli(script, *args):
    cmd = [sys.executable, "-c", PINNED] if script == "size_trade.py" else [sys.executable, os.path.join(HERE, script)]
    out = subprocess.run([*cmd, *map(str, args)], capture_output=True, text=True)
    if out.returncode != 0:
        raise AssertionError(f"{script} exited {out.returncode}: {out.stderr}")
    return json.loads(out.stdout)


def jfile(obj, d):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir=d)
    json.dump(obj, f)
    f.close()
    return f.name


def evidence(ticker, isin, asset, **over):
    src = lambda f="no_match": dict(finding=f, checked_on="2026-11-04", url="https://example.org/s")
    ev = dict(ticker=ticker, isin=isin, entity=f"{ticker} Corp", asset=asset, identity_resolved=True,
              sources=dict(ohchr=dict(src(), list_version="A/HRC/63/20"), bds=src(), afsc=src(), whoprofits=src(),
                           sec=dict(src(), israel_hq=False, material_israel_ops=False)))
    if asset == "etf":
        ev["etf"] = dict(screened_weight_pct=100, excluded_weight_pct=0, flagged_weight_pct=0)
    ev.update(over)
    return ev


def size(d, state, ticker, isin, asset, extra, boycott=True, shariah_file=None, shariah_mode="off"):
    args = ["--asset", asset, "--ticker", ticker, "--isin", isin, "--as-of", AS_OF, "--profile", "balanced",
            "--state", state, "--broker", "bank-al-etihad-jo", "--quote-status", "live",
            "--quote-time", QT, "--quote-source", "Test feed", "--shariah-mode", shariah_mode]
    if boycott:
        bfile = jfile(bs.screen(evidence(ticker, isin, asset), AS_OF), d)
        args += ["--boycott-mode", "exclude", "--boycott-result", bfile]
    else:
        args += ["--boycott-mode", "off"]
    if shariah_file:
        args += ["--shariah-result", shariah_file]
    extra = list(extra)
    if "--market-price" not in extra:   # v4.3: market price from the same quote; default = the (first) entry
        if "--entry" in extra:
            args += ["--market-price", extra[extra.index("--entry") + 1]]
        elif "--tranches" in extra:
            args += ["--market-price", str(extra[extra.index("--tranches") + 1]).split(",")[0]]
        elif "--price" in extra:      # T-bill ETF limit price
            args += ["--market-price", extra[extra.index("--price") + 1]]
    return cli("size_trade.py", *args, *extra)


class FullChain(unittest.TestCase):
    def test_consecutive_trades_all_asset_types(self):
        with tempfile.TemporaryDirectory() as d:
            state_in = jfile(dict(cash=20000, holdings=[], orders=[]), d)
            actual = jfile(cli("portfolio_state.py", "--input", state_in, "--broker", "bank-al-etihad-jo"), d)

            stock = size(d, actual, "ABC", "US0000000001", "stock",
                         ["--entry", 100, "--stop", 94, "--t1", 112, "--t2", 119, "--sector-weights", '{"Tech": 1}'])
            self.assertEqual(stock["verdict"], "TRADE", stock["reasons"])
            p1 = jfile(stock, d)
            proj1 = cli("portfolio_state.py", "--input", state_in, "--broker", "bank-al-etihad-jo", "--plans", p1)
            self.assertEqual(proj1["actual"]["stock_etf_positions"], 0)          # actual untouched
            self.assertEqual(proj1["projected"]["stock_etf_positions"], 1)
            self.assertAlmostEqual(proj1["size_trade_args"]["committed"], stock["reservation"]["total"], places=2)

            etf = size(d, jfile(proj1, d), "XYZ", "US0000000002", "etf",
                       ["--tranches", "50,48.5,47", "--stop", 46, "--t1", 56, "--t2", 62, "--horizon", "long",
                        "--sector-weights", '{"Tech": 0.5, "Health": 0.3, "Unclassified": 0.2}'])
            self.assertEqual(etf["verdict"], "TRADE", etf["reasons"])
            self.assertEqual(len(etf["tranches"]), 3)
            for t in etf["tranches"]:
                self.assertGreaterEqual(t["order_value"], 100)

            metal = size(d, jfile(proj1, d), "GLDX", "US0000000003", "metal",
                         ["--entry", 300, "--stop", 285, "--t1", 336, "--t2", 345], boycott=False)
            self.assertEqual(metal["verdict"], "TRADE", metal["reasons"])

            tb = size(d, jfile(proj1, d), "TBIL", "US0000000004", "tbill",
                      ["--amount", 2000, "--price", 50, "--yield-pct", 4, "--duration-yrs", 0.15,
                       "--hold-months", 6], boycott=False)
            self.assertEqual(tb["verdict"], "TRADE", tb["reasons"])

            proj_all = cli("portfolio_state.py", "--input", state_in, "--broker", "bank-al-etihad-jo", "--plans",
                           p1, jfile(etf, d), jfile(metal, d), jfile(tb, d))
            a = proj_all["size_trade_args"]
            total = sum(x["reservation"]["total"] for x in (stock, etf, metal, tb))
            self.assertAlmostEqual(a["committed"], total, places=2)
            self.assertGreater(a["tbill_exposure"], 0)
            self.assertGreater(a["metals_exposure"], 0)
            self.assertEqual(a["open_positions"], 2)
            self.assertIn("Unclassified", a["portfolio_sectors"])

    def test_second_trade_in_same_ticker_respects_combined_cap(self):
        with tempfile.TemporaryDirectory() as d:
            state_in = jfile(dict(cash=10000, holdings=[], orders=[]), d)
            actual = jfile(cli("portfolio_state.py", "--input", state_in, "--broker", "bank-al-etihad-jo"), d)
            first = size(d, actual, "ABC", "US0000000001", "stock",
                         ["--entry", 100, "--stop", 94, "--t1", 112, "--t2", 119, "--sector-weights", '{"Tech": 1}'])
            proj = jfile(cli("portfolio_state.py", "--input", state_in, "--broker", "bank-al-etihad-jo",
                             "--plans", jfile(first, d)), d)
            second = size(d, proj, "ABC", "US0000000001", "stock",
                          ["--entry", 100, "--stop", 94, "--t1", 112, "--t2", 119, "--sector-weights", '{"Tech": 1}'])
            self.assertEqual(second["verdict"], "NO TRADE")
            self.assertIn("position cap reached for ABC", " ".join(second["reasons"]))

    def test_partial_fill_then_cancel_lifecycle(self):
        with tempfile.TemporaryDirectory() as d:
            # tranche 1 filled (in holdings), tranche 2 partially filled, tranche 3 open
            state = dict(cash=8650, holdings=[dict(ticker="XYZ", asset="etf", shares=9, avg_cost=49.8, price=49,
                                                   level=46, level_type="review", sector_weights={"Tech": 1})],
                         orders=[dict(id="XYZ-2", ticker="XYZ", asset="etf", side="buy", limit=48.5, shares=6, filled_shares=2,
                                      status="partial", level=46, level_type="review", sector_weights={"Tech": 1}),
                                 dict(id="XYZ-3", ticker="XYZ", asset="etf", side="buy", limit=47, shares=6, status="open",
                                      level=46, level_type="review", sector_weights={"Tech": 1})])
            out = cli("portfolio_state.py", "--input", jfile(state, d), "--broker", "bank-al-etihad-jo")
            commits = {o["id"]: o["commitment"] for o in out["actual"]["orders"]}
            self.assertAlmostEqual(commits["XYZ-2"], 4 * 48.5 + FEE(4 * 48.5, 4), places=2)
            self.assertAlmostEqual(out["size_trade_args"]["ticker_exposure"]["XYZ"], 9 * 49 + 4 * 48.5 + 6 * 47, places=2)
            state["orders"][1]["status"] = "cancelled"
            out2 = cli("portfolio_state.py", "--input", jfile(state, d), "--broker", "bank-al-etihad-jo")
            self.assertAlmostEqual(out2["size_trade_args"]["committed"], commits["XYZ-2"], places=2)
            self.assertAlmostEqual(out2["size_trade_args"]["ticker_exposure"]["XYZ"], 9 * 49 + 4 * 48.5, places=2)

    def test_order_confirmation_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            actual = jfile(cli("portfolio_state.py", "--input", jfile(dict(cash=10000, holdings=[], orders=[]), d),
                               "--broker", "bank-al-etihad-jo"), d)
            base = ["--entry", 100, "--stop", 94, "--t1", 112, "--t2", 119, "--sector-weights", '{"Tech": 1}',
                    "--stop-orders", "yes"]
            plan = size(d, actual, "ABC", "US0000000001", "stock", base)
            shares = plan["tranches"][0]["shares"]
            ok = size(d, actual, "ABC", "US0000000001", "stock", base + ["--confirm-order", f"ABC|limit|100|{shares}"])
            self.assertTrue(ok["placement_status"].startswith("ready"))
            for bad in (f"ABC|market|100|{shares}", f"ABC|stop|100|{shares}", f"ABC|limit|100.5|{shares}"):
                r = size(d, actual, "ABC", "US0000000001", "stock", base + ["--confirm-order", bad])
                self.assertTrue(r["placement_status"].startswith("provisional"), bad)


class BoycottScreen(unittest.TestCase):
    def test_clean_evidence(self):
        self.assertEqual(bs.screen(evidence("ABC", "US1", "stock"), AS_OF)["status"], "REVIEWED_NO_MATCH")

    def test_listing_excludes(self):
        ev = evidence("ABC", "US1", "stock")
        ev["sources"]["whoprofits"]["finding"] = "match"
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "EXCLUDED")
        self.assertEqual(bs.screen(ev, AS_OF, "moderate")["status"], "FLAGGED")

    def test_israel_hq_excludes(self):
        ev = evidence("ABC", "US1", "stock")
        ev["sources"]["sec"]["israel_hq"] = True
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "EXCLUDED")

    def test_unreachable_or_missing_source_unverified(self):
        ev = evidence("ABC", "US1", "stock")
        ev["sources"]["afsc"]["finding"] = "unreachable"
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "UNVERIFIED")
        del ev["sources"]["afsc"]
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "UNVERIFIED")

    def test_stale_or_future_evidence_unverified(self):
        for d in ("2026-09-01", "2026-12-01"):
            ev = evidence("ABC", "US1", "stock")
            ev["sources"]["bds"]["checked_on"] = d
            self.assertEqual(bs.screen(ev, AS_OF)["status"], "UNVERIFIED", d)

    def test_identity_must_be_resolved(self):
        ev = evidence("ABC", "US1", "stock")
        ev["identity_resolved"] = False
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "UNVERIFIED")

    def test_etf_partial_screening_unverified(self):
        ev = evidence("XYZ", "US2", "etf")
        ev["etf"]["screened_weight_pct"] = 60
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "UNVERIFIED")

    def test_etf_excluded_weight(self):
        ev = evidence("XYZ", "US2", "etf")
        ev["etf"]["excluded_weight_pct"] = 3
        self.assertEqual(bs.screen(ev, AS_OF)["status"], "EXCLUDED")
        self.assertEqual(bs.screen(ev, AS_OF, "moderate")["status"], "FLAGGED")

    def test_validate_binds_to_instrument(self):
        res = bs.screen(evidence("ABC", "US1", "stock"), AS_OF)
        self.assertEqual(bs.validate_result(res, "ABC", "stock", "US1", AS_OF)[0], "REVIEWED_NO_MATCH")
        self.assertEqual(bs.validate_result(res, "XYZ", "stock", "US1", AS_OF)[0], "UNVERIFIED")
        self.assertEqual(bs.validate_result(res, "ABC", "etf", "US1", AS_OF)[0], "UNVERIFIED")
        self.assertEqual(bs.validate_result(res, "ABC", "stock", "US9", AS_OF)[0], "UNVERIFIED")
        self.assertEqual(bs.validate_result(res, "ABC", "stock", "US1", "2026-12-31")[0], "UNVERIFIED")

    def test_edited_status_rejected(self):
        ev = evidence("ABC", "US1", "stock")
        ev["sources"]["ohchr"]["finding"] = "match"
        res = bs.screen(ev, AS_OF)
        res["status"] = "REVIEWED_NO_MATCH"
        self.assertEqual(bs.validate_result(res, "ABC", "stock", "US1", AS_OF)[0], "UNVERIFIED")

    def test_typed_status_flag_removed(self):
        import contextlib, io
        import size_trade as st
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            st.build_parser().parse_args(["--asset", "stock", "--profile", "safe", "--quote-status", "live",
                                          "--boycott-mode", "exclude", "--shariah-mode", "off",
                                          "--boycott-status", "reviewed_no_match"])


class ShariahBinding(unittest.TestCase):
    BASE = dict(asset="stock", ticker="ABC", isin="US0000000001", entity="ABC Corp", business="permissible",
                as_of=AS_OF, period="FY2025", data_published="2026-02-20", market_cap=1000, total_assets=1000,
                interest_debt=100, total_debt=100, cash=40, interest_deposits=10, interest_securities=10,
                receivables=60, nonpermissible_income=1, total_income=500, market_cap_date="2026-11-04")

    def screen(self, **kw):
        d = dict(self.BASE, **kw)
        argv = sum([[f"--{k.replace('_', '-')}", str(v)] for k, v in d.items()], [])
        return sh.screen(sh.build_parser().parse_args(argv))

    def test_isin_mismatch_rejected(self):
        res = self.screen()
        self.assertEqual(sh.validate_result(res, "ABC", AS_OF, expected_asset="stock", isin="US9999999999")[0],
                         "UNVERIFIED")
        self.assertEqual(sh.validate_result(res, "ABC", AS_OF, expected_asset="stock", isin="US0000000001")[0],
                         "PERMITTED")

    def test_stale_filing_rejected(self):
        self.assertEqual(self.screen(data_published="2024-01-15")["policy_decision"], "UNVERIFIED")

    def test_old_market_cap_rejected(self):
        self.assertEqual(self.screen(market_cap_date="2026-08-01")["policy_decision"], "UNVERIFIED")
        self.assertEqual(self.screen(market_cap_date="2026-11-04")["policy_decision"], "PERMITTED")

    def test_infinite_input_rejected(self):
        self.assertEqual(self.screen(total_debt="inf")["policy_decision"], "UNVERIFIED")


class PendingOrders(unittest.TestCase):
    def test_pending_order_without_level_is_unquantified(self):
        out = ps.build(dict(cash=5000, holdings=[], orders=[dict(id="1", ticker="ABC", asset="stock", side="buy", limit=50,
                                                                  shares=4, status="open", sector_weights={"Tech": 1})]),
                       (), FEE)
        self.assertEqual(out["size_trade_args"]["unquantified_holdings"], 1)

    def test_related_share_classes_share_the_cap(self):
        import size_trade as st
        with tempfile.TemporaryDirectory() as d:
            state = ps.build(dict(cash=9200, holdings=[dict(ticker="GOOG", asset="stock", shares=8, avg_cost=100,
                                                            price=100, level=94, level_type="hard",
                                                            sector_weights={"Tech": 1})], orders=[]), (), FEE)
            argv = ["--asset", "stock", "--ticker", "GOOGL", "--related-tickers", "GOOG", "--profile", "balanced",
                    "--state", jfile(state, d), "--broker", "bank-al-etihad-jo", "--quote-status", "live",
                    "--quote-time", QT, "--quote-source", "Test", "--as-of", AS_OF, "--boycott-mode", "off",
                    "--shariah-mode", "off", "--entry", "100", "--stop", "94", "--t1", "112", "--t2", "119",
                    "--sector-weights", '{"Tech": 1}']
            r = st.compute(st.build_parser().parse_args(argv))
            if r["verdict"] == "TRADE":
                self.assertLessEqual(800 + r["total_order_value"], 1000)
            self.assertEqual(r["limits"]["existing_ticker_exposure"], 800.0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
