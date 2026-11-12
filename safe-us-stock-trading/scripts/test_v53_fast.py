#!/usr/bin/env python3
"""v5.3 tests: compact market data with a checksum, the session store, the "check more" buttons."""
import copy, datetime as dt, json, os, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ingest, signals, store  # noqa: E402
import render_dashboard as rd  # noqa: E402

# A real browser_fetch.js "full" result (GLDM, read 2026-11-12 with the US market closed).
REAL = {"v": 2, "read_at": "2026-11-12T08:37:30.458Z", "source": "nasdaq", "axes": [{"d0": "2025-10-20", "gaps": "111131111311113111131111311231111311113111131123112311113111141113111131111311114111311113111131111311113111131114111131111311113111131111311113111141113111131111311141111311141111311113111131111311113111131111311113111141113111131111311113111131111311113111131111311"}], "tickers": {"GLDM": {"cls": "etf", "price": "78.825", "time": "Nov 11, 2026", "realtime": False, "ax": 0, "n": 268, "sum": 749020, "c": "6ot 69w 69k 6ad 69n 63d 61r 60x 657 63z 64h 60k 633 62v 646 6a6 6b3 6ep 6cy 68q 667 67t 686 685 67p 6b9 6b7 6cz 6fu 6gy 6fg 6fb 6fh 6f3 6ei 6fl 6gl 6j3 6ke 6kp 6kq 6mo 6ma 6mm 6s3 6v9 6ue 6x7 6mc 6mm 6l5 6m6 6sg 6v4 6sr 6u2 6vv 70i 705 72r 715 6zz 79i 7de 7ic 7lx 7py 7wr 87o 88l 7ep 73j 7jv 7jg 7ch 7ke 7re 7om 7rn 7i5 7op 7g7 7m2 7mx 7s8 7zw 7vx 7v8 7xn 81a 856 7s8 7ua 7qu 7v9 7uo 7xt 7wz 7rg 7ns 7nk 7mw 7e5 736 6vf 6ps 6pv 6x3 6nt 6w6 6w4 75h 79y 74w 73x 76g 783 7a6 79p 78o 7ee 7bn 7bg 7es 7es 756 78l 761 77a 75b 70k 6xx 71t 71d 6wa 6yd 75x 76h 77p 789 778 75q 73t 6xy 6yj 6ue 6xw 6xn 6vt 6vt 6sl 6v5 6xt 6u9 6um 6s9 6ub 6la 6lv 6i2 68d 6f7 6fg 6lj 6m7 6gq 6fs 6ec 69y 635 65a 67x 64p 64m 660 6ai 6cv 6a5 686 6ai 69t 63x 66x 66w 62o 64p 647 68i 6b2 66j 66r 68e 65a 66a 69x 66m 66m 686 6hf 6hf 6mr 6p5 6o6 6ql 6n1 6oi 6qx 6mu 6w1 6wv 71o 73m 74j 70i 719 6t0 6sr 6lr 6pd 6tw 6rp 6nj 6pr 6lj 6mw 6jd 6k4 6it 6mr 6oj 6ms 6nt 6jf 6is 6jt 6ak 6dk 6ca 6dh 6bx 6bi 6d1 69b 6b0 6ej 6d3 6cs 69d 6df 6d2 6bm 6ac 6b7 65a 63t 64i 674 67w 650 5xf 60r 5zd 67a 696 67d 6bj 65j 62x", "hl": "6bo.69g 6ew.6dq 6de.6ck 6e5.6bu 69n.67t 6dg.6bn 6ep.6cd 6cx.6ba 6cb.6a7 6bj.69j 683.64v 65a.62f 65d.636 67c.64w 67y.655 65r.63z 60u.5wn 623.60a 60x.5z7 67l.65c 6b6.67w 682.65d 6bw.699 66x.64j 65h.62s"}, "ZZZZQ": {"error": "not found on Nasdaq"}}}


