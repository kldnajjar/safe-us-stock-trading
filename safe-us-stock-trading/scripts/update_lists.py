#!/usr/bin/env python3
"""One command to refresh the halal list and the boycott list (v5.3). Run it about once a month.

Run it yourself, in a terminal on a computer with internet (the assistant's own workspace has none):

    python3 safe-us-stock-trading/scripts/update_lists.py --store trade-store

It reads four public sources once each, politely (one request at a time, a pause between pages):
  halal    the SPUS holdings file SP Funds publishes for download (a certified Shariah fund)
  boycott  AFSC Investigate's occupations list, the BDS movement's target page, Who Profits' company list
then matches every holding's name against the three boycott lists, saves both lists in STORE/lists, and writes
the result files the trading engine reads. Standard library only. Nothing is sent anywhere.

Accuracy rules:
  * every name match counts as a match (the careful side). Wrong matches are printed under REVIEW; mark one
    with  "not_a_match": {"whoprofits": ["TGT"]}  in STORE/lists/OVERRIDES.json and run again.
  * a source that fails or looks wrong (too few names, a known name missing) is marked "did not answer":
    every stock is then UNVERIFIED for the boycott screen, never clean. Old lists are kept until a run succeeds.
  * your own halal lookups (lists.py set-halal) are kept and win over the fund list.
  --from-dir DIR reads saved pages instead of the web (spus.csv, afsc.html, bds.html, whoprofits_1.html ...):
    for a site that blocks scripts, save its page from your browser and use this.
Check each site's terms before scheduling this; AFSC's dataset page asks for-profit professionals to donate.
"""
import argparse, csv, datetime as dt, html, io, json, os, re, sys, time, urllib.request
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lists  # noqa: E402

UA = "Mozilla/5.0 (personal list refresh; safe-us-stock-trading update_lists.py)"
SPUS_CSV = "https://www.sp-funds.com/wp-content/uploads/data/TidalFG_Holdings_SPUS.csv"
AFSC = "https://investigate.afsc.org/occupations"
BDS = "https://bdsmovement.net/Guide-to-BDS-Boycott"
WHO = "https://www.whoprofits.org/index.php/companies?page={n}"
CONTROL = {"afsc": "caterpillar", "whoprofits": "caterpillar", "bds": "chevron"}      # long-listed names: must be there
MIN_NAMES = {"afsc": 150, "whoprofits": 300}


