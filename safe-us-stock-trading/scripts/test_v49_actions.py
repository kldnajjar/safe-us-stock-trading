#!/usr/bin/env python3
"""v4.9: action block, SKIPPED grouping for never-researched plans, and --budget cap."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render_simple as rs
import render_dashboard as rd
import size_trade as st

TRADE = dict(verdict="TRADE", reasons=[], ticker="GLDM", asset="metal", profile="safe", horizon="medium",
             placement_status="provisional: confirm", shares=19,
             tranches=[dict(price=78.0, shares=19)], stop_level=75.1, t1_level=88.6, t2_level=99.0,
             total_order_value=1482.0, total_buy_fees=7.41,
             downside=dict(executable_stop_downside=71.1), gap_scenario=dict(loss=142.06),
             partial_exit_plan=dict(feasible=True, sell_at_t1=9, hold_for_t2=10, combined_net_profit=287.41,
                                    stop_after_t1=dict(keep_at_least=75.1, optional_raise_to=78.87)),
             net_profit_full_exit_t1=100.0,
             boycott=dict(mode="flag", status="REVIEWED_NO_MATCH", screened=True,
                          sources_checked={k: dict(finding="no_match", checked_on="2026-11-09", url=f"https://{k}.example")
                                           for k in ("ohchr", "bds", "afsc", "whoprofits", "sec")}),
             shariah=dict(mode="flag", policy_decision="PERMITTED", screened=True, methodology="SS-21",
                          rules_source="https://aaoifi.com/ss-21", reasons=[]))
FLAGGED = dict(TRADE, ticker="XYZ", tranches=[dict(price=50.0, shares=10)], shares=10,
               boycott=dict(mode="flag", status="EXCLUDED", screened=True, reasons=["listed by: afsc"],
                            sources_checked=dict(afsc=dict(finding="match", checked_on="2026-11-09",
                                                           url="https://investigate.afsc.org/company/xyz"))),
               shariah=dict(mode="flag", policy_decision="EXCLUDED", screened=True, methodology="SS-21",
                            rules_source="https://aaoifi.com/ss-21", reasons=["interest_debt 41% > 30%"]))
UNRUN = dict(verdict="NO TRADE", ticker="HLAL", asset="etf",
             reasons=["boycott screen not run: flag mode still needs a valid result file",
                      "Shariah screen not run: flag mode still needs a valid result file"])
RR = dict(verdict="NO TRADE", ticker="ABC", asset="stock", tranches=[dict(price=10.0, shares=5)],
          reasons=["net reward:risk of the exit plan 2.320 is below profile minimum 2.5"])


class T(unittest.TestCase):
    def test_action_block_for_trade(self):
        out = rs.render([TRADE])
        self.assertIn("WHAT TO DO NOW:", out)
        self.assertIn("LIMIT BUY 19 GLDM AT 78.00", out)
        self.assertIn("STOP ORDER AT 75.10", out)
        self.assertIn("9 AT 88.60, 10 AT 99.00", out)
        self.assertLess(out.index("WHAT TO DO NOW"), out.index("BUY GLDM\n"))

    def test_no_trade_gives_next_step(self):
        out = rs.render([RR], events="CPI TUE")
        self.assertIn("DO NOTHING TODAY", out)
        self.assertIn("CLOSEST IDEA: ABC", out)
        self.assertIn("RE-RUN ME AFTER: CPI TUE", out)

    def test_unscreened_goes_to_skipped_not_red(self):
        out = rs.render([TRADE, UNRUN], skipped=["SPUS|too much NVDA"])
        self.assertNotIn("NO BUY HLAL", out)
        self.assertIn("SKIPPED:", out)
        self.assertIn("HLAL: NOT RESEARCHED", out)
        self.assertIn("SPUS: TOO MUCH NVDA", out)

    def test_real_screen_failure_still_shown(self):
        d = dict(UNRUN, reasons=["boycott screen: excluded"])
        out = rs.render([d])
        self.assertIn("NO BUY HLAL", out)

    def test_dashboard_action_and_skipped(self):
        page = rd.render([TRADE, UNRUN])
        self.assertIn("What to do now", page)
        self.assertIn("Skipped", page)
        self.assertNotIn("screen not run", page)

    def test_budget_rejects_nonpositive(self):
        a = st.build_parser().parse_args(["--asset", "stock", "--profile", "safe", "--quote-status", "live",
                                          "--boycott-mode", "flag", "--shariah-mode", "flag", "--budget", "0"])
        self.assertTrue(any("--budget" in b for b in st.validate_inputs(a)))


class FlagOptions(unittest.TestCase):
    def test_flagged_shown_as_option_with_references(self):
        out = rs.render([FLAGGED, TRADE])
        self.assertIn("YOUR OPTIONS:", out)
        self.assertIn("SCREENS (EVERY IDEA, WITH REFERENCES):", out)
        self.assertIn("XYZ: BOYCOTT ON BOYCOTT LIST | HALAL NOT HALAL", out)
        self.assertIn("https://investigate.afsc.org/company/xyz", out)
        self.assertIn("interest_debt 41% > 30%", out)
        self.assertIn("BUY XYZ", out)                         # flag mode: still planned and shown
        self.assertIn("(FLAG ONLY: YOU DECIDE)", out)

    def test_recommends_clean_option_first(self):
        rows, rec = rs.option_rows([FLAGGED, TRADE])
        self.assertEqual(rec, "A")
        self.assertIn("GLDM", rows[0][1])
        self.assertIn("KEEP CASH", rows[-1][1])

    def test_only_flagged_recommends_cash(self):
        rows, rec = rs.option_rows([FLAGGED])
        self.assertIn("KEEP CASH", dict((r[0], r[1]) for r in rows)[rec])

    def test_dashboard_has_screens_and_options(self):
        page = rd.render([FLAGGED, TRADE])
        self.assertIn("Screens (every idea, with references)", page)
        self.assertIn("Your options", page)
        self.assertIn("recommended", page)


class Brokers(unittest.TestCase):
    def test_robinhood_profile_commission_free_and_verified(self):
        from fees import broker_profile
        prof, fee = broker_profile("robinhood")
        self.assertEqual(prof["source"], "verified")
        self.assertTrue(prof["verified_source"].startswith("https://robinhood.com/"))
        self.assertEqual(fee(1500.0, 19), 0.0)
        self.assertEqual(fee(1500.0, 19, side="sell"), 0.0)

    def test_both_platforms_listed(self):
        from fees import load_brokers
        ids = [k for k, v in load_brokers()["brokers"].items() if not v.get("template")]
        self.assertEqual(ids[:2], ["bank-al-etihad-jo", "robinhood"])


if __name__ == "__main__":
    unittest.main()
