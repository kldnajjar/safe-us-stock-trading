#!/usr/bin/env python3
"""Check many stocks ahead of time (v5.3): boycott and halal results for a whole pool, saved to the store.

Screen results stay valid for weeks (boycott 30 days, halal to its own expiry), so they do not have to be
made during a trade run. This tool turns three small inputs into result files for every stock at once,
by calling the same boycott_screen.py and shariah_screen.py the trade run uses. It looks at no price
history, sizes nothing and names no buy. Stocks only: funds and metal trusts need their own documents.

  quick (default, one source each):
  python3 prescreen.py --halal HALAL.json --review REVIEW.json --store STORE
  full (five boycott sources, halal worked out from SEC numbers):
  python3 prescreen.py --depth full --facts FACTS.json --prices SCAN.json --review REVIEW.json --store STORE

  HALAL.json   {"rows": ["AAPL|200|HALAL|AAOIFI|November 2026", ...]}: verdicts the USER looked up on the provider's
               own page or app and reported. Never fetched by a script: the provider's terms forbid automated reading.

  FACTS.json   browser_facts.js with COMPACT = true (SEC numbers and Israel mentions per ticker)
  SCAN.json    browser_fetch.js MODE "scan" (only the price is used, for today's market cap)
  REVIEW.json  what the assistant found on the lists AFTER opening every lead from browser_boycott.js:
     {"sites": {"afsc": {"ok": true, "url": "https://..."}, "whoprofits": {...}, "bds": {...},
                "ohchr": {"ok": true, "url": "https://...", "list_version": "A/HRC/63/20"}},
      "matches": {"afsc": {"NVDA": "https://investigate.afsc.org/company/nvidia"}, "whoprofits": {}, "bds": {},
                  "ohchr": {}},
      "sec_material_ops": ["NVDA"], "israel_hq": [], "version_seen": {"aaoifi": "SS-21"}}
     A site with "ok": false (or missing) is recorded as unreachable for every ticker, never as no_match.
     "matches" holds confirmed matches only; an AFSC entry about prisons or borders alone is not a match.

Identity (legal name, ISIN, search words) and the business reading come from universe.json "stocks".
Halal numbers follow the conservative mapping in SKILL.md (fast path, rule 6). A number SEC does not hold
for the newest balance-sheet date is not passed, so the screen answers INSUFFICIENT_DATA; nothing is filled in.
Writes EVIDENCE_T.json, BOYCOTT_T.json, SCREEN_T.json and PRESCREEN.json (the summary) into the store.
"""
import argparse, datetime as dt, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
INSTANT = ["Assets", "LongTermDebt", "LongTermDebtNoncurrent", "LongTermDebtCurrent", "CommercialPaper",
           "ShortTermBorrowings", "DebtCurrent", "LongTermDebtAndCapitalLeaseObligations",
           "CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments", "ShortTermInvestments",
           "MarketableSecuritiesCurrent", "MarketableSecuritiesNoncurrent", "AvailableForSaleSecuritiesDebtSecurities",
           "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
           "LongTermInvestments", "AccountsReceivableNetCurrent"]
FLOW = ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "RevenuesNetOfInterestExpense",
        "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet", "InvestmentIncomeInterest",
        "InvestmentIncomeInterestAndDividend", "InterestIncomeOther", "InterestAndOtherIncome", "InvestmentIncomeNet",
        "InterestIncomeOperating", "InterestExpense", "InterestExpenseNonoperating", "NonoperatingIncomeExpense"]
REVENUE, INTEREST = FLOW[:5], FLOW[5:11]
LISTS = ("ohchr", "bds", "afsc", "whoprofits")
M = 1e6


def unpack(rec):
    """Compact record -> ({tag: USD}, {tag: USD}); empty fields are simply absent."""
    def vals(names, text):
        parts = str(text or "").split(",")
        return {k: float(v) * M for k, v in zip(names, parts) if v not in ("", None)} if len(parts) == len(names) else {}
    return vals(INSTANT, rec.get("i")), vals(FLOW, rec.get("fl"))


