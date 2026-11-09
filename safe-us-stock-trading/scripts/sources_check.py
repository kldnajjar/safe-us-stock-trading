#!/usr/bin/env python3
"""Source freshness and accuracy check for the safe-us-stock-trading skill (v4.8).

Every number and claim the skill reports comes from a source ledger. This script checks each
entry against the maintainer registry (sources.json) and the SYSTEM CLOCK:

  * the source is registered, allowed for that kind of data, and the URL really is on that
    source's domain (a Yahoo URL cannot be labelled "Nasdaq")
  * it was read recently enough (observed_at) and the data itself is recent enough (published_at)
  * nothing is dated in the future
  * prices from two sources agree (within cross_check_pct), else CONFLICT
  * a scheduled release is the latest one (next_release has not already passed)
  * fundamentals come only from the SEC filing, and the EDGAR filing list was re-checked today
  * a news claim has two different sources or one tier-1 source (else a warning)

Every ledger entry must be FRESH for the check to pass: stale entries are refreshed or removed,
never reported. size_trade.py re-runs this check at sizing time (--sources-check).

Ledger JSON (--ledger FILE):
{"items": [
  {"category": "quote", "ticker": "ABC", "source": "nasdaq", "url": "https://www.nasdaq.com/...",
   "observed_at": "2026-11-05T15:30:00-05:00", "value": 100.00, "delay_min": 0, "what": "last trade"},
  {"category": "price_history", "ticker": "ABC", "source": "yahoo", "url": "https://finance.yahoo.com/...",
   "observed_at": "...", "history_through": "2026-11-05", "what": "50/200-day MA, ATR(14)"},
  {"category": "fundamentals", "ticker": "ABC", "source": "sec_edgar", "url": "https://www.sec.gov/...",
   "observed_at": "...", "published_at": "2026-10-31", "form": "10-Q", "period_end": "2026-09-27",
   "latest_filing_checked_at": "2026-11-05T14:00:00-05:00"},
  {"category": "macro_release", "source": "bls", "url": "https://www.bls.gov/...", "observed_at": "...",
   "published_at": "2026-10-15", "next_release": "2026-11-13", "what": "CPI September"},
  {"category": "news", "source": "reuters", "url": "https://www.reuters.com/...", "observed_at": "...",
   "published_at": "2026-11-05T12:10:00Z", "claim_id": "fed-hold", "what": "Fed holds rates"}
]}
Times are ISO 8601 with a UTC offset; dates (YYYY-MM-DD) are accepted for published_at,
history_through, period_end and next_release.

  python3 sources_check.py --ledger LEDGER.json [--out SOURCES_CHECK.json]
Exit code 0 only if every entry is FRESH.
"""
import argparse, datetime as dt, json, math, os, sys
from urllib.parse import urlparse

SCHEMA = "source-check/1"
HERE = os.path.dirname(os.path.abspath(__file__))
FUTURE_TOLERANCE = dt.timedelta(minutes=5)


def CLOCK():
    """The system clock (UTC). Tests replace this function; nothing on the command line can."""
    return dt.datetime.now(dt.timezone.utc)


def load_registry(path=None):
    with open(path or os.path.join(HERE, "sources.json")) as f:
        reg = json.load(f)
    validate_registry(reg)
    return reg


def validate_registry(reg):
    if reg.get("schema") != "source-registry/1":
        raise ValueError("sources.json: wrong schema")
    srcs, cats = reg.get("sources") or {}, reg.get("categories") or {}
    if not srcs or not cats:
        raise ValueError("sources.json: sources and categories are required")
    for k, s in srcs.items():
        if s.get("tier") not in (1, 2, 3) or not s.get("name") or not s.get("domains"):
            raise ValueError(f"sources.json: source '{k}' needs name, tier 1-3 and domains")
    for k, c in cats.items():
        bad = [x for x in c.get("allowed", []) if x not in srcs]
        if not c.get("allowed") or bad:
            raise ValueError(f"sources.json: category '{k}' has no or unknown allowed sources {bad}")
        if not isinstance(c.get("max_observed_age_min"), (int, float)) or c["max_observed_age_min"] <= 0:
            raise ValueError(f"sources.json: category '{k}' needs max_observed_age_min > 0")
    return True


def parse_when(s):
    """(aware datetime, date_only). Raises ValueError."""
    s = str(s or "").strip()
    if not s:
        raise ValueError("missing")
    if len(s) == 10:
        d = dt.date.fromisoformat(s)
        return dt.datetime(d.year, d.month, d.day, tzinfo=dt.timezone.utc), True
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("no UTC offset")
    return t, False


def host_matches(url, domains):
    try:
        u = urlparse(url)
    except ValueError:
        return False
    if u.scheme != "https" or not u.hostname:
        return False
    h = u.hostname.lower()
    return any(h == d or h.endswith("." + d) for d in domains)


