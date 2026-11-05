#!/usr/bin/env python3
"""Boycott screen for the safe-us-stock-trading skill (v4.4): companies complicit with Israel.

The status is COMPUTED from source-by-source evidence, never typed in. Evidence is
what the assistant found on each source page (finding, date checked, URL). This is a
structured record of research, not independent verification of the sources.

Evidence JSON (--evidence FILE):
{
  "ticker": "ABC", "isin": "US0000000001", "entity": "ABC Corp", "asset": "stock|etf|metal|tbill",
  "identity_resolved": true,
  "related_entities": ["ABC Holdings (parent)", "ABC Labs (subsidiary)"],
  "sources": {
    "ohchr":      {"finding": "match|no_match|unreachable", "checked_on": "YYYY-MM-DD", "url": "https://...",
                   "list_version": "A/HRC/63/20", "involvement": "contributing|directly linked"},
    "bds":        {"finding": ..., "checked_on": ..., "url": ...},
    "afsc":       {"finding": ..., "checked_on": ..., "url": ...},
    "whoprofits": {"finding": ..., "checked_on": ..., "url": ...},
    "sec":        {"finding": "no_match|match|unreachable", "checked_on": ..., "url": ...,
                   "israel_hq": false, "material_israel_ops": false}
  },
  "etf": {"screened_weight_pct": 100, "excluded_weight_pct": 0, "flagged_weight_pct": 0}   (ETFs only)
}
ETF weights are percentages of the fund: each a finite number from 0 to 100, screened exactly 100,
and excluded + flagged <= screened. Anything else is UNVERIFIED.

  python3 boycott_screen.py --evidence EVIDENCE.json --as-of YYYY-MM-DD [--strictness strict|moderate] --out RESULT.json
"""
import argparse, datetime as dt, json, math

SCHEMA = "boycott-result/1"
SOURCES = ("ohchr", "bds", "afsc", "whoprofits", "sec")
LIST_SOURCES = ("ohchr", "bds", "afsc", "whoprofits")
FINDINGS = ("match", "no_match", "unreachable")
MAX_EVIDENCE_AGE_DAYS = 30
RESULT_VALID_DAYS = 30


def compute_status(ev, as_of, strictness="strict"):
    """Returns (status, reasons). status: EXCLUDED | FLAGGED | REVIEWED_NO_MATCH | UNVERIFIED."""
    reasons = []
    today = dt.date.fromisoformat(as_of)
    for k in ("ticker", "entity", "asset"):
        if not ev.get(k):
            reasons.append(f"evidence missing '{k}'")
    if ev.get("asset") in ("stock", "etf") and not ev.get("isin"):
        reasons.append("evidence missing 'isin'")
    if ev.get("identity_resolved") is not True:
        reasons.append("company identity (parent, subsidiaries, share classes) not resolved")
    src = ev.get("sources") or {}
    for s in SOURCES:
        e = src.get(s)
        if not isinstance(e, dict):
            reasons.append(f"source '{s}' not checked")
            continue
        if e.get("finding") not in FINDINGS:
            reasons.append(f"source '{s}' has no valid finding")
        elif e["finding"] == "unreachable":
            reasons.append(f"source '{s}' was unreachable")
        if not str(e.get("url", "")).startswith("https://"):
            reasons.append(f"source '{s}' needs an https URL")
        try:
            d = dt.date.fromisoformat(e.get("checked_on", ""))
            if d > today:
                reasons.append(f"source '{s}' checked in the future ({d})")
            elif (today - d).days > MAX_EVIDENCE_AGE_DAYS:
                reasons.append(f"source '{s}' evidence is older than {MAX_EVIDENCE_AGE_DAYS} days")
        except (TypeError, ValueError):
            reasons.append(f"source '{s}' needs checked_on as YYYY-MM-DD")
    if (src.get("ohchr") or {}).get("finding") in ("match", "no_match") and not src["ohchr"].get("list_version"):
        reasons.append("OHCHR list version not recorded")
    sec = src.get("sec") or {}
    for k in ("israel_hq", "material_israel_ops"):
        if not isinstance(sec.get(k), bool):
            reasons.append(f"SEC check must state {k} as true/false")
    etf = ev.get("etf") if ev.get("asset") == "etf" else None
    if ev.get("asset") == "etf":
        keys = ("screened_weight_pct", "excluded_weight_pct", "flagged_weight_pct")
        if not isinstance(etf, dict) or any(isinstance(etf.get(k), bool) or not isinstance(etf.get(k), (int, float))
                                            for k in keys):
            reasons.append("ETF look-through weights missing")
        elif any(not math.isfinite(etf[k]) or not 0 <= etf[k] <= 100 for k in keys):
            reasons.append("ETF look-through weights must be finite percentages from 0 to 100: "
                           + ", ".join(f"{k}={etf[k]}" for k in keys))
        elif etf["screened_weight_pct"] != 100:
            reasons.append(f"only {etf['screened_weight_pct']}% of the ETF's holdings were screened")
        elif etf["excluded_weight_pct"] + etf["flagged_weight_pct"] > etf["screened_weight_pct"] + 1e-9:
            reasons.append("ETF excluded + flagged weight is more than the screened weight")
    if reasons:
        return "UNVERIFIED", reasons

    strict = strictness == "strict"
    excl_sources = LIST_SOURCES if strict else ("ohchr", "bds")
    hits = [s for s in excl_sources if src[s]["finding"] == "match"]
    soft = [] if strict else [s for s in ("afsc", "whoprofits") if src[s]["finding"] == "match"]
    if hits or sec["israel_hq"]:
        return "EXCLUDED", [f"listed by: {', '.join(hits)}" if hits else "Israel-headquartered per SEC filings"]
    if etf and etf["excluded_weight_pct"] > (0 if strict else 5):
        return "EXCLUDED", [f"{etf['excluded_weight_pct']}% of the ETF's weight is in excluded companies"]
    flags = []
    if soft:
        flags.append(f"listed only by: {', '.join(soft)}")
    if sec["material_israel_ops"]:
        flags.append("material Israeli operations per SEC filings")
    if etf and (etf["flagged_weight_pct"] > 0 or etf["excluded_weight_pct"] > 0):
        flags.append(f"ETF has {etf['excluded_weight_pct']}% excluded and {etf['flagged_weight_pct']}% flagged weight")
    if flags:
        return "FLAGGED", flags
    return "REVIEWED_NO_MATCH", ["all five sources checked; nothing found (absence from a list is not proof of no involvement)"]