def halal_inputs(rec, price):
    """The shariah_screen.py numbers from one compact record. Returns (args dict, notes); missing stays missing."""
    i, f = unpack(rec)
    notes, a = [], {}

    def first(d, names):
        return next((d[k] for k in names if k in d), None)
    if "Assets" in i:
        a["total-assets"] = i["Assets"]
    # Debt: build it every way the filed tags allow and take the largest (the careful side for a debt limit).
    short = i.get("CommercialPaper", 0.0) + i.get("ShortTermBorrowings", 0.0)
    current = max(i.get("DebtCurrent", 0.0), i.get("LongTermDebtCurrent", 0.0) + short)
    ways = []
    if "LongTermDebt" in i:                                     # by definition includes the current part
        ways.append(i["LongTermDebt"] + short)
    for k in ("LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"):
        if k in i:
            ways.append(i[k] + current)
    if not ways:
        notes.append("no long-term debt figure in SEC's facts: read the filing")
    else:
        a["interest-debt"] = a["total-debt"] = max(ways)
    cash = i.get("CashAndCashEquivalentsAtCarryingValue")
    if cash is not None:
        a["cash"] = cash
        if "MarketableSecuritiesCurrent" in i or "MarketableSecuritiesNoncurrent" in i:
            sec = i.get("MarketableSecuritiesCurrent", 0.0) + i.get("MarketableSecuritiesNoncurrent", 0.0)
        elif "AvailableForSaleSecuritiesDebtSecurities" in i:
            sec = i["AvailableForSaleSecuritiesDebtSecurities"]
        elif "AvailableForSaleSecuritiesDebtSecuritiesCurrent" in i or "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent" in i:
            sec = i.get("AvailableForSaleSecuritiesDebtSecuritiesCurrent", 0.0) + i.get("AvailableForSaleSecuritiesDebtSecuritiesNoncurrent", 0.0)
        else:
            sec = i.get("ShortTermInvestments", 0.0) + i.get("LongTermInvestments", 0.0)
            notes.append("no marketable-securities line: short- and long-term investments counted instead")
        a["interest-securities"] = sec
        a["interest-deposits"] = cash + sec
    if "AccountsReceivableNetCurrent" in i:
        a["receivables"] = i["AccountsReceivableNetCurrent"]
    rev = first(f, REVENUE)
    if rev is not None:
        a["total-income"] = rev + max(f.get("NonoperatingIncomeExpense", 0.0), 0.0)
    npi = first(f, INTEREST)
    if npi is None:
        notes.append("interest income is not its own line in SEC's facts: read the filing")
    else:
        a["nonpermissible-income"] = max(npi, 0.0)
    if rec.get("so") and price:
        a["market-cap"] = float(rec["so"]) * float(price)
        a["shares-outstanding"] = float(rec["so"])
        near = [k for k in ("interest-debt", "interest-deposits") if a.get(k, 0.0) / a["market-cap"] > 0.2]
        if near:
            notes.append("near a 30% limit (" + ", ".join(near) + "): read the filing before relying on it")
    else:
        notes.append("no single share count in SEC's facts (several share classes?): market cap not worked out")
    return a, notes


def prices_of(scan):
    out = {}
    for row in (scan or {}).get("rows") or []:
        parts = str(row).split("|")
        try:
            out[parts[0].upper()] = float(parts[1])
        except (IndexError, ValueError):
            pass
    out.update({str(k).upper(): float(v) for k, v in ((scan or {}).get("prices") or {}).items()})
    return out


MONTHS = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}