class CompactData(unittest.TestCase):
    def test_real_payload_decodes_and_signals_run(self):
        rows, problem = ingest.rows_v2(REAL["tickers"]["GLDM"], REAL["axes"])
        self.assertIsNone(problem)
        self.assertEqual(len(rows), 268)
        self.assertEqual(rows[0], ["2025-10-20", "86.69", "", ""])            # old rows: close only
        self.assertEqual(rows[-1], ["2026-11-11", "78.81", "79.73", "78.76"])  # newest rows: high and low too
        with tempfile.TemporaryDirectory() as d:
            out = ingest.ingest(copy.deepcopy(REAL), os.path.join(d, "L.json"), "", d)
            self.assertTrue(out["GLDM"]["ok"], out["GLDM"])
            self.assertEqual(out["GLDM"]["history_through"], "2026-11-11")
            self.assertFalse(out["ZZZZQ"]["ok"])
            sig = signals.one("GLDM", signals.load_prices(os.path.join(d, "GLDM.csv")))
            self.assertIn("atr", json.dumps(sig).lower())
            self.assertNotIn('"atr14": null', json.dumps(sig))

    def test_a_copying_mistake_is_caught_not_repaired(self):
        bad = copy.deepcopy(REAL["tickers"]["GLDM"])
        bad["c"] = bad["c"].replace("6ot", "6ou", 1)                          # one character wrong
        rows, problem = ingest.rows_v2(bad, REAL["axes"])
        self.assertEqual(rows, [])
        self.assertIn("checksum", problem)
        short = copy.deepcopy(REAL["tickers"]["GLDM"])
        short["c"] = " ".join(short["c"].split()[:-1])                        # a dropped row
        self.assertTrue(ingest.rows_v2(short, REAL["axes"])[1])

    def test_old_shape_still_works(self):
        self.assertEqual(ingest.rows_of("2026-11-10,79.75,80.25,79.39;junk"), [["2026-11-10", "79.75", "80.25", "79.39"]])


class Store(unittest.TestCase):
    def test_only_live_screens_come_back(self):
        today = dt.date(2026, 11, 12)
        with tempfile.TemporaryDirectory() as s, tempfile.TemporaryDirectory() as w, tempfile.TemporaryDirectory() as w2:
            def put(name, obj):
                with open(os.path.join(w, name), "w") as f:
                    json.dump(obj, f)
            put("PROFILE.json", {"profile": "aggressive", "broker": "bank-al-etihad-jo"})
            put("BOYCOTT_AAA.json", {"status": "REVIEWED_NO_MATCH", "as_of": "2026-11-01"})
            put("EVIDENCE_AAA.json", {"ticker": "AAA"})
            put("BOYCOTT_OLD.json", {"status": "REVIEWED_NO_MATCH", "as_of": "2026-09-01"})
            put("EVIDENCE_OLD.json", {"ticker": "OLD"})
            put("SCREEN_AAA.json", {"policy_decision": "PERMITTED", "expires_on": "2027-01-10"})
            put("SCREEN_OLD.json", {"policy_decision": "PERMITTED", "expires_on": "2026-10-01"})
            put("PLAN_AAA.json", {"verdict": "TRADE"})                         # plans and prices are never stored
            saved = store.save(s, w)["saved"]
            self.assertNotIn("PLAN_AAA.json", saved)
            got = store.load(s, w2, today)
            self.assertEqual(got["profile"]["profile"], "aggressive")
            self.assertEqual(set(got["reusable"]), {"AAA"})
            self.assertEqual(set(got["expired"]), {"OLD"})
            self.assertEqual(sorted(f for f in os.listdir(w2) if "OLD" in f), [])
            self.assertTrue(os.path.exists(os.path.join(w2, "EVIDENCE_AAA.json")))

    def test_no_store_is_fine(self):
        self.assertFalse(store.load("/nonexistent/store", tempfile.gettempdir())["found"])


class CheckMore(unittest.TestCase):
    PLAN = {"ticker": "ABC", "verdict": "NO TRADE", "profile": "aggressive", "horizon": "medium",
            "broker": "Test app", "reasons": ["net reward:risk of the exit plan 1.4 is below profile minimum 2.0"],
            "boycott": {"mode": "flag", "status": "REVIEWED_NO_MATCH", "screened": True},
            "shariah": {"mode": "flag", "policy_decision": "PERMITTED", "screened": True, "methodology": "SS-21"}}

    def test_page_has_sector_buttons_with_ready_requests(self):
        page = rd.render([copy.deepcopy(self.PLAN)])
        self.assertIn("Check more", page)
        for sector in json.load(open(os.path.join(HERE, "universe.json")))["sectors"]:
            self.assertIn(rd.e(sector), page)
        self.assertIn("quick:", page)
        self.assertIn("risk aggressive", page)
        self.assertIn("boycott flag", page)
        self.assertNotIn("http://", page.split("<script>")[1])               # the script loads nothing
        self.assertNotIn("src=", page)

    def test_requests_are_escaped(self):
        p = copy.deepcopy(self.PLAN); p["horizon"] = 'medium"><img>'
        self.assertNotIn("<img>", rd.render([p]))



