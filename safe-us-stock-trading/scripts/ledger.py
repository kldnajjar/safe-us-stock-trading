#!/usr/bin/env python3
"""Source-ledger helper for the safe-us-stock-trading skill (v4.8).

Adds one source per command, so nobody hand-writes ledger JSON. The source is recognised from the
URL's site (sources.json), "observed_at" defaults to now, and each entry is checked the moment it
is added, so a stale or wrong source is fixed on the spot instead of at sizing time.

  python3 ledger.py add --ledger LEDGER.json --category quote --ticker ABC \\
      --url https://www.nasdaq.com/market-activity/stocks/abc --value 100.00 --observed-at 2026-11-05T15:30:00-05:00
  python3 ledger.py add --ledger LEDGER.json --category fundamentals --ticker ABC --url https://www.sec.gov/... \\
      --published-at 2026-10-31 --form 10-Q --period-end 2026-09-27 --latest-filing-checked-at now
  python3 ledger.py add --ledger LEDGER.json --category earnings_date --ticker ABC --url https://www.nasdaq.com/... \
      --event-date 2027-01-28
  python3 ledger.py add --ledger LEDGER.json --category news --url https://www.reuters.com/... \\
      --published-at 2026-11-05T12:10:00Z --claim-id fed-hold --what "Fed holds rates"
  python3 ledger.py list  --ledger LEDGER.json          # one line per entry with its status
  python3 ledger.py check --ledger LEDGER.json --out SOURCES_CHECK.json   # same as sources_check.py
  python3 ledger.py drop  --ledger LEDGER.json --id ABC-quote-2

An entry with the same category, ticker and URL replaces the older one (re-reading a page updates
it). "now" is accepted for any time field. Quotes: --observed-at is the QUOTE's own time (the time
the site shows), not when you opened the page, and must match --quote-time in size_trade.py.
Exit code 1 if the entry just added (or, for list/check, any entry) is not FRESH.
"""
import argparse, json, os, sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sources_check as sc  # noqa: E402

FIELDS = ("value", "delay_min", "published_at", "event_date", "history_through", "form", "period_end",
          "latest_filing_checked_at", "next_release", "claim_id", "what")
TIME_FIELDS = ("observed_at", "published_at", "latest_filing_checked_at")


def load(path):
    if not os.path.isfile(path):
        return dict(items=[])
    with open(path) as f:
        d = json.load(f)
    if not isinstance(d, dict) or not isinstance(d.get("items"), list):
        raise ValueError(f"{path} is not a ledger (no items list)")
    return d


def save(path, d):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, path)


def source_for_url(url, reg):
    host = (urlparse(url).hostname or "").lower()
    hits = [k for k, s in reg["sources"].items() if any(host == d or host.endswith("." + d) for d in s["domains"])]
    return hits[0] if len(hits) == 1 else None


def build(a, reg, now):
    src = a.source or source_for_url(a.url, reg)
    if not src:
        raise ValueError(f"no registered source for {urlparse(a.url).hostname}: use a source in sources.json "
                         "(a maintainer adds new ones)")
    it = dict(category=a.category, source=src, url=a.url)
    if a.ticker:
        it["ticker"] = a.ticker.upper()
    stamp = now.isoformat(timespec="seconds")
    it["observed_at"] = stamp if a.observed_at in ("", "now") else a.observed_at
    for f in FIELDS:
        v = getattr(a, f)
        if v in (None, ""):
            continue
        if f in TIME_FIELDS and v == "now":
            v = stamp
        it[f] = v
    prefix = f"{it['ticker']}-{a.category}-" if it.get("ticker") else f"{a.category}-"
    used = [x.get("id", "") for x in a._items]
    if a.id and a.id in used:
        raise ValueError(f"id {a.id} already used")
    nums = [int(i[len(prefix):]) for i in used if i.startswith(prefix) and i[len(prefix):].isdigit()]
    it["id"] = a.id or f"{prefix}{max(nums, default=0) + 1}"
    return it


def line(r):
    p = "; ".join(r.get("problems") or [])
    return (f"{r['status']:<10} {r.get('id', '?'):<28} {str(r.get('source_name')):<28} "
            f"{r.get('category', ''):<16} read {r.get('observed_age', '?')} ago" + (f"  -> {p}" if p else ""))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ad = sub.add_parser("add")
    ad.add_argument("--ledger", required=True)
    ad.add_argument("--category", required=True)
    ad.add_argument("--url", required=True)
    ad.add_argument("--ticker", default="")
    ad.add_argument("--source", default="", help="registry key; normally recognised from the URL")
    ad.add_argument("--observed-at", default="now")
    ad.add_argument("--value", type=float)
    ad.add_argument("--delay-min", type=int)
    for f in ("published_at", "event_date", "history_through", "form", "period_end", "latest_filing_checked_at",
              "next_release", "claim_id", "what", "id"):
        ad.add_argument("--" + f.replace("_", "-"), default="")
    for name in ("list", "check"):
        p = sub.add_parser(name)
        p.add_argument("--ledger", required=True)
        p.add_argument("--out", default="")
    dr = sub.add_parser("drop")
    dr.add_argument("--ledger", required=True)
    dr.add_argument("--id", required=True)
    a = ap.parse_args(argv)

    reg, now = sc.load_registry(), sc.CLOCK()
    led = load(a.ledger)
    if a.cmd == "add":
        a._items = led["items"]
        try:
            it = build(a, reg, now)
        except ValueError as e:
            print(json.dumps(dict(added=False, error=str(e)), indent=2))
            return 1
        same = [x for x in led["items"] if x.get("category") == it["category"] and
                x.get("ticker") == it.get("ticker") and x.get("url") == it["url"]]
        if same and not a.id:
            it["id"] = same[0].get("id", it["id"])      # re-reading a page keeps its id
        led["items"] = [x for x in led["items"] if x not in same] + [it]
        save(a.ledger, led)
        r = sc.check_item(it, reg, now)
        print(json.dumps(dict(added=True, id=it["id"], status=r["status"], source=r.get("source_name"),
                              tier=r.get("tier"), problems=r.get("problems")), indent=2))
        return 0 if r["status"] == "FRESH" else 1
    if a.cmd == "drop":
        before = len(led["items"])
        led["items"] = [x for x in led["items"] if x.get("id") != a.id]
        save(a.ledger, led)
        print(json.dumps(dict(dropped=before - len(led["items"]))))
        return 0
    out = sc.check(led, reg, now)
    if a.out:
        with open(a.out, "w") as f:
            json.dump(out, f, indent=2)
    if a.cmd == "list":
        for r in out["items"]:
            print(line(r))
        for w in out["warnings"]:
            print("WARNING    " + w)
        print("OK" if out["ok"] else f"NOT OK: {len(out['blocking'])} entr{'y' if len(out['blocking']) == 1 else 'ies'} to fix")
    else:
        print(json.dumps(out, indent=2))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
