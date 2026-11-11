#!/usr/bin/env python3
"""v5.0: ingest.py turns one browser result into CSVs, ledger entries and signals; text output marks."""
import datetime as dt, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ingest
import render_simple as rs
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
        self.assertIsNone(ingest.quote_time("soon"))

    def test_rows_drop_garbage(self):
        self.assertEqual(len(ingest.rows_of("2026-01-02,1,2,0.5;bad;2026-13-40,1,1,1;2026-01-05,x,1,1")), 1)

    def test_end_to_end(self):
        tmp = tempfile.mkdtemp()
        now = dt.datetime.now(ingest.NY).strftime("%b %d, %Y %I:%M %p ET")
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


class Marks(unittest.TestCase):
    def test_text_marks(self):
        out = rs.render([t49.FLAGGED, t49.TRADE])
        self.assertIn("\U0001F7E2 GLDM:", out)
        self.assertIn("\U0001F534 XYZ:", out)
        self.assertIn("\U0001F7E2 A. BUY 19 GLDM", out)
        self.assertIn("\U0001F7E1 B. BUY 10 XYZ", out)


if __name__ == "__main__":
    unittest.main()