class Prescreen(unittest.TestCase):
    """prescreen.py: many stocks checked ahead of time with the same two screens the trade run uses."""
    REC = {"f": ["10-Q", "2026-11-03", "2026-09-30", "000155115226000037/abbv-20260930.htm"], "k": "0001551152",
           "bs": "2026-09-30", "lag": 0, "so": 1767616306, "st": "2026-01-01",
           "i": "147680,,,,,0,,72230,10774,,,,,,,,387,13509", "fl": ",49396,,,,241,,,,,,2265,,", "il": 0}
    SITES = {k: {"ok": True, "url": "https://example.org/" + k} for k in ("afsc", "whoprofits", "bds", "ohchr")}

    def test_tag_order_is_the_same_in_the_browser_script(self):
        import prescreen as ps
        js = open(os.path.join(HERE, "browser_facts.js")).read()
        for name, tags in (("INSTANT", ps.INSTANT), ("FLOW", ps.FLOW)):
            block = js.split(f"const {name} = [", 1)[1].split("];", 1)[0]
            self.assertEqual([t.strip().strip('"') for t in block.replace("\n", " ").split(",") if t.strip()], tags)

    def test_missing_numbers_stay_missing_and_debt_takes_the_larger_reading(self):
        import prescreen as ps
        nums, notes = ps.halal_inputs(self.REC, 294.875)
        self.assertEqual(nums["interest-debt"], 72230e6)
        self.assertEqual(nums["nonpermissible-income"], 241e6)
        rec = dict(self.REC, fl=",49396,,,,,,,,,,2265,,", i="147680,,,,,,,,,,,,,,,,,")
        nums, notes = ps.halal_inputs(rec, 294.875)
        for k in ("interest-debt", "cash", "nonpermissible-income"):
            self.assertNotIn(k, nums)
        self.assertTrue(any("interest income" in n for n in notes))
        both = dict(self.REC, i="100,50,,,,,30,80,5,,,,,,,,,")            # LongTermDebt 50; LTD+leases 80 + current 30
        self.assertEqual(ps.halal_inputs(both, 10)[0]["interest-debt"], 110e6)

    def test_end_to_end_writes_results_the_store_can_reuse(self):
        import prescreen as ps
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        rec = dict(self.REC); rec["f"] = ["10-Q", today, "2026-09-30", rec["f"][3]]
        review = {"sites": copy.deepcopy(self.SITES), "matches": {"afsc": {"NVDA": "https://example.org/nvda"}}}
        review["sites"]["ohchr"]["list_version"] = "A/HRC/63/20"
        review["sites"]["bds"]["ok"] = False                                   # a site whose control check failed
        with tempfile.TemporaryDirectory() as s:
            out = ps.prescreen({"tickers": {"ABBV": rec, "NVDA": dict(rec), "ZZZ": rec, "ERR": {"e": "x"}}},
                               {"rows": ["ABBV|294.875", "NVDA|173.73"]}, review, s, today)
            rows = {r["ticker"]: r for r in out["rows"]}
            self.assertEqual(rows["ABBV"]["boycott"], "UNVERIFIED")           # unreachable list is never "no match"
            review["sites"]["bds"]["ok"] = True
            again = ps.prescreen({"tickers": {"NVDA": dict(rec)}}, {"rows": ["NVDA|173.73"]}, review, os.path.join(s, "b"), today)
            self.assertEqual(again["rows"][0]["boycott"], "EXCLUDED")         # a confirmed match on a reachable list
            self.assertEqual(rows["ABBV"]["halal"], "REQUIRES_ACCEPTANCE")    # scripted SEC mapping: first pass
            self.assertEqual(rows["ZZZ"]["boycott"], "NOT RUN")
            ev = json.load(open(os.path.join(s, "EVIDENCE_ABBV.json")))
            self.assertEqual(ev["sources"]["bds"]["finding"], "unreachable")
            self.assertEqual(ev["sources"]["sec"]["url"], "https://www.sec.gov/Archives/edgar/data/1551152/" + rec["f"][3])
            got = store.load(s, os.path.join(s, "w"))
            self.assertIn("screen", got["reusable"]["ABBV"])
            self.assertIn("Checked ahead of time", rd.render([], prescreen=out))

    def test_universe_isins_have_valid_check_digits(self):
        def ok(i):
            d, t = "".join(str(int(c, 36)) for c in i[:-1]), 0
            for k, c in enumerate(reversed(d)):
                n = int(c) * (2 if k % 2 == 0 else 1); t += n // 10 + n % 10
            return (10 - t % 10) % 10 == int(i[-1])
        stocks = json.load(open(os.path.join(HERE, "universe.json")))["stocks"]
        self.assertTrue(stocks)
        for t, m in stocks.items():
            self.assertTrue(len(m["isin"]) == 12 and ok(m["isin"]), t)
            self.assertIn(m["business"], ("permissible", "mixed", "prohibited"))


