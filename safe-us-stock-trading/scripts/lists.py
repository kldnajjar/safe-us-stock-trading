#!/usr/bin/env python3
"""Screen from saved lists (v5.3): a halal list and a boycott list kept in the store, read with no web call.

The halal list is the published holdings file of a certified Shariah fund (default: SPUS, SP Funds S&P 500
Sharia Industry Exclusions ETF): a stock the fund holds passed the fund's own Shariah screen on that date.
The boycott list records, for the same names, which of them AFSC Investigate (its occupations list), the BDS
target page and Who Profits name. Lists are data the user's own session gathered: they live in the store,
never in the skill, and are rebuilt about once a month (a boycott finding counts for 30 days).

  lists.py halal-add   --store S --file HOLDINGS.txt --as-of YYYY-MM-DD --url URL [--provider spus]
  lists.py keys        --store S                 search words per ticker, to paste into browser_boycott.js
  lists.py boycott-add --store S --as-of YYYY-MM-DD --sites JSON --hits JSON
  lists.py apply       --store S [--tickers A,B]  write result files for the engine and PRESCREEN.json
  lists.py check       --store S T1 T2 ...        look tickers up (no files written)
  lists.py set-halal   --store S TICKER halal|not_halal|doubtful|clear [YYYY-MM-DD]
                       what the USER found on a screening provider (Musaffa); it wins over the fund list
To rebuild both lists in one go, run update_lists.py on a computer with internet (see that file).

HOLDINGS.txt: "TICKER|CUSIP|Name;..." taken from the fund's own holdings file.
--sites: {"afsc": {"ok": true, "url": "https://..."}, "bds": {...}, "whoprofits": {...}}; a site that did not
answer is left out or "ok": false and every name is then UNVERIFIED, never clean.
--hits: {"afsc": ["MSFT", ...], "bds": [...], "whoprofits": [...]}: confirmed matches after opening each lead.
Halal authority (v5.3): the saved fund list by default, so no question is asked: a stock the fund holds is halal
by that fund's own screen. Checking Musaffa is OPTIONAL: if the user reports its verdict (set-halal; kept 120 days)
it wins over the fund list. Set "halal_authority": "musaffa" in STORE/lists/OVERRIDES.json to make the fund list
only a shortlist ("your call" until the user reports Musaffa's verdict).
A ticker that is not on the halal list gets no halal result here ("not on the list" is not "not halal").
"""
import argparse, datetime as dt, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SUFFIX = {"inc", "corp", "co", "plc", "ltd", "nv", "holdings", "holding", "cos", "the", "group", "sa", "ag", "&"}
EXTRA = {"GOOGL": ["google"], "XOM": ["exxon"], "IBM": ["ibm"], "SLB": ["schlumberger"], "NVDA": ["mellanox"],
         "AVGO": ["vmware"], "LLY": ["lilly"], "PG": ["procter"], "P": ["pure storage"], "FDXF": ["fedex"],
         "UPS": ["ups"], "WAB": ["wabtec"], "EL": ["estée lauder"], "MMM": ["3m company"], "DHI": ["d.r. horton"],
         "JBHT": ["j.b. hunt"], "CHRW": ["c.h. robinson"], "GWW": ["grainger"], "AOS": ["a. o. smith"]}
LISTS = ("afsc", "bds", "whoprofits")


def isin_from_cusip(cusip):
    """US ISIN for a US CUSIP (first character a digit). Foreign CUSIPs have another country code: returns ""."""
    if not re.fullmatch(r"[0-9][0-9A-Z]{8}", cusip or ""):
        return ""
    body = "US" + cusip
    digits, total = "".join(str(int(c, 36)) for c in body), 0
    for k, c in enumerate(reversed(digits)):
        n = int(c) * (2 if k % 2 == 0 else 1)
        total += n // 10 + n % 10
    return body + str((10 - total % 10) % 10)


