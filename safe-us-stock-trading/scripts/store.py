#!/usr/bin/env python3
"""Keep answers and screen results between sessions (v5.3), so a run does not start from zero.

The store is a plain folder that survives the session: a folder on the user's computer, when one is
reachable. Nothing in it is trusted more than a fresh file: the engine re-checks every screen result
at trade time (expiry, ticker, ISIN, rules), so a stale or edited file still blocks the trade.

  store.py load --store DIR [--work .]     copy saved files into the work folder; print what can be reused
  store.py save --store DIR [--work .]     copy this session's files into the store

Saved: PROFILE.json (the user's setup answers), STATE_IN.json (the account as the app showed it),
JOURNAL.json, and per ticker BOYCOTT_T.json, EVIDENCE_T.json, SCREEN_T.json.
`load` reports each screen result as reusable or expired (boycott: 30 days from its date; halal: its own
expires_on). Expired files are not copied. PROFILE and STATE_IN are offered back to the user as
"same as last time?", never used silently. Prices, quotes, signals and the source ledger are never stored.
"""
import argparse, datetime as dt, glob, json, os, shutil, sys

ONCE = ("PROFILE.json", "STATE_IN.json", "JOURNAL.json")
PER_TICKER = ("BOYCOTT_*.json", "EVIDENCE_*.json", "SCREEN_*.json")
BOYCOTT_DAYS = 30


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _date(s):
    try:
        return dt.date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def status(path, today):
    """(kind, ticker, usable, note) for one screen file."""
    name = os.path.basename(path)
    kind, _, rest = name.partition("_")
    ticker = rest[:-5].upper()
    d = _load(path)
    if not isinstance(d, dict):
        return kind, ticker, False, "unreadable"
    if kind == "BOYCOTT":
        made = _date(d.get("as_of"))
        if not made or (today - made).days > BOYCOTT_DAYS or made > today:
            return kind, ticker, False, f"older than {BOYCOTT_DAYS} days: screen again"
        return kind, ticker, True, f"{d.get('status')} checked {made}, good to {made + dt.timedelta(days=BOYCOTT_DAYS)}"
    if kind == "SCREEN":
        exp = _date(d.get("expires_on"))
        if not exp or exp < today:
            return kind, ticker, False, "expired: screen again"
        return kind, ticker, True, f"{d.get('policy_decision')} good to {exp} (market cap is re-checked at trade time)"
    return kind, ticker, True, ""


def load(store, work, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    out = dict(store=store, found=os.path.isdir(store), copied=[], reusable={}, expired={})
    if not out["found"]:
        return out
    os.makedirs(work, exist_ok=True)
    for name in ONCE:
        src = os.path.join(store, name)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(work, name)); out["copied"].append(name)
    out["profile"] = _load(os.path.join(work, "PROFILE.json")) if "PROFILE.json" in out["copied"] else None
    ok_boycott = set()
    for pat in ("BOYCOTT_*.json", "SCREEN_*.json"):
        for src in sorted(glob.glob(os.path.join(store, pat))):
            kind, t, usable, note = status(src, today)
            if usable:
                shutil.copyfile(src, os.path.join(work, os.path.basename(src)))
                out["reusable"].setdefault(t, {})[kind.lower()] = note
                if kind == "BOYCOTT":
                    ok_boycott.add(t)
            else:
                out["expired"].setdefault(t, {})[kind.lower()] = note
    for src in glob.glob(os.path.join(store, "EVIDENCE_*.json")):      # evidence travels with a live result only
        if os.path.basename(src)[9:-5].upper() in ok_boycott:
            shutil.copyfile(src, os.path.join(work, os.path.basename(src)))
    return out


def save(store, work):
    os.makedirs(store, exist_ok=True)
    saved = []
    for pat in ONCE + PER_TICKER:
        for src in sorted(glob.glob(os.path.join(work, pat))):
            if _load(src) is None:
                continue
            shutil.copyfile(src, os.path.join(store, os.path.basename(src))); saved.append(os.path.basename(src))
    return dict(store=store, saved=saved)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=("load", "save"))
    ap.add_argument("--store", required=True)
    ap.add_argument("--work", default=".")
    a = ap.parse_args(argv)
    print(json.dumps(load(a.store, a.work) if a.cmd == "load" else save(a.store, a.work), indent=1))


if __name__ == "__main__":
    main()