def screen(ev, as_of, strictness="strict"):
    status, reasons = compute_status(ev, as_of, strictness)
    return dict(schema=SCHEMA, ticker=str(ev.get("ticker", "")).upper(), isin=ev.get("isin", ""),
                entity=ev.get("entity", ""), asset=ev.get("asset", ""), strictness=strictness,
                as_of=as_of, expires_on=(dt.date.fromisoformat(as_of) + dt.timedelta(days=RESULT_VALID_DAYS)).isoformat(),
                status=status, reasons=reasons, evidence=ev,
                ohchr_involvement=((ev.get("sources") or {}).get("ohchr") or {}).get("involvement"),
                integrity="status recomputed from the recorded evidence when used; the evidence itself is the "
                          "assistant's research record, not independent verification")


def validate_result(res, ticker, asset, isin, as_of):
    """Used by size_trade.py. Returns (status, reasons); anything off -> UNVERIFIED."""
    if res.get("schema") != SCHEMA:
        return "UNVERIFIED", ["boycott result: unknown or missing schema"]
    if str(res.get("ticker", "")).upper() != (ticker or "").upper():
        return "UNVERIFIED", [f"boycott result is for {res.get('ticker')}, not {ticker}"]
    if res.get("asset") != asset:
        return "UNVERIFIED", [f"boycott result is for asset type '{res.get('asset')}', not '{asset}'"]
    if isin and res.get("isin") and res["isin"] != isin:
        return "UNVERIFIED", [f"boycott result ISIN {res['isin']} does not match {isin}"]
    try:
        today = dt.date.fromisoformat(as_of)
        if today > dt.date.fromisoformat(res["expires_on"]):
            return "UNVERIFIED", [f"boycott result expired on {res['expires_on']}; re-screen"]
        if today < dt.date.fromisoformat(res["as_of"]):
            return "UNVERIFIED", ["boycott result is dated in the future"]
    except (KeyError, TypeError, ValueError):
        return "UNVERIFIED", ["boycott result or --as-of has no valid date"]
    ev = res.get("evidence") or {}
    if str(ev.get("ticker", "")).upper() != res["ticker"]:
        return "UNVERIFIED", ["boycott result ticker does not match its evidence"]
    status, _ = compute_status(ev, res["as_of"], res.get("strictness", "strict"))
    if status != res.get("status"):
        return "UNVERIFIED", ["boycott status does not match a recomputation from its evidence"]
    return status, []


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--as-of", required=True)
    ap.add_argument("--strictness", choices=["strict", "moderate"], default="strict")
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    try:
        with open(a.evidence) as f:
            res = screen(json.load(f), a.as_of, a.strictness)
    except Exception as e:
        res = dict(schema=SCHEMA, status="UNVERIFIED", reasons=[f"screen error: {e}"])
    text = json.dumps(res, indent=2)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