class MarketButton(unittest.TestCase):
    def test_follow_the_market_button_knows_the_holidays(self):
        page = rd.render([copy.deepcopy(CheckMore.PLAN)])
        self.assertIn('id="more-market"', page)
        held = rd.render([copy.deepcopy(CheckMore.PLAN)], {"actual": {"holdings": [{"ticker": "nvda"}]}})
        self.assertIn("review what I hold (NVDA)", held)                      # portfolio_state.py output shape
        self.assertIn("follow the market now", page)
        self.assertIn("2026-11-26", page)                                     # Thanksgiving is in the embedded list


class QuickScreens(unittest.TestCase):
    """v5.3 quick depth: one primary boycott list, and a screening provider's halal verdict."""
    def ev(self, **kw):
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        e = {"ticker": "ABC", "isin": "US0378331005", "entity": "ABC Corp", "asset": "stock", "identity_resolved": True,
             "depth": "quick", "sources": {"afsc": {"finding": "no_match", "checked_on": today, "url": "https://investigate.afsc.org/company-search"},
                                           "bds": {"finding": "no_match", "checked_on": today, "url": "https://bdsmovement.net/Guide-to-BDS-Boycott"},
                                           "whoprofits": {"finding": "no_match", "checked_on": today, "url": "https://www.whoprofits.org/index.php/companies?page=1"}}}
        e.update(kw); return e, today

    def test_three_lists_are_enough_only_when_the_evidence_says_quick(self):
        import boycott_screen as bs
        e, today = self.ev()
        status, why = bs.compute_status(e, today)
        self.assertEqual(status, "REVIEWED_NO_MATCH"); self.assertIn("BDS, AFSC, WHOPROFITS", why[0])
        full = dict(e); full.pop("depth")
        self.assertEqual(bs.compute_status(full, today)[0], "UNVERIFIED")       # full depth still needs all five
        e["sources"]["afsc"]["finding"] = "match"
        self.assertEqual(bs.compute_status(e, today)[0], "EXCLUDED")
        e["sources"]["afsc"]["finding"] = "unreachable"
        self.assertEqual(bs.compute_status(e, today)[0], "UNVERIFIED")          # both lists must have answered
        e["sources"]["afsc"]["finding"] = "no_match"; e["sources"]["bds"]["finding"] = "match"
        self.assertEqual(bs.compute_status(e, today)[0], "EXCLUDED")            # a BDS target is excluded
        e["sources"]["bds"]["finding"] = "no_match"; e["sources"]["whoprofits"]["finding"] = "match"
        self.assertEqual(bs.compute_status(e, today)[0], "EXCLUDED")            # so is a Who Profits listing
        del e["sources"]["whoprofits"]
        self.assertEqual(bs.compute_status(e, today)[0], "UNVERIFIED")          # Who Profits is required too
        e2, _ = self.ev(sources={"bds": {"finding": "no_match", "checked_on": today, "url": "https://bdsmovement.net/x"}})
        self.assertEqual(bs.compute_status(e2, today)[0], "UNVERIFIED")         # BDS alone is not enough: AFSC is required

    def run_provider(self, *extra):
        import shariah_screen as sh
        today = dt.datetime.now(dt.timezone.utc).date()
        args = ["--asset", "stock", "--ticker", "ABC", "--isin", "US0378331005", "--entity", "ABC Corp", "--methodology", "aaoifi",
                "--as-of", today.isoformat(), "--provider", "musaffa", "--provider-verdict", "halal",
                "--provider-date", (today - dt.timedelta(days=20)).isoformat(), "--provider-methodology", "AAOIFI",
                "--provider-url", "https://musaffa.com/stock/ABC/"]
        for k, v in zip(extra[::2], extra[1::2]):
            args[args.index(k) + 1] = v
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "S.json")
            sh.main(args + ["--out", path]) if hasattr(sh, "main") else None
            return sh, json.load(open(path)), today

    def test_provider_verdict_is_copied_checked_and_expires(self):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            sh, res, today = self.run_provider()
            _, bad_site, _ = self.run_provider("--provider-url", "https://example.com/stock/ABC/")
            _, old, _ = self.run_provider("--provider-date", (today - dt.timedelta(days=200)).isoformat())
            _, other, _ = self.run_provider("--provider-methodology", "S&P")
            _, no, _ = self.run_provider("--provider-verdict", "not_halal")
            _, maybe, _ = self.run_provider("--provider-verdict", "doubtful")
        self.assertEqual(res["policy_decision"], "PERMITTED"); self.assertIn("did not read the provider's site", res["note"])
        for r in (bad_site, old, other):
            self.assertEqual(r["policy_decision"], "UNVERIFIED")
        self.assertEqual(no["policy_decision"], "EXCLUDED"); self.assertEqual(maybe["policy_decision"], "REQUIRES_ACCEPTANCE")
        ok = sh.validate_result(res, "ABC", today.isoformat(), expected_asset="stock", isin="US0378331005")
        self.assertEqual(ok, ("PERMITTED", []))
        edited = dict(no, policy_decision="PERMITTED", screening_result="PASS")
        self.assertEqual(sh.validate_result(edited, "ABC", today.isoformat(), expected_asset="stock", isin="US0378331005")[0], "UNVERIFIED")
        later = (today + dt.timedelta(days=80)).isoformat()                    # result still inside 92 days...
        late = dict(res, inputs=dict(res["inputs"], provider_date=(today - dt.timedelta(days=60)).isoformat()))
        self.assertEqual(sh.validate_result(late, "ABC", later, expected_asset="stock", isin="US0378331005")[0], "UNVERIFIED")

    def test_a_scripted_pass_is_never_clean_and_no_script_reads_the_provider(self):
        import prescreen as ps
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        rec = dict(Prescreen.REC); rec["f"] = ["10-Q", today, "2026-09-30", rec["f"][3]]
        review = {"sites": copy.deepcopy(Prescreen.SITES), "matches": {}}
        review["sites"]["ohchr"]["list_version"] = "A/HRC/63/20"
        with tempfile.TemporaryDirectory() as s:
            out = ps.prescreen({"tickers": {"ABBV": rec}}, {"rows": ["ABBV|294.875"]}, review, s, today, depth="full")
            self.assertEqual(out["rows"][0]["halal"], "REQUIRES_ACCEPTANCE")    # SEC tags mapped by a script: first pass
            self.assertIn("first pass", json.load(open(os.path.join(s, "SCREEN_ABBV.json")))["internal_policy_flags"][0])
        self.assertFalse(os.path.exists(os.path.join(HERE, "browser_halal.js")))  # provider terms forbid automated reading
        for name in os.listdir(HERE):
            if name.endswith(".js"):
                self.assertNotIn("musaffa", open(os.path.join(HERE, name)).read().lower(), name)

    def test_provider_verdict_also_covers_funds_and_metal_trusts(self):
        import contextlib, io, shariah_screen as sh
        today = dt.datetime.now(dt.timezone.utc).date()
        base = ["--methodology", "aaoifi", "--as-of", today.isoformat(), "--provider", "musaffa", "--provider-verdict", "halal",
                "--provider-date", today.replace(day=1).isoformat(), "--provider-methodology", "AAOIFI"]
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            sh.main(["--asset", "etf-certified", "--ticker", "SPUS", "--isin", "US8863648015", "--entity", "SP Funds S&P 500 Sharia ETF",
                     "--provider-url", "https://musaffa.com/etf/SPUS/", "--out", os.path.join(d, "e.json")] + base)
            sh.main(["--asset", "metal", "--ticker", "GLDM", "--entity", "SPDR Gold MiniShares Trust",
                     "--provider-url", "https://musaffa.com/etf/GLDM/", "--out", os.path.join(d, "m.json")] + base)
            e, m = json.load(open(os.path.join(d, "e.json"))), json.load(open(os.path.join(d, "m.json")))
        self.assertEqual(sh.validate_result(e, "SPUS", today.isoformat(), expected_asset="etf-certified", isin="US8863648015"), ("PERMITTED", []))
        self.assertEqual(sh.validate_result(m, "GLDM", today.isoformat(), expected_asset="metal"), ("PERMITTED", []))

    def test_prescreen_quick_needs_no_sec_numbers(self):
        import prescreen as ps
        today = dt.datetime.now(dt.timezone.utc).date()
        month = today.strftime("%B %Y")
        review = {"sites": {"afsc": {"ok": True, "url": "https://investigate.afsc.org/company-search"},
                            "bds": {"ok": True, "url": "https://bdsmovement.net/Guide-to-BDS-Boycott"},
                            "whoprofits": {"ok": True, "url": "https://www.whoprofits.org/index.php/companies?page=1"}}, "matches": {}}
        only_afsc = {"sites": {"afsc": review["sites"]["afsc"]}, "matches": {}}
        with tempfile.TemporaryDirectory() as s0:
            o = ps.prescreen({}, {}, only_afsc, s0, today.isoformat(), depth="quick", halal={"rows": [f"AAPL|200|HALAL|AAOIFI|{month}"]})
            self.assertEqual(o["rows"][0]["boycott"], "UNVERIFIED")            # BDS not checked: not a clean result
        with tempfile.TemporaryDirectory() as s:
            out = ps.prescreen({}, {}, review, s, today.isoformat(), depth="quick",
                               halal={"rows": [f"AAPL|200|HALAL|AAOIFI|{month}", f"MRK|200|NOT HALAL|AAOIFI|{month}", "TSLA|200|?|?|?"]})
            rows = {r["ticker"]: r for r in out["rows"]}
            self.assertEqual((rows["AAPL"]["boycott"], rows["AAPL"]["halal"]), ("REVIEWED_NO_MATCH", "PERMITTED"))
            self.assertEqual(rows["MRK"]["halal"], "EXCLUDED")
            self.assertNotIn("TSLA", rows)                                     # an unreadable row is never a verdict