def keys_for(ticker, name):
    words = [w for w in re.split(r"\s+", name.lower().replace(",", " ")) if w]
    while words and words[-1].strip(".") in SUFFIX:
        words.pop()
    key = " ".join(words)
    return [k for k in dict.fromkeys([key] + EXTRA.get(ticker, [])) if len(k) >= 2]


GENERIC = set("united texas first general american international applied analog advanced boston cardinal carrier "
              "charles comfort constellation steel tractor waste republic monster norfolk illinois martin monolithic "
              "packaging quanta rockwell zebra target trane tyler union vulcan waters church emerson edwards micron "
              "microchip marvell align genuine lennox mettler bloom".split())


def search_words(ticker, name):
    """keys_for plus the first word when it is distinctive (cisco, expedia): wider, so a lead is not missed."""
    out = list(keys_for(ticker, name))
    for k in list(out):
        first = k.split(" ")[0]
        if len(first) >= 5 and first not in GENERIC and first not in out:
            out.append(first)
    return out


def match_names(rows, names):
    """{ticker: [listed names]} for every holding whose search word appears as whole words in a listed name."""
    hits = {}
    low = [(n, n.lower()) for n in names]
    for t, r in rows.items():
        for k in search_words(t, r["name"]):
            rx = re.compile(r"(^|[^a-z0-9])" + re.escape(k) + r"([^a-z0-9]|$)")
            for n, ln in low:
                if rx.search(ln) and n not in hits.setdefault(t, []):
                    hits[t].append(n)
    return {t: v for t, v in hits.items() if v}


def overrides(store):
    o = _load(_path(store, "OVERRIDES.json")) or {}
    return dict(not_a_match=o.get("not_a_match") or {}, match=o.get("match") or {}, halal=o.get("halal") or {},
                halal_authority=o.get("halal_authority") or "fund")


USER_VERDICT_DAYS = 120


def user_verdict(store, ticker, today):
    """The user's own provider lookup for this ticker if it is still current (120 days), else None."""
    said = overrides(store)["halal"].get(ticker.upper())
    try:
        age = (today - dt.date.fromisoformat(said["date"])).days if said else None
    except (KeyError, TypeError, ValueError):
        return None
    return said if said and 0 <= age <= USER_VERDICT_DAYS else None


def set_halal(store, ticker, verdict, date=None, note=""):
    """Record what the USER found on a screening provider (Musaffa): halal, not_halal, doubtful, or clear to remove."""
    o = overrides(store)
    if verdict == "clear":
        o["halal"].pop(ticker.upper(), None)
    else:
        if verdict not in ("halal", "not_halal", "doubtful"):
            raise ValueError("verdict must be halal, not_halal, doubtful or clear")
        o["halal"][ticker.upper()] = dict(verdict=verdict, date=date or dt.datetime.now(dt.timezone.utc).date().isoformat(), note=note)
    with open(_path(store, "OVERRIDES.json"), "w") as f:
        json.dump(o, f, indent=1)
    return o["halal"]


def _path(store, name):
    d = os.path.join(store, "lists")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, name)


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def halal_add(store, text, as_of, url, provider="spus"):
    rows = {}
    for part in text.strip().split(";"):
        f = [x.strip() for x in part.split("|")]
        if len(f) == 3 and re.fullmatch(r"[A-Z][A-Z.]{0,5}", f[0]):
            rows[f[0]] = dict(cusip=f[1], name=f[2], isin=isin_from_cusip(f[1]))
    dt.date.fromisoformat(as_of)
    out = dict(schema="halal-list/1", provider=provider, url=url, as_of=as_of, rows=rows)
    with open(_path(store, "HALAL_LIST.json"), "w") as f:
        json.dump(out, f, indent=1)
    return dict(saved=len(rows), without_isin=sorted(t for t, r in rows.items() if not r["isin"]))