def fetch(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,text/csv,*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.out, self._href, self._buf = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._buf = dict(attrs).get("href") or "", []

    def handle_data(self, data):
        if self._href is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            self.out.append((self._href, " ".join("".join(self._buf).split()))); self._href = None


def company_links(page, marker="/company/"):
    p = _Links(); p.feed(page)
    seen = []
    for href, text in p.out:
        if marker in href and text and text not in seen:
            seen.append(text)
    return seen


def page_text(page):
    page = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", page)
    return " ".join(html.unescape(re.sub(r"(?s)<[^>]+>", " ", page)).split())


def spus_rows(text):
    """The fund's CSV -> ("T|CUSIP|Name;...", ISO date). Cash and odd lines are dropped."""
    rows, day = [], None
    for r in csv.DictReader(io.StringIO(text)):
        t, c, n = (r.get("StockTicker") or "").strip(), (r.get("CUSIP") or "").strip(), (r.get("SecurityName") or "").strip()
        try:
            value = float(r.get("MarketValue") or 0)
        except ValueError:
            value = 0
        if re.fullmatch(r"[A-Z][A-Z.]{0,5}", t) and re.fullmatch(r"[0-9A-Z]{9}", c) and value > 0:
            rows.append(f"{t}|{c}|{re.sub(r'/[A-Za-z]+$', '', n).replace('|', ' ').replace(';', ' ')}")
            if not day and r.get("Date"):
                m, d, y = r["Date"].split("/")
                day = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    return ";".join(rows), day


def gather(src_dir=None, pause=1.0, log=print):
    """Read every source. Returns (pages dict, problems dict). A failed source is a problem, never a guess."""
    got, bad = {}, {}

    def read(name, url):
        if src_dir:
            with open(os.path.join(src_dir, name)) as f:
                return f.read()
        time.sleep(pause)
        return fetch(url)
    for key, name, url in (("spus", "spus.csv", SPUS_CSV), ("afsc", "afsc.html", AFSC), ("bds", "bds.html", BDS)):
        try:
            got[key] = read(name, url); log(f"read {key}")
        except Exception as e:
            bad[key] = f"{e.__class__.__name__}: {e}"
    names, n = [], 0
    try:
        for n in range(1, 81):
            if src_dir and not os.path.exists(os.path.join(src_dir, f"whoprofits_{n}.html")):
                break
            new = [x for x in company_links(read(f"whoprofits_{n}.html", WHO.format(n=n))) if x not in names]
            if not new:
                break
            names += new
        got["whoprofits"] = names; log(f"read whoprofits ({n} pages, {len(names)} names)")
    except Exception as e:
        bad["whoprofits"] = f"{e.__class__.__name__}: {e}"
    return got, bad


def update(store, src_dir=None, pause=1.0, log=print, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date().isoformat()
    got, bad = gather(src_dir, pause, log)
    report = dict(problems=bad, review={}, halal=None, boycott=None)
    if "spus" in got:
        text, day = spus_rows(got["spus"])
        if text.count(";") + 1 < 100 or not day:
            bad["spus"] = "holdings file looks wrong (fewer than 100 stocks or no date): halal list kept as it was"
        else:
            report["halal"] = lists.halal_add(store, text, day, SPUS_CSV)
    hl = lists._load(lists._path(store, "HALAL_LIST.json"))
    if not hl:
        report["error"] = "no halal list: nothing to screen"
        return report
    over, sites, hits = lists.overrides(store), {}, {}
    afsc = company_links(got["afsc"]) if "afsc" in got else []
    who = got.get("whoprofits") or []
    bds_text = page_text(got["bds"]).lower() if "bds" in got else ""
    found = {"afsc": lists.match_names(hl["rows"], afsc), "whoprofits": lists.match_names(hl["rows"], who),
             "bds": {t: [k] for t, r in hl["rows"].items() for k in lists.search_words(t, r["name"])
                     if re.search(r"(^|[^a-z0-9])" + re.escape(k) + r"([^a-z0-9]|$)", bds_text)}}
    urls = {"afsc": AFSC, "bds": BDS, "whoprofits": WHO.format(n=1)}
    for k in lists.LISTS:
        names = {"afsc": afsc, "whoprofits": who}.get(k)
        ok = k not in bad and (CONTROL[k] in bds_text if k == "bds" else
                               len(names) >= MIN_NAMES[k] and any(CONTROL[k] in x.lower() for x in names))
        if not ok and k not in bad:
            bad[k] = "the page loaded but looks wrong (too few names or a long-listed name is missing)"
        sites[k] = dict(ok=bool(ok), url=urls[k])
        skip = {str(x).upper() for x in over["not_a_match"].get(k) or []}
        hits[k] = sorted((set(found[k]) - skip) | {str(x).upper() for x in over["match"].get(k) or []})
        for t in sorted(set(found[k]) - skip):
            report["review"].setdefault(t, []).append(f"{k}: {', '.join(found[k][t][:2])}")
    report["boycott"] = lists.boycott_add(store, today, sites, hits)
    out = lists.apply(store, None, today)
    tally = {}
    for r in out.get("rows", []):
        tally[(r["boycott"], r["halal"])] = tally.get((r["boycott"], r["halal"]), 0) + 1
    report["results"] = {f"{b} / {h}": n for (b, h), n in sorted(tally.items())}
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--store", required=True, help="the folder that keeps your lists and results (e.g. trade-store)")
    ap.add_argument("--from-dir", help="read saved pages from this folder instead of the web")
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests (default 1)")
    a = ap.parse_args(argv)
    rep = update(a.store, a.from_dir, a.pause)
    print("\nHALAL LIST:", rep["halal"] or "kept as it was")
    print("BOYCOTT LIST:", rep["boycott"])
    print("RESULTS:"); [print(f"  {n:4}  {k}") for k, n in (rep.get("results") or {}).items()]
    if rep["review"]:
        print("\nREVIEW (each counts as a boycott match until you say otherwise in lists/OVERRIDES.json):")
        [print(f"  {t:6} {'; '.join(v)}") for t, v in sorted(rep["review"].items())]
    if rep["problems"]:
        print("\nPROBLEMS (a boycott source that did not answer leaves every stock UNVERIFIED):")
        [print(f"  {k}: {v}") for k, v in rep["problems"].items()]
    sys.exit(1 if rep.get("error") or rep["problems"] else 0)


if __name__ == "__main__":
    main()