class SavedLists(unittest.TestCase):
    """lists.py: a halal list (a certified fund's holdings) and a boycott list, read with no web call."""
    HOLD = "AAPL|037833100|Apple Inc;MSFT|594918104|Microsoft Corp;LIN|G54950103|Linde PLC;BAD ROW"
    SITES = {"afsc": {"ok": True, "url": "https://investigate.afsc.org/occupations"},
             "bds": {"ok": True, "url": "https://bdsmovement.net/Guide-to-BDS-Boycott"},
             "whoprofits": {"ok": True, "url": "https://www.whoprofits.org/index.php/companies?page=1"}}

    def test_isin_and_search_words(self):
        import lists
        self.assertEqual(lists.isin_from_cusip("037833100"), "US0378331005")
        self.assertEqual(lists.isin_from_cusip("G54950103"), "")                # foreign share: never guessed
        self.assertEqual(lists.keys_for("PG", "Procter & Gamble Co"), ["procter & gamble", "procter"])

    def test_lists_make_results_the_engine_accepts(self):
        import lists, shariah_screen as sh, boycott_screen as bs
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        with tempfile.TemporaryDirectory() as s:
            self.assertEqual(lists.halal_add(s, self.HOLD, today, "https://www.sp-funds.com/x.csv")["saved"], 3)
            lists.boycott_add(s, today, self.SITES, {"afsc": ["MSFT"], "bds": ["msft"]})
            rows = {r["ticker"]: r for r in lists.apply(s, ["AAPL", "MSFT", "LIN", "KO"], today)["rows"]}
            self.assertEqual((rows["AAPL"]["boycott"], rows["AAPL"]["halal"]), ("REVIEWED_NO_MATCH", "REQUIRES_ACCEPTANCE"))
            self.assertIn("CONFIRM ON MUSAFFA", lists.lookup(s, ["AAPL"])["AAPL"]["halal"])   # fund list = shortlist only
            lists.set_halal(s, "AAPL", "halal", today)                          # the user looked it up on Musaffa
            lists.set_halal(s, "MSFT", "halal", (dt.date.fromisoformat(today) - dt.timedelta(days=200)).isoformat())
            rows = {r["ticker"]: r for r in lists.apply(s, ["AAPL", "MSFT", "LIN", "KO"], today)["rows"]}
            self.assertEqual(rows["AAPL"]["halal"], "PERMITTED")
            self.assertEqual(rows["MSFT"]["halal"], "REQUIRES_ACCEPTANCE")      # a lookup older than 120 days no longer counts
            self.assertEqual(rows["MSFT"]["boycott"], "EXCLUDED")
            self.assertEqual(rows["LIN"]["boycott"], "UNVERIFIED")              # no ISIN on file: identity not resolved
            self.assertEqual(rows["KO"]["halal"], "NOT RUN")                    # not on the list is not "not halal"
            res = json.load(open(os.path.join(s, "SCREEN_AAPL.json")))
            self.assertEqual(sh.validate_result(res, "AAPL", today, expected_asset="stock", isin="US0378331005"), ("PERMITTED", []))
            self.assertIn("as the user looked it up", res["note"])
            json.dump({"halal_authority": "fund"}, open(os.path.join(s, "lists", "OVERRIDES.json"), "w"))
            self.assertEqual(lists.apply(s, ["AAPL"], today)["rows"][0]["halal"], "PERMITTED")   # opt-in: the fund list counts alone
            self.assertIn("Other screeners can disagree", json.load(open(os.path.join(s, "SCREEN_AAPL.json")))["note"])
            b = json.load(open(os.path.join(s, "BOYCOTT_AAPL.json")))
            self.assertEqual(bs.validate_result(b, "AAPL", "stock", "US0378331005", today)[0], "REVIEWED_NO_MATCH")
            self.assertEqual(lists.lookup(s, ["MSFT"])["MSFT"]["boycott"], "LISTED BY AFSC, BDS")

    def test_a_list_site_that_did_not_answer_never_gives_a_clean_result(self):
        import lists
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        sites = copy.deepcopy(self.SITES); sites["whoprofits"]["ok"] = False
        with tempfile.TemporaryDirectory() as s:
            lists.halal_add(s, self.HOLD, today, "https://www.sp-funds.com/x.csv")
            lists.boycott_add(s, today, sites, {})
            self.assertEqual(lists.apply(s, ["AAPL"], today)["rows"][0]["boycott"], "UNVERIFIED")
            self.assertEqual(lists.lookup(s, ["AAPL"])["AAPL"]["boycott"], "LIST TOO OLD OR INCOMPLETE")

    def test_a_fund_list_can_only_say_halal(self):
        import contextlib, io, shariah_screen as sh
        today = dt.datetime.now(dt.timezone.utc).date().isoformat()
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            sh.main(["--asset", "stock", "--ticker", "ABC", "--isin", "US0378331005", "--entity", "ABC", "--methodology", "aaoifi",
                     "--as-of", today, "--provider", "spus", "--provider-verdict", "not_halal", "--provider-date", today,
                     "--provider-methodology", "AAOIFI", "--provider-url", "https://www.sp-funds.com/x.csv", "--out", os.path.join(d, "s.json")])
            self.assertEqual(json.load(open(os.path.join(d, "s.json")))["policy_decision"], "UNVERIFIED")