def provider_rows(halal):
    """browser_halal.js rows -> {ticker: (verdict, methodology, YYYY-MM-01)}; unreadable rows are left out."""
    out = {}
    for row in (halal or {}).get("rows") or []:
        p = str(row).split("|")
        if len(p) != 5 or p[1] != "200" or "?" in p[2:]:
            continue
        verdict = {"HALAL": "halal", "NOT HALAL": "not_halal", "DOUBTFUL": "doubtful"}.get(p[2].strip())
        month, _, year = p[4].strip().partition(" ")
        if verdict and month.lower() in MONTHS and year.isdigit():
            out[p[0].upper()] = (verdict, p[3].strip(), f"{int(year):04d}-{MONTHS[month.lower()]:02d}-01")
    return out


def evidence(t, meta, rec, review, as_of, depth="full"):
    sites, matches = review.get("sites") or {}, review.get("matches") or {}
    src = {}
    for k in LISTS:
        site = sites.get(k) or {}
        if depth == "quick" and k not in ("afsc", "bds", "whoprofits") and not site:
            continue                                  # a quick screen needs AFSC, BDS and Who Profits; OHCHR counts when given
        hit = (matches.get(k) or {}).get(t)
        if not site.get("ok") or not str(site.get("url", "")).startswith("https://"):
            src[k] = dict(finding="unreachable", checked_on=as_of, url=site.get("url") or "")
        elif hit:
            url = hit.get("url") if isinstance(hit, dict) else hit
            src[k] = dict(finding="match", checked_on=as_of, url=url or site["url"])
            if isinstance(hit, dict) and hit.get("involvement"):
                src[k]["involvement"] = hit["involvement"]
        else:
            src[k] = dict(finding="no_match", checked_on=as_of, url=site["url"])
        if k == "ohchr" and site.get("list_version"):
            src[k]["list_version"] = site["list_version"]
    if depth == "quick" and not rec:
        return dict(ticker=t, isin=meta.get("isin") or "", entity=meta.get("entity") or t, asset="stock", depth="quick",
                    identity_resolved=bool(meta.get("isin") and meta.get("entity")),
                    related_entities=[f"searched: {w}" for w in meta.get("search") or []], sources=src)
    f = rec.get("f") or []
    url = f"https://www.sec.gov/Archives/edgar/data/{int(rec['k'])}/{f[3]}" if len(f) == 4 and rec.get("k") else ""
    il = rec.get("il", -1)
    ops, hq = t in (review.get("sec_material_ops") or []), t in (review.get("israel_hq") or [])
    src["sec"] = dict(finding="unreachable" if (il is None or il < 0 or not url) else ("match" if ops or hq else "no_match"),
                      checked_on=as_of, url=url, israel_hq=hq, material_israel_ops=ops)
    ev = dict(ticker=t, isin=meta.get("isin") or "", entity=meta.get("entity") or t, asset="stock",
              identity_resolved=bool(meta.get("isin") and meta.get("entity")),
              related_entities=[f"searched: {w}" for w in meta.get("search") or []], sources=src)
    if depth == "quick":
        ev.update(depth="quick")
    return ev