def _age_text(td):
    m = int(td.total_seconds() // 60)
    return f"{m} min" if m < 120 else (f"{m // 60} h" if m < 2880 else f"{m // 1440} days")


def check_item(it, reg, now):
    """Returns the item annotated with status and problems."""
    out = dict(it)
    probs, status = [], "FRESH"
    cat = reg["categories"].get(it.get("category"))
    src = reg["sources"].get(it.get("source"))
    out["source_name"] = src["name"] if src else it.get("source")
    out["tier"] = src["tier"] if src else None
    if not cat:
        return dict(out, status="INVALID", problems=[f"unknown category '{it.get('category')}'"])
    if not src:
        return dict(out, status="BAD_SOURCE", problems=[f"source '{it.get('source')}' is not in the registry"])
    if it["source"] not in cat["allowed"]:
        return dict(out, status="BAD_SOURCE",
                    problems=[f"{src['name']} is not an accepted source for {it['category']} "
                              f"(accepted: {', '.join(reg['sources'][x]['name'] for x in cat['allowed'])})"])
    if not host_matches(it.get("url", ""), src["domains"]):
        return dict(out, status="BAD_SOURCE",
                    problems=[f"URL must be https on {src['name']}'s own site ({', '.join(src['domains'])})"])
    if cat.get("ticker") and not it.get("ticker"):
        probs.append("ticker is required for this category")
    for f in cat.get("requires", []):
        if it.get(f) in (None, ""):
            probs.append(f"'{f}' is required for {it['category']}")
    if probs:
        return dict(out, status="INVALID", problems=probs)

    try:
        obs, date_only_obs = parse_when(it.get("observed_at"))
    except ValueError as e:
        return dict(out, status="INVALID", problems=[f"observed_at: {e} (ISO 8601 with a UTC offset)"])
    if date_only_obs:
        return dict(out, status="INVALID", problems=["observed_at needs a time with a UTC offset, not just a date"])
    if obs > now + FUTURE_TOLERANCE:
        return dict(out, status="INVALID", problems=["observed_at is in the future"])
    limit = dt.timedelta(minutes=cat["max_observed_age_min"])
    if it["category"] == "quote":
        delay = it.get("delay_min") or 0
        if not isinstance(delay, (int, float)) or delay < 0 or delay > cat.get("max_delay_min", 20):
            return dict(out, status="INVALID", problems=[f"quote delay must be 0-{cat.get('max_delay_min', 20)} min"])
        limit += dt.timedelta(minutes=delay)
        v = it.get("value")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            return dict(out, status="INVALID", problems=["quote value must be a positive number"])
    age = now - obs
    out["observed_age"] = _age_text(max(age, dt.timedelta(0)))
    if age > limit:
        status = "STALE"
        probs.append(f"read {_age_text(age)} ago (limit {_age_text(limit)}): read it again")

    if it.get("published_at"):
        try:
            pub, date_only = parse_when(it["published_at"])
        except ValueError as e:
            return dict(out, status="INVALID", problems=[f"published_at: {e}"])
        if (pub.date() > now.date()) if date_only else (pub > now + FUTURE_TOLERANCE):
            return dict(out, status="INVALID", problems=["published_at is in the future"])
        pdays = (now.date() - pub.date()).days
        out["published_age_days"] = pdays
        if cat.get("max_published_age_days") is not None and pdays > cat["max_published_age_days"]:
            status = "STALE"
            probs.append(f"published {pdays} days ago (limit {cat['max_published_age_days']}): find the newer one")

    if it["category"] == "price_history":
        try:
            ht, _ = parse_when(it["history_through"])
            lag = (now.date() - ht.date()).days
            if lag < 0:
                return dict(out, status="INVALID", problems=["history_through is in the future"])
            if lag > cat.get("max_history_lag_days", 4):
                status = "STALE"
                probs.append(f"price history ends {ht.date()} ({lag} days ago): it must include the latest session")
        except ValueError as e:
            return dict(out, status="INVALID", problems=[f"history_through: {e}"])

    if it["category"] == "fundamentals":
        if cat.get("forms") and it.get("form") not in cat["forms"]:
            return dict(out, status="INVALID", problems=[f"form must be one of {', '.join(cat['forms'])}"])
        try:
            chk, chk_date_only = parse_when(it["latest_filing_checked_at"])
            if chk_date_only:
                return dict(out, status="INVALID", problems=["latest_filing_checked_at needs a time with a UTC offset"])
            if chk > now + FUTURE_TOLERANCE:
                return dict(out, status="INVALID", problems=["latest_filing_checked_at is in the future"])
            if now - chk > dt.timedelta(hours=cat.get("max_latest_filing_check_hours", 24)):
                status = "STALE"
                probs.append("EDGAR filing list not re-checked in the last "
                             f"{cat.get('max_latest_filing_check_hours', 24)} h: a newer 10-Q/10-K may exist")
        except ValueError as e:
            return dict(out, status="INVALID", problems=[f"latest_filing_checked_at: {e}"])

    if it["category"] == "earnings_date":
        try:
            ev, _ = parse_when(it["event_date"])
            if ev.date() < now.date():
                status = "STALE"
                probs.append(f"earnings date {ev.date()} has passed: record the next one")
        except ValueError as e:
            return dict(out, status="INVALID", problems=[f"event_date: {e}"])

    if it["category"] == "macro_release":
        try:
            nxt, _ = parse_when(it["next_release"])
            pub, _ = parse_when(it["published_at"])
            if nxt.date() <= now.date() and pub.date() < nxt.date():
                status = "STALE"
                probs.append(f"the next release was due {nxt.date()}: use the new number")
        except ValueError as e:
            return dict(out, status="INVALID", problems=[f"next_release: {e}"])

    return dict(out, status=status, problems=probs)


def check(ledger, reg=None, now=None):
    reg = reg or load_registry()
    now = now or CLOCK()
    items = ledger.get("items") if isinstance(ledger, dict) else None
    if not isinstance(items, list) or not items:
        return dict(schema=SCHEMA, checked_at=now.isoformat(timespec="seconds"), ok=False, items=[],
                    blocking=["ledger has no items: every reported number needs a source entry"],
                    warnings=[], tickers={}, market={}, ledger=ledger)
    res = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            res.append(dict(id=f"item{i + 1}", status="INVALID", problems=["entry is not an object"]))
            continue
        r = check_item(it, reg, now)
        r.setdefault("id", it.get("id") or f"{it.get('ticker') or it.get('category')}-{i + 1}")
        res.append(r)
    warnings = []

    # price cross-check per ticker
    cat_q = reg["categories"]["quote"]
    by_t = {}
    for r in res:
        if r.get("category") == "quote" and r["status"] == "FRESH":
            by_t.setdefault(str(r.get("ticker", "")).upper(), []).append(r)
    for t, qs in by_t.items():
        if len({q["source"] for q in qs}) < cat_q.get("preferred_sources", 2):
            warnings.append(f"{t}: price from one source only ({qs[0]['source_name']}); a second source "
                            "(exchange site + Yahoo/Stooq) makes it more reliable")
        vals = [q["value"] for q in qs]
        spread = 100 * (max(vals) / min(vals) - 1)
        if spread > cat_q.get("cross_check_pct", 0.5):
            for q in qs:
                q["status"] = "CONFLICT"
                q["problems"] = q.get("problems", []) + [
                    f"price sources disagree by {spread:.2f}% (limit {cat_q.get('cross_check_pct', 0.5)}%): "
                    "re-read both, trust the exchange (tier 1)"]

    # news corroboration
    claims = {}
    for r in res:
        if r.get("category") == "news" and r["status"] == "FRESH":
            claims.setdefault(r["claim_id"], []).append(r)
    for cid, rs in claims.items():
        if len({x["source"] for x in rs}) < 2 and not any(x["tier"] == 1 for x in rs):
            warnings.append(f"news '{cid}': one source only ({rs[0]['source_name']}); confirm it with a second "
                            "outlet or the official release before relying on it")

    blocking = [f"{r['id']} ({r.get('source_name')}, {r.get('category')}): {r['status']}: "
                + "; ".join(r.get("problems") or []) for r in res if r["status"] != "FRESH"]
    try:
        reg_age = (now.date() - dt.date.fromisoformat(reg["verified_on"])).days
        if reg_age < 0:
            blocking.append(f"source registry verified_on {reg['verified_on']} is in the future: fix sources.json")
        elif reg_age > reg.get("max_age_days", 180):
            blocking.append(f"source registry sources.json last verified {reg_age} days ago (limit "
                            f"{reg.get('max_age_days', 180)}): a maintainer re-checks it and re-runs run_checks.py")
    except (KeyError, TypeError, ValueError):
        blocking.append("source registry has no valid verified_on date")
    tickers, market = {}, {}
    for r in res:
        if r["status"] != "FRESH":
            continue
        if reg["categories"].get(r["category"], {}).get("ticker"):
            d = tickers.setdefault(str(r["ticker"]).upper(), {})
            d[r["category"]] = d.get(r["category"], 0) + 1
        else:
            market[r["category"]] = market.get(r["category"], 0) + 1
    return dict(schema=SCHEMA, checked_at=now.isoformat(timespec="seconds"), registry_verified_on=reg.get("verified_on"),
                ok=not blocking, items=res, blocking=blocking, warnings=warnings, tickers=tickers, market=market,
                ledger=ledger)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args(argv)
    try:
        with open(a.ledger) as f:
            ledger = json.load(f)
        out = check(ledger)
    except Exception as e:
        out = dict(schema=SCHEMA, ok=False, blocking=[f"source check error: {e}"], items=[], warnings=[])
    text = json.dumps(out, indent=2)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
    print(text)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