class UpdateCommand(unittest.TestCase):
    """update_lists.py: one command rebuilds both lists; a source that fails never produces a clean result."""
    def pages(self, d, who_ok=True, afsc_ctrl=True):
        names = ["Apple Inc", "Microsoft Corp", "Target Corp", "Cisco Systems Inc"] + [f"Filler{i:03d} Holdings Inc" for i in range(120)]
        with open(os.path.join(d, "spus.csv"), "w") as f:
            f.write("Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits\n")
            for i, n in enumerate(names):
                t = {0: "AAPL", 1: "MSFT", 2: "TGT", 3: "CSCO"}.get(i, "F" + "".join(chr(65 + int(c)) for c in f"{i:03d}"))
                c = {0: "037833100", 1: "594918104", 2: "87612E106", 3: "17275R102"}.get(i, f"{100000000 + i}")
                f.write(f"11/12/2026,SPUS,{t},{c},{n},1,1,1000.0,0.1%,1,1,1\n")
            f.write("11/12/2026,SPUS,Cash&Other,Cash&Other,Cash & Other,1,1,5.0,0%,1,1,1\n")
        link = lambda n: f'<a href="/company/{n.lower().replace(" ", "-")}">{n}</a>'
        afsc = ["Microsoft Corp"] + (["Caterpillar Inc"] if afsc_ctrl else []) + [f"Other Co {i}" for i in range(160)]
        open(os.path.join(d, "afsc.html"), "w").write("<main>" + "".join(link(n) for n in afsc) + '<a href="/about">About Target practice</a></main>')
        open(os.path.join(d, "bds.html"), "w").write("<html><script>var x='Apple';</script><body>Boycott Chevron, Microsoft and Carrefour</body></html>")
        if who_ok:
            for p in (1, 2):
                ns = (["Caterpillar", "Cisco Systems", "Target Hardware Ltd"] if p == 1 else []) + [f"Firm {p}-{i}" for i in range(160)]
                open(os.path.join(d, f"whoprofits_{p}.html"), "w").write("".join(f'<a href="/companies/company/{i}">{n}</a>' for i, n in enumerate(ns)))

    def test_one_run_builds_lists_and_results(self):
        import update_lists as ul, lists
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as s:
            self.pages(d)
            rep = ul.update(s, d, 0, log=lambda *_: None, today="2026-11-12")
            self.assertEqual(rep["problems"], {})
            self.assertEqual(rep["halal"]["saved"], 124)                         # the cash line is dropped
            self.assertEqual(rep["boycott"]["listed"], ["CSCO", "MSFT", "TGT"])  # every name match counts until reviewed
            self.assertIn("whoprofits: Target Hardware Ltd", rep["review"]["TGT"][0])
            look = lists.lookup(s, ["AAPL", "MSFT"], dt.date(2026, 11, 12))
            self.assertEqual(look["AAPL"]["boycott"], "NOT ON LISTS")            # 'Apple' inside a script tag is not a hit
            self.assertEqual(look["MSFT"]["boycott"], "LISTED BY AFSC, BDS")
            json.dump({"not_a_match": {"whoprofits": ["TGT"]}}, open(os.path.join(s, "lists", "OVERRIDES.json"), "w"))
            lists.set_halal(s, "MSFT", "not_halal", "2026-11-10")
            rep = ul.update(s, d, 0, log=lambda *_: None, today="2026-11-12")
            self.assertEqual(rep["boycott"]["listed"], ["CSCO", "MSFT"])         # the reviewed wrong match is gone
            self.assertEqual(json.load(open(os.path.join(s, "SCREEN_MSFT.json")))["policy_decision"], "EXCLUDED")
            self.assertIn("YOU REPORTED NOT HALAL", lists.lookup(s, ["MSFT"], dt.date(2026, 11, 12))["MSFT"]["halal"])

    def test_a_source_that_fails_or_looks_wrong_is_never_clean(self):
        import update_lists as ul, lists
        for kw in ({"who_ok": False}, {"afsc_ctrl": False}):
            with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as s:
                self.pages(d, **kw)
                rep = ul.update(s, d, 0, log=lambda *_: None, today="2026-11-12")
                self.assertTrue(rep["problems"])
                self.assertEqual(lists.lookup(s, ["AAPL"], dt.date(2026, 11, 12))["AAPL"]["boycott"], "LIST TOO OLD OR INCOMPLETE")
                self.assertEqual(json.load(open(os.path.join(s, "BOYCOTT_AAPL.json")))["status"], "UNVERIFIED")

    def test_name_matching_finds_what_the_live_sites_showed(self):
        import lists
        rows = {"MSFT": {"name": "Microsoft Corp"}, "GOOGL": {"name": "Alphabet Inc"}, "IBM": {"name": "International Business Machines Corp"},
                "CSCO": {"name": "Cisco Systems Inc"}, "BKNG": {"name": "Booking Holdings Inc"}, "XOM": {"name": "ExxonMobil Holdings Corp"},
                "FSLR": {"name": "First Solar Inc"}, "AAPL": {"name": "Apple Inc"}, "ON": {"name": "ON Semiconductor Corp"}, "IT": {"name": "Gartner Inc"}}
        live = ["Microsoft", "Google LLC (Alphabet Inc.)", "IBM", "Cisco Systems", "Booking.com", "Exxon Mobil Corp",
                "First Solar פירסט סולר", "Applebee's", "Electra Consumer Products", "First International Bank of Israel"]
        self.assertEqual(sorted(lists.match_names(rows, live)), ["BKNG", "CSCO", "FSLR", "GOOGL", "IBM", "MSFT", "XOM"])


if __name__ == "__main__":
    unittest.main()