def run(script, args):
    r = subprocess.run([sys.executable, os.path.join(HERE, script)] + args, capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return dict(error=(r.stderr or r.stdout).strip()[-200:])


def prescreen(facts, scan, review, store, as_of, methodology="aaoifi", universe=None, halal=None, depth="full"):
    uni = universe or json.load(open(os.path.join(HERE, "universe.json")))
    stocks, px = uni.get("stocks") or {}, prices_of(scan)
    sector = {t: s for s, ts in (uni.get("sectors") or {}).items() for t in ts}
    os.makedirs(store, exist_ok=True)
    rows, verdicts = [], provider_rows(halal)
    todo = dict((facts or {}).get("tickers") or {})
    for t in verdicts:
        todo.setdefault(t, {})
    for t, rec in sorted(todo.items()):
        t, meta = t.upper(), stocks.get(t.upper())
        if not meta:
            rows.append(dict(ticker=t, sector=sector.get(t, ""), boycott="NOT RUN", halal="NOT RUN", note="not in universe.json stocks")); continue
        if rec.get("e"):
            rows.append(dict(ticker=t, sector=sector.get(t, ""), boycott="NOT RUN", halal="NOT RUN", note=str(rec["e"]))); continue
        ev_path, b_path, s_path = (os.path.join(store, f"{k}_{t}.json") for k in ("EVIDENCE", "BOYCOTT", "SCREEN"))
        with open(ev_path, "w") as fh:
            json.dump(evidence(t, meta, rec, review, as_of, depth), fh, indent=1)
        b = run("boycott_screen.py", ["--evidence", ev_path, "--as-of", as_of, "--out", b_path])
        nums, notes = halal_inputs(rec, px.get(t))
        f = rec.get("f") or ["", "", "", ""]
        if rec.get("lag"):
            notes.insert(0, "a newer filing exists than SEC's facts cover: read it")
        args = ["--asset", "stock", "--ticker", t, "--isin", meta.get("isin") or "", "--entity", meta.get("entity") or t,
                "--methodology", methodology, "--as-of", as_of, "--business", meta.get("business") or "",
                "--period", f"{f[0]} to {rec.get('bs')} (from {rec.get('st')})", "--data-published", f[1],
                "--market-cap-date", as_of, "--auto-inputs", "--out", s_path]
        seen = (review.get("version_seen") or {}).get(methodology)
        if seen:
            args += ["--source-version-seen", seen]
        if not meta.get("business"):
            args = [x for k, x in enumerate(args) if not (args[k - 1] == "--business" or x == "--business")]
        for k, v in nums.items():
            args += [f"--{k}", repr(float(v))]
        if t in verdicts:                      # quick halal screen: the provider's published verdict, copied
            v, meth, day = verdicts[t]
            notes = [f"halal: Musaffa's verdict ({day[:7]}), reported by the user"]
            s = run("shariah_screen.py", [
                "--asset", "stock", "--ticker", t, "--isin", meta.get("isin") or "", "--entity", meta.get("entity") or t,
                "--methodology", methodology, "--as-of", as_of, "--provider", "musaffa", "--provider-verdict", v,
                "--provider-date", day, "--provider-methodology", meth,
                "--provider-url", f"https://musaffa.com/stock/{t}/", "--out", s_path])
        else:
            s = {} if rec.get("lag") else run("shariah_screen.py", args)
        why = "; ".join((b.get("reasons") or [])[:1] if b.get("status") not in ("REVIEWED_NO_MATCH",) else [])
        hw = "" if t in verdicts else "; ".join((s.get("reasons") or [])[:2])
        rows.append(dict(ticker=t, sector=sector.get(t, ""), boycott=b.get("status") or "NOT RUN",
                         halal=s.get("policy_decision") or "NOT RUN",
                         note="; ".join(x for x in (why, hw, "; ".join(notes)) if x)[:300]))
    out = dict(schema="prescreen/1", as_of=as_of, methodology=methodology, rows=rows)
    with open(os.path.join(store, "PRESCREEN.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    for k in ("review", "store"):
        ap.add_argument(f"--{k}", required=True)
    ap.add_argument("--facts", help="browser_facts.js COMPACT output (full depth: SEC numbers and the SEC boycott source)")
    ap.add_argument("--prices", help="scan output; only needed when halal is computed from --facts")
    ap.add_argument("--halal", help="verdicts the user looked up on the provider's page and reported (quick halal screen)")
    ap.add_argument("--depth", choices=("quick", "full"), default="quick",
                    help="boycott depth: quick = AFSC, BDS and Who Profits (default); full = all five sources")
    ap.add_argument("--as-of", default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument("--methodology", default="aaoifi")
    a = ap.parse_args(argv)
    load = lambda p: json.load(open(p))  # noqa: E731
    out = prescreen(load(a.facts) if a.facts else {}, load(a.prices) if a.prices else {}, load(a.review), a.store,
                    a.as_of, a.methodology, halal=load(a.halal) if a.halal else None, depth=a.depth)
    for r in out["rows"]:
        print(f"{r['ticker']:6}{r['boycott']:19}{r['halal']:21}{r['note'][:110]}")


if __name__ == "__main__":
    main()
