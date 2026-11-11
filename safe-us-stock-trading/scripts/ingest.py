#!/usr/bin/env python3
"""One command to take in market data (v5.0): quotes + a year of daily prices for every ticker.

Input is the JSON string returned by browser_fetch.js (run once in the browser on nasdaq.com).
For every ticker this writes TICKER.csv (date,close,high,low), records the Nasdaq quote and the price
history in the source ledger (ledger.py checks each entry on the spot), and runs signals.py.
Nothing is estimated: a ticker with an error, no rows or a bad quote time is reported and skipped.

  python3 ingest.py --data DATA.json --ledger LEDGER.json --market HLAL [--outdir .]

Prints one JSON summary: per ticker the price, quote time (ISO, New York), rows, last day, ledger
status and the signals hint. Still do by hand: the second quote source (0.5% cross-check).
"""
import argparse, datetime as dt, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import market_clock as mc  # noqa: E402  (same New York clock as the engine; no tz database needed)
URL_Q = "https://www.nasdaq.com/market-activity/{kind}/{t}"
URL_H = "https://api.nasdaq.com/api/quote/{T}/historical?assetclass={cls}"


def _ny(naive):
    """A New York wall-clock time -> aware datetime with the right offset (EST -5 or EDT -4)."""
    for off in (-5, -4):
        aware = naive.replace(tzinfo=dt.timezone(dt.timedelta(hours=off)))
        if mc.ny_offset_hours(aware.astimezone(dt.timezone.utc)) == off:
            return aware
    return naive.replace(tzinfo=dt.timezone(dt.timedelta(hours=-5)))


def now_ny():
    return mc.to_new_york(dt.datetime.now(dt.timezone.utc))


def quote_time(text):
    """'Nov 9, 2026 10:45 AM ET' -> ISO 8601 with the New York offset. None if it can't be read.
    A date with no clock time (market closed) is read as midnight, so the engine treats it as old."""
    s = (text or "").replace(" ET", "").strip()
    for fmt in ("%b %d, %Y %I:%M %p", "%b %d, %Y"):
        try:
            return _ny(dt.datetime.strptime(s, fmt)).isoformat()
        except ValueError:
            pass
    return None


def run(args):
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return dict(error=(r.stderr or r.stdout).strip()[-300:])


def rows_of(h):
    out = []
    for part in (h or "").split(";"):
        f = part.split(",")
        if len(f) == 4:
            try:
                dt.date.fromisoformat(f[0]); [float(x) for x in f[1:]]
                out.append(f)
            except ValueError:
                pass
    return out


def ingest(data, ledger, market="", outdir="."):
    summary, tick = {}, data.get("tickers") or {}
    market = market if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,9}", market or "") else ""
    order = sorted(tick, key=lambda t: str(t).upper() != market.upper())    # market fund first: signals need it
    for t in order:
        d, T = tick[t], str(t).upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", T):       # the name becomes a file name: letters only
            summary[T[:20]] = dict(ok=False, problem="not a ticker symbol"); continue
        if not isinstance(d, dict):
            summary[T] = dict(ok=False, problem="no data"); continue
        if d.get("error"):
            summary[T] = dict(ok=False, problem=d["error"]); continue
        rows, when = rows_of(d.get("h")), quote_time(d.get("time"))
        try:
            price = float(d.get("price"))
        except (TypeError, ValueError):
            price = None
        if not rows or price is None or price <= 0 or not when:
            summary[T] = dict(ok=False, problem="no rows, bad price or unreadable quote time"); continue
        csv_path = os.path.join(outdir, f"{T}.csv")
        with open(csv_path, "w") as f:
            f.write("date,close,high,low\n" + "\n".join(",".join(r) for r in rows) + "\n")
        kind = "etf" if d.get("cls") == "etf" else "stocks"
        led = os.path.join(HERE, "ledger.py")
        q = run([led, "add", "--ledger", ledger, "--category", "quote", "--ticker", T,
                 "--url", URL_Q.format(kind=kind, t=t.lower()), "--value", str(price), "--observed-at", when])
        h = run([led, "add", "--ledger", ledger, "--category", "price_history", "--ticker", T,
                 "--url", URL_H.format(T=T, cls=kind), "--history-through", rows[-1][0], "--observed-at", "now"])
        sig_path = os.path.join(outdir, f"SIG_{T}.json")
        cmd = [os.path.join(HERE, "signals.py"), "one", "--ticker", T, "--prices", csv_path, "--out", sig_path]
        mkt = os.path.join(outdir, f"{(market or '').upper()}.csv")
        if market and os.path.exists(mkt):
            cmd += ["--market", mkt]
        sg = run(cmd)
        summary[T] = dict(ok=True, price=price, quote_time=when, realtime=bool(d.get("realtime")), rows=len(rows),
                          history_through=rows[-1][0], csv=csv_path, signals=sig_path,
                          quote_ledger=q.get("status") or q.get("error"),
                          history_ledger=h.get("status") or h.get("error"),
                          hint=sg.get("hint") or sg.get("error"), flags=sg.get("flags"))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", required=True, help="JSON from browser_fetch.js")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--market", default="", help="ticker of the broad-market fund in the same data")
    ap.add_argument("--outdir", default=".")
    a = ap.parse_args(argv)
    with open(a.data) as f:
        data = json.load(f)
    if isinstance(data, str):                       # the browser tool may return the JSON as a quoted string
        data = json.loads(data)
    print(json.dumps(ingest(data, a.ledger, a.market, a.outdir), indent=1))


if __name__ == "__main__":
    main()