def boycott_add(store, as_of, sites, hits):
    hl = _load(_path(store, "HALAL_LIST.json")) or {}
    dt.date.fromisoformat(as_of)
    out = dict(schema="boycott-list/1", as_of=as_of, sites=sites, covers=sorted(hl.get("rows") or {}),
               hits={k: sorted({str(t).upper() for t in (hits.get(k) or [])}) for k in LISTS})
    with open(_path(store, "BOYCOTT_LIST.json"), "w") as f:
        json.dump(out, f, indent=1)
    return dict(covers=len(out["covers"]), listed=sorted({t for v in out["hits"].values() for t in v}))


def lookup(store, tickers, today=None):
    """Per ticker: (halal, boycott, note) from the lists alone."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    hl, bl = _load(_path(store, "HALAL_LIST.json")) or {}, _load(_path(store, "BOYCOTT_LIST.json")) or {}
    out = {}
    b_age = (today - dt.date.fromisoformat(bl["as_of"])).days if bl.get("as_of") else None
    for t in tickers:
        t = t.upper()
        on = t in (hl.get("rows") or {})
        said = user_verdict(store, t, today)
        by = [k for k in LISTS if t in ((bl.get("hits") or {}).get(k) or [])]
        if t not in (bl.get("covers") or []):
            b = "NOT ON FILE"
        elif b_age is None or b_age > 30 or any(not (bl.get("sites") or {}).get(k, {}).get("ok") for k in LISTS):
            b = "LIST TOO OLD OR INCOMPLETE"
        else:
            b = "LISTED BY " + ", ".join(by).upper() if by else "NOT ON LISTS"
        h = f"ON {str(hl.get('provider')).upper()} LIST ({hl.get('as_of')})" if on else "NOT ON THE HALAL LIST"
        if on and not said and overrides(store)["halal_authority"] == "musaffa":
            h += ": CONFIRM ON MUSAFFA"
        if said:
            h = f"YOU REPORTED {said['verdict'].replace('_', ' ').upper()} ({said['date']})" + ("; ALSO " + h if on else "")
        out[t] = dict(halal=h, boycott=b)
    return out


def run(script, args):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)] + args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return dict(error=(r.stderr or r.stdout).strip()[-200:])


def apply(store, tickers=None, as_of=None, methodology="aaoifi"):
    as_of = as_of or dt.datetime.now(dt.timezone.utc).date().isoformat()
    hl, bl = _load(_path(store, "HALAL_LIST.json")), _load(_path(store, "BOYCOTT_LIST.json"))
    if not hl or not bl:
        return dict(error="build the lists first (halal-add, then boycott-add)")
    rows = []
    for t in sorted(tickers or hl["rows"]):
        t = t.upper()
        meta = hl["rows"].get(t)
        if not meta:
            rows.append(dict(ticker=t, sector="", boycott="NOT RUN", halal="NOT RUN", note="not on the halal list: no result from the lists")); continue
        src = {}
        for k in LISTS:
            site = (bl.get("sites") or {}).get(k) or {}
            ok = site.get("ok") and str(site.get("url", "")).startswith("https://") and t in bl.get("covers", [])
            src[k] = dict(finding=("match" if t in bl["hits"].get(k, []) else "no_match") if ok else "unreachable",
                          checked_on=bl["as_of"], url=site.get("url") or "")
        ev = dict(ticker=t, isin=meta["isin"], entity=meta["name"], asset="stock", depth="quick",
                  identity_resolved=bool(meta["isin"]), related_entities=[f"searched: {k}" for k in keys_for(t, meta["name"])],
                  sources=src)
        e_path, b_path, s_path = (os.path.join(store, f"{k}_{t}.json") for k in ("EVIDENCE", "BOYCOTT", "SCREEN"))
        with open(e_path, "w") as f:
            json.dump(ev, f, indent=1)
        b = run("boycott_screen.py", ["--evidence", e_path, "--as-of", as_of, "--out", b_path])
        said = user_verdict(store, t, dt.date.fromisoformat(as_of))
        confirm = [] if overrides(store)["halal_authority"] != "musaffa" else ["--needs-confirmation"]
        if said:                                   # the user's own lookup on a screening provider wins over the fund list
            s = run("shariah_screen.py", ["--asset", "stock", "--ticker", t, "--isin", meta["isin"], "--entity", meta["name"],
                                          "--methodology", methodology, "--as-of", as_of, "--provider", "musaffa",
                                          "--provider-verdict", said["verdict"], "--provider-date", said["date"],
                                          "--provider-methodology", "AAOIFI", "--provider-url", f"https://musaffa.com/stock/{t}/",
                                          "--out", s_path])
        else:
            s = run("shariah_screen.py", ["--asset", "stock", "--ticker", t, "--isin", meta["isin"], "--entity", meta["name"],
                                          "--methodology", methodology, "--as-of", as_of, "--provider", hl["provider"],
                                          "--provider-verdict", "halal", "--provider-date", hl["as_of"],
                                          "--provider-methodology", "AAOIFI (the fund's own screen)",
                                          "--provider-url", hl["url"], "--out", s_path] + confirm)
        note = "; ".join(x for x in ("; ".join((b.get("reasons") or [])[:1]) if b.get("status") != "REVIEWED_NO_MATCH" else "",
                                     "" if meta["isin"] else "foreign-registered share: ISIN not on file, confirm it in your app",
                                     (f"halal: you reported {said['verdict'].replace('_', ' ')} ({said['date']})" if said
                                      else f"halal: held by {hl['provider'].upper()} on {hl['as_of']}"
                                      + ("; confirm on Musaffa and tell me" if confirm
                                         else "; optional: check Musaffa yourself and tell me if it differs"))) if x)
        rows.append(dict(ticker=t, sector="", boycott=b.get("status") or "NOT RUN", halal=s.get("policy_decision") or "NOT RUN", note=note[:300]))
    out = dict(schema="prescreen/1", as_of=as_of, methodology=methodology, rows=rows)
    with open(os.path.join(store, "PRESCREEN.json"), "w") as f:
        json.dump(out, f, indent=1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("halal-add", "keys", "boycott-add", "apply", "check", "set-halal"))
    ap.add_argument("names", nargs="*")
    ap.add_argument("--store", required=True)
    for k in ("file", "as-of", "url", "sites", "hits", "tickers"):
        ap.add_argument(f"--{k}")
    ap.add_argument("--provider", default="spus")
    a = ap.parse_intermixed_args(argv)
    if a.cmd == "halal-add":
        print(json.dumps(halal_add(a.store, open(a.file).read(), a.as_of, a.url, a.provider)))
    elif a.cmd == "keys":
        hl = _load(_path(a.store, "HALAL_LIST.json")) or {"rows": {}}
        print(";".join(f"{t}:{'|'.join(keys_for(t, r['name']))}" for t, r in sorted(hl["rows"].items())))
    elif a.cmd == "boycott-add":
        print(json.dumps(boycott_add(a.store, a.as_of, json.loads(a.sites), json.loads(a.hits))))
    elif a.cmd == "set-halal":                  # lists.py set-halal --store S MSFT not_halal [YYYY-MM-DD]
        print(json.dumps(set_halal(a.store, a.names[0], a.names[1], a.names[2] if len(a.names) > 2 else None)))
    elif a.cmd == "check":
        for t, r in lookup(a.store, a.names).items():
            print(f"{t:6} halal: {r['halal']:34} boycott: {r['boycott']}")
    else:
        out = apply(a.store, a.tickers.split(",") if a.tickers else None, a.as_of)
        if out.get("error"):
            sys.exit(out["error"])
        tally = {}
        for r in out["rows"]:
            tally.setdefault((r["boycott"], r["halal"]), []).append(r["ticker"])
        for k, v in sorted(tally.items()):
            print(f"{k[0]} / {k[1]} ({len(v)}): {' '.join(v)}")


if __name__ == "__main__":
    main()
