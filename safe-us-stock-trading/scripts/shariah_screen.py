#!/usr/bin/env python3
"""Shariah screen for the safe-us-stock-trading skill (v4.3).

Rules come ONLY from methodologies.json (versioned, sourced, dated). This file
contains no thresholds. A methodology that is disabled, stale, or whose source
version no longer matches returns INSUFFICIENT_DATA / UNVERIFIED.

A screen against a published methodology, not a fatwa. Four outcomes are reported
separately:
  screening_result   PASS | FAIL | BORDERLINE | INSUFFICIENT_DATA   (business + core thresholds)
  index_entry        ELIGIBLE | INELIGIBLE | UNKNOWN | NOT_APPLICABLE
  retention          RETAINED | REMOVAL_CONDITION_MET | UNKNOWN | NOT_APPLICABLE
  policy_decision    PERMITTED | REQUIRES_ACCEPTANCE | EXCLUDED | UNVERIFIED
policy_decision is what size_trade.py consumes (--shariah-policy). An index-entry
failure alone is never treated as a religious prohibition: it makes the decision
REQUIRES_ACCEPTANCE, not EXCLUDED.

Stock inputs ($ unless noted; collect each separately from the filing):
  --interest-debt     interest-bearing borrowings      --total-debt          total debt as the provider defines it
  --cash              cash and non-interest deposits   --interest-deposits   interest-bearing deposits
  --interest-securities interest-bearing securities    --receivables         accounts receivable
  --market-cap  --total-assets  --avg-market-cap-24m  --avg-market-cap-36m
  --nonpermissible-income  --total-income             (same reporting period)
  --period FY2025  --data-published YYYY-MM-DD        (provenance; required)
  --market-cap-date YYYY-MM-DD   REQUIRED when any ratio uses market cap (AAOIFI, MSCI M-Series, S&P, DJIM):
                                 the observation date of the market-cap figure (end of the averaging window
                                 for averages); at most 31 days old when screened AND when traded.

Certificates (etf-certified, and metals for PERMITTED): --certifier, --certificate-date (<= --as-of and at
most 400 days old), and --certificate-url (https link to the certificate or fund page that states it).
"""
import argparse, math, datetime as dt, hashlib, json, operator, os

HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY = os.path.join(HERE, "methodologies.json")
OPS = {"<": operator.lt, "<=": operator.le}
RESULT_SCHEMA = "shariah-result/2"
COMPARED = ("screening_result", "index_entry", "retention", "policy_decision", "purification")
NOT_RECORDED = ("out", "registry")
RESULT_VALID_DAYS = 92
MAX_FILING_AGE_DAYS = 550     # ~18 months: older financials are stale for screening
MAX_MCAP_AGE_DAYS = 31
MAX_CERT_AGE_DAYS = 400       # Shariah certificates are normally renewed annually; allow a short grace period
MCAP_DENOMS = {"market_cap", "avg_market_cap_24m", "avg_market_cap_36m"}
DENOMS = {"market_cap", "total_assets", "avg_market_cap_24m", "avg_market_cap_36m", "total_income"}
INPUT_FIELDS = ["interest_debt", "total_debt", "cash", "interest_deposits", "interest_securities", "receivables",
                "market_cap", "total_assets", "avg_market_cap_24m", "avg_market_cap_36m",
                "nonpermissible_income", "total_income"]


def validate_registry(reg):
    """Schema check. Any problem raises ValueError, which the screen reports as UNVERIFIED."""
    if not isinstance(reg.get("methodologies"), dict) or not reg["methodologies"]:
        raise ValueError("registry: 'methodologies' missing")
    if not isinstance(reg.get("max_age_days"), int):
        raise ValueError("registry: 'max_age_days' must be an integer")
    for mid, m in reg["methodologies"].items():
        vs = m.get("versions") or []
        if sum(1 for v in vs if v.get("current")) != 1:
            raise ValueError(f"registry: {mid} must have exactly one current version")
        for v in vs:
            for key in ("document_version", "provider", "source", "verified_on", "ratios", "income",
                        "purification", "enabled", "is_index"):
                if key not in v:
                    raise ValueError(f"registry: {mid} '{v.get('document_version')}' missing '{key}'")
            if not str(v["source"]).startswith("https://"):
                raise ValueError(f"registry: {mid} source must be an https URL")
            dt.date.fromisoformat(v["verified_on"])
            if v["purification"].get("method") not in ("attributable", "dividend"):
                raise ValueError(f"registry: {mid} unknown purification method")
            for r in v["ratios"] + [dict(v["income"], name="income")]:
                if r.get("comparator") not in OPS:
                    raise ValueError(f"registry: {mid} {r.get('name')} bad comparator")
                for k in ("threshold", "entry", "exit_buffer"):
                    x = r.get(k)
                    if x is not None and not (0 < x < 1):
                        raise ValueError(f"registry: {mid} {r.get('name')} {k} out of range")
                nums = r["numerator"] if isinstance(r["numerator"], list) else [r["numerator"]]
                for f in nums + [r["denominator"]]:
                    if f not in INPUT_FIELDS:
                        raise ValueError(f"registry: {mid} uses unknown field '{f}'")
                if r["denominator"] not in DENOMS:
                    raise ValueError(f"registry: {mid} {r.get('name')} denominator '{r['denominator']}' not allowed")
            if v.get("buffer_rule") not in (None, "msci_exit_buffer_average", "two_point_three_periods"):
                raise ValueError(f"registry: {mid} unknown buffer rule")
    return reg


def load_registry(path=REGISTRY):
    with open(path) as f:
        return validate_registry(json.load(f))


def fingerprint(v):
    """SHA-256 of the rule content of one registry entry (ties a result to the exact rules used)."""
    keys = ("document_version", "provider", "effective_date", "source", "ratios", "income",
            "buffer_rule", "buffer_pp", "is_index", "purification")
    return hashlib.sha256(json.dumps({k: v.get(k) for k in keys}, sort_keys=True).encode()).hexdigest()


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", choices=["stock", "etf-certified", "metal", "tbill"], required=True)
    ap.add_argument("--methodology", default="aaoifi")
    ap.add_argument("--version", default="", help="document_version to use; default is the current one")
    ap.add_argument("--as-of", default="", help="today's date YYYY-MM-DD (required for stocks)")
    ap.add_argument("--source-version-seen", default="",
                    help="document version found on the provider's site this session; mismatch -> UNVERIFIED")
    ap.add_argument("--registry", default=REGISTRY)
    ap.add_argument("--ticker", default="")
    ap.add_argument("--isin", default="")
    ap.add_argument("--entity", default="", help="legal entity name as in the filing")
    ap.add_argument("--out", default="", help="write the result (with provenance) to this JSON file")
    ap.add_argument("--business", choices=["permissible", "mixed", "prohibited"])
    ap.add_argument("--auto-inputs", action="store_true",
                    help="v5.3: the numbers were mapped by a script from SEC data tags, not read from the filing; "
                         "a pass then needs the user's acceptance")
    ap.add_argument("--provider", help="v5.3 quick screen: a screening provider whose verdict the USER looked up and reported (musaffa)")
    ap.add_argument("--provider-verdict", choices=["halal", "not_halal", "doubtful"])
    ap.add_argument("--needs-confirmation", action="store_true",
                    help="v5.3: a fund-list result is only a shortlist; it needs the user's own check on the screening provider")
    ap.add_argument("--provider-date", help="date of the provider's review, YYYY-MM-DD")
    ap.add_argument("--provider-url", help="https page on the provider's site showing the verdict")
    ap.add_argument("--provider-methodology", help="the methodology the provider states, e.g. AAOIFI")
    ap.add_argument("--existing-holding", action="store_true")
    ap.add_argument("--previous-index-status", choices=["compliant", "noncompliant", "unknown"], default="unknown")
    ap.add_argument("--consecutive-periods", type=int, default=0,
                    help="consecutive evaluation periods in the current state (breaches if compliant, passes if not)")
    for f in INPUT_FIELDS:
        ap.add_argument(f"--{f.replace('_', '-')}", type=float)
    ap.add_argument("--period", default="")
    ap.add_argument("--data-published", default="")
    ap.add_argument("--market-cap-date", default="",
                    help="observation date of the market-cap figures; required when a ratio uses market cap")
    ap.add_argument("--internal-margin", type=float, default=0.10,
                    help="INTERNAL conservative policy, not a methodology rule: within this fraction of a limit -> requires acceptance")
    # purification
    ap.add_argument("--shares-outstanding", type=float)
    ap.add_argument("--shares-held", type=float)
    ap.add_argument("--held-at-period-end", choices=["yes", "no"])
    ap.add_argument("--dividend-per-share", type=float)
    ap.add_argument("--dividends-count", type=int, default=1)
    ap.add_argument("--fund-purifies", choices=["yes", "no", "unknown"], default="unknown")
    # metals
    ap.add_argument("--metal-structure", choices=["physical", "futures", "leveraged"])
    for f in ("allocated", "ownership-rights", "spot-settlement", "no-lending"):
        ap.add_argument(f"--{f}", choices=["yes", "no", "unknown"], default="unknown")
    ap.add_argument("--certifier", default="")
    ap.add_argument("--certificate-date", default="")
    ap.add_argument("--certificate-url", default="", help="https link to the certificate or the fund page stating it")
    return ap


def certificate_problem(a, as_of=None):
    """None if the certificate is complete, dated, current and sourced; else the reason it is not."""
    if not (a.certifier and a.certificate_date):
        return "certifying board and certificate date are required"
    try:
        cd = dt.date.fromisoformat(a.certificate_date)
    except ValueError:
        return "--certificate-date must be YYYY-MM-DD"
    try:
        today = dt.date.fromisoformat(as_of or a.as_of)
    except (TypeError, ValueError):
        return "--as-of is required to check the certificate is current"
    if cd > today:
        return f"certificate date {cd} is after {today}"
    if (today - cd).days > MAX_CERT_AGE_DAYS:
        return f"certificate from {cd} is older than {MAX_CERT_AGE_DAYS} days; get the current certificate"
    if not str(a.certificate_url).startswith("https://"):
        return "--certificate-url (https) is required as evidence of the certificate"
    return None


PROVIDERS = {"musaffa": ("Musaffa", "musaffa.com"),     # a verdict the USER looks up (their terms forbid scripts)
             "spus": ("SP Funds SPUS holdings", "sp-funds.com")}   # the fund's published holdings file (lists.py)
FUND_LISTS = ("spus",)                                  # "held by a certified Shariah fund": only ever a halal verdict
MAX_PROVIDER_AGE_DAYS = 120                              # a provider's review older than this: screen again
PROVIDER_VERDICT = {"halal": "PASS", "not_halal": "FAIL", "doubtful": "BORDERLINE"}


def provider_problem(a, as_of=None):
    """None if a screening provider's verdict is complete, sourced and current; else the reason it is not."""
    if a.provider not in PROVIDERS:
        return f"--provider must be one of: {', '.join(PROVIDERS)}"
    name, domain = PROVIDERS[a.provider]
    if a.provider_verdict not in PROVIDER_VERDICT:
        return "--provider-verdict must be halal, not_halal or doubtful"
    host = str(a.provider_url or "").partition("https://")[2].partition("/")[0].lower()
    if not (host == domain or host.endswith("." + domain)):
        return f"--provider-url must be an https page on {domain}"
    want = {"aaoifi": "aaoifi", "msci": "msci", "msci-m": "msci", "sp": "s&p", "djim": "dow jones"}.get(a.methodology or "", "")
    if not a.provider_methodology or (want and want not in str(a.provider_methodology).lower()):
        return f"{name}'s stated methodology ({a.provider_methodology or 'not given'}) is not the chosen one ({a.methodology})"
    try:
        made = dt.date.fromisoformat(a.provider_date)
        today = dt.date.fromisoformat(as_of or a.as_of)
    except (TypeError, ValueError):
        return "--provider-date and --as-of must be YYYY-MM-DD"
    if made > today:
        return f"provider review date {made} is after {today}"
    if (today - made).days > MAX_PROVIDER_AGE_DAYS:
        return f"{name}'s review ({made}) is older than {MAX_PROVIDER_AGE_DAYS} days"
    return None


def screen_provider(a):
    """v5.3 quick screen: copy one named provider's published verdict. Nothing is computed here."""
    head = dict(basis="provider", methodology_id=a.methodology, provider=PROVIDERS.get(a.provider, (a.provider,))[0],
                methodology=f"{PROVIDERS.get(a.provider, (a.provider,))[0]}: {a.provider_methodology}",
                source=a.provider_url, period=f"provider review dated {a.provider_date}",
                data_published=a.provider_date, source_rechecked_this_session=True)
    if not (a.ticker and a.entity and (a.isin or a.asset == "metal")):
        return out("INSUFFICIENT_DATA", ["--ticker, --isin and --entity are required (identity provenance)"], **head)
    why = provider_problem(a)
    if why:
        return out("INSUFFICIENT_DATA", [f"provider verdict: {why}"], **head)
    if a.provider in FUND_LISTS:
        if a.provider_verdict != "halal":
            return out("INSUFFICIENT_DATA", ["a fund's holdings list can only say a stock is held (halal by the fund's screen)"], **head)
        if getattr(a, "needs_confirmation", False):
            res = out("BORDERLINE", [f"held by a certified Shariah fund ({head['provider']}, file dated {a.provider_date}), "
                                     "not yet confirmed on Musaffa: look it up and report what it says"], **head)
            res["note"] = ("shortlist only: the fund holds it, but the user's chosen authority is Musaffa and the user has not "
                           "reported its verdict yet. Not a fatwa")
            return res
        res = out("PASS", [f"held by a certified Shariah fund ({head['provider']}, file dated {a.provider_date}): {a.provider_url}"], **head)
        res["note"] = ("list screen: the stock is in the fund's published holdings, so it passed that fund's Shariah screen "
                       "on that date. Other screeners can disagree. This skill computed no ratios. Not a fatwa")
        return res
    word = a.provider_verdict.replace("_", " ").upper()
    res = out(PROVIDER_VERDICT[a.provider_verdict],
              [f"{head['provider']} lists it as {word} under {a.provider_methodology} (reviewed {a.provider_date}): {a.provider_url}"],
              **head)
    res["note"] = ("quick screen: one screening provider's verdict, as the user looked it up and reported it; "
                   "this skill did not read the provider's site or compute the ratios. Not a fatwa")
    return res


def mcap_date_problem(mcap_date, as_of):
    try:
        md = dt.date.fromisoformat(mcap_date)
        today = dt.date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return "--market-cap-date (YYYY-MM-DD) is required for market-cap ratios"
    if md > today:
        return f"market-cap date {md} is after {today}"
    if (today - md).days > MAX_MCAP_AGE_DAYS:
        return f"market-cap date {md} is older than {MAX_MCAP_AGE_DAYS} days; refresh the market cap"
    return None


def decision(screening, index_entry="NOT_APPLICABLE", flags=()):
    if screening == "FAIL":
        return "EXCLUDED"
    if screening == "INSUFFICIENT_DATA":
        return "UNVERIFIED"
    if screening == "BORDERLINE" or index_entry in ("INELIGIBLE", "UNKNOWN") or flags:
        return "REQUIRES_ACCEPTANCE"
    return "PERMITTED"


def out(screening, reasons, index_entry="NOT_APPLICABLE", retention="NOT_APPLICABLE", flags=(), **extra):
    return dict(screening_result=screening, index_entry=index_entry, retention=retention,
                policy_decision=decision(screening, index_entry, flags), reasons=reasons,
                internal_policy_flags=list(flags), **extra,
                note="methodology-based screen, not a fatwa")


def pick_version(reg, a):
    m = reg["methodologies"].get(a.methodology)
    if not m:
        return None, f"unknown methodology '{a.methodology}'"
    vs = m["versions"]
    v = next((x for x in vs if x["document_version"] == a.version), None) if a.version else \
        next((x for x in vs if x.get("current")), None)
    if v is None:
        return None, "requested methodology version not in registry"
    if not v.get("enabled"):
        return None, f"{v['document_version']} is disabled pending review"
    accepted = [v["document_version"]] + list(v.get("equivalent_versions", []))
    if a.source_version_seen and a.source_version_seen not in accepted and not a.version:
        return None, (f"provider now publishes '{a.source_version_seen}' but the registry has "
                      f"'{v['document_version']}': methodology disabled until the registry is reviewed and tested")
    if not a.as_of:
        return None, "--as-of date is required to check the registry is current"
    age = (dt.date.fromisoformat(a.as_of) - dt.date.fromisoformat(v["verified_on"])).days
    if age > reg.get("max_age_days", 120) and not v.get("historical_only"):
        return None, f"registry entry last verified {age} days ago; re-verify against the source"
    return v, None


def cents_up(x):
    """Charity owed is rounded UP to the cent, never down (tolerates float noise like 2.2500000001)."""
    return math.ceil(round(x * 100, 6)) / 100


def purification(a, v):
    meth = v["purification"]["method"]
    if a.fund_purifies == "yes":
        return dict(status="NOT DUE", amount_usd=0.0, note="the fund purifies at fund level; do not purify again")
    if meth == "attributable":
        need = dict(period=a.period or None, nonpermissible_income=a.nonpermissible_income,
                    shares_outstanding=a.shares_outstanding, shares_held=a.shares_held,
                    held_at_period_end=a.held_at_period_end)
        missing = [k for k, x in need.items() if x is None]
        base = dict(method=f"AAOIFI SS-21 attributable income (clauses {v['purification']['clauses']})")
        if missing:
            return dict(base, status="UNAVAILABLE", missing=missing)
        if a.held_at_period_end == "no":
            return dict(base, status="NOT DUE", amount_usd=0.0, period=a.period,
                        note="sold before the end of the financial period (3/4/6/1)")
        per_share = a.nonpermissible_income / a.shares_outstanding
        return dict(base, status="DUE", period=a.period, per_share_usd=round(per_share, 6),
                    amount_usd=cents_up(per_share * a.shares_held),
                    note="due whether or not profits were distributed (3/4/6/2)")
    need = dict(period=a.period or None, nonpermissible_income=a.nonpermissible_income,
                total_income=a.total_income, dividend_per_share=a.dividend_per_share, shares_held=a.shares_held)
    missing = [k for k, x in need.items() if x is None]
    base = dict(method=f"dividend x non-permissible income / total income ({v['provider']})")
    if missing:
        return dict(base, status="UNAVAILABLE", missing=missing)
    ratio = a.nonpermissible_income / a.total_income
    return dict(base, status="DUE", period=a.period,
                amount_usd=cents_up(a.dividend_per_share * a.dividends_count * a.shares_held * ratio))


def screen_stock(a, reg):
    v, err = pick_version(reg, a)
    if err:
        return out("INSUFFICIENT_DATA", [err])
    head = dict(methodology_id=a.methodology, methodology=v["document_version"], provider=v["provider"],
                source=v["source"], effective_date=v.get("effective_date"), rule_fingerprint=fingerprint(v),
                source_rechecked_this_session=bool(a.source_version_seen),
                test_basis="existing holding" if a.existing_holding else "new purchase")
    if not (a.ticker and a.isin and a.entity):
        return out("INSUFFICIENT_DATA", ["--ticker, --isin and --entity are required (identity provenance)"], **head)
    if a.business is None:
        return out("INSUFFICIENT_DATA", ["core business not classified"], **head)
    if a.business == "prohibited":
        return out("FAIL", ["core business is prohibited"], **head)
    if not a.period or not a.data_published:
        return out("INSUFFICIENT_DATA", ["--period and --data-published are required (data provenance)"], **head)

    try:
        today = dt.date.fromisoformat(a.as_of)
        pub = dt.date.fromisoformat(a.data_published)
    except ValueError:
        return out("INSUFFICIENT_DATA", ["--as-of and --data-published must be YYYY-MM-DD"], **head)
    if pub > today:
        return out("INSUFFICIENT_DATA", [f"filing date {pub} is after --as-of {today}"], **head)
    if (today - pub).days > MAX_FILING_AGE_DAYS:
        return out("INSUFFICIENT_DATA", [f"filing from {pub} is older than {MAX_FILING_AGE_DAYS} days; use the latest filing"], **head)
    uses_mcap = any(r["denominator"] in MCAP_DENOMS for r in v["ratios"])
    head["uses_market_cap"] = uses_mcap
    if uses_mcap or a.market_cap_date:
        why = mcap_date_problem(a.market_cap_date, a.as_of)
        if why:
            return out("INSUFFICIENT_DATA", [why], **head)
    bad = [f for f in INPUT_FIELDS if getattr(a, f) is not None
           and (not isinstance(getattr(a, f), (int, float)) or not (getattr(a, f) == getattr(a, f))
                or getattr(a, f) in (float("inf"), float("-inf")) or getattr(a, f) < 0)]
    if bad:
        return out("INSUFFICIENT_DATA", [f"financial inputs must be finite and zero or more: {', '.join(bad)}"], **head)
    for f in ("shares_outstanding", "shares_held", "dividend_per_share"):
        x = getattr(a, f)
        if x is not None and (x < 0 or x != x):
            return out("INSUFFICIENT_DATA", [f"--{f.replace('_', '-')} must be zero or more"], **head)
    if a.shares_outstanding is not None and a.shares_outstanding <= 0:
        return out("INSUFFICIENT_DATA", ["--shares-outstanding must be positive"], **head)
    vals = {f: getattr(a, f) for f in INPUT_FIELDS}
    needed = set()
    for r in v["ratios"]:
        needed.update(r["numerator"])
        needed.add(r["denominator"])
    needed.update([v["income"]["numerator"], v["income"]["denominator"]])
    missing = sorted(f for f in needed if vals[f] is None)
    zero = sorted(f for f in needed if vals[f] == 0 and f in ("market_cap", "total_assets", "avg_market_cap_24m",
                                                                "avg_market_cap_36m", "total_income"))
    if missing or zero:
        return out("INSUFFICIENT_DATA", [f"missing data: {', '.join(missing + zero)}"], **head)

    rule = v.get("buffer_rule")
    pp = v.get("buffer_pp", 0.0)
    ratios, results, entries, retentions, flags, reasons = {}, [], [], [], [], []

    def check(name, val, comp, thr, entry=None, exit_buf=None, buffered=True):
        op = OPS[comp]
        passes_thr = op(val, thr)
        row = dict(value_pct=round(100 * val, 3), comparator=comp, threshold_pct=round(100 * thr, 2),
                   entry_pct=None if entry is None else round(100 * entry, 2),
                   exit_buffer_pct=None if exit_buf is None else round(100 * exit_buf, 2))
        res, ent, ret = ("PASS" if passes_thr else "FAIL"), "NOT_APPLICABLE", "NOT_APPLICABLE"

        if v.get("is_index") and not buffered:
            ent = "ELIGIBLE" if passes_thr else "INELIGIBLE"
            ret = "RETAINED" if passes_thr else "REMOVAL_CONDITION_MET"
        if v.get("is_index") and buffered:
            ent = "ELIGIBLE" if op(val, entry if entry is not None else thr) else "INELIGIBLE"
            ret = "RETAINED" if passes_thr else "REMOVAL_CONDITION_MET"

            if rule == "msci_exit_buffer_average" and exit_buf is not None and not passes_thr and val <= exit_buf:
                res, ret = "BORDERLINE", "UNKNOWN"
                reasons.append(f"{name}: between threshold and exit buffer; MSCI applies a four-period average test")

            if rule == "two_point_three_periods":
                in_upper = (not passes_thr) and val <= thr + pp
                in_lower = passes_thr and val >= thr - pp
                prev = a.previous_index_status
                if in_upper:
                    if prev == "compliant":
                        if a.consecutive_periods >= 3:
                            res, ret = "FAIL", "REMOVAL_CONDITION_MET"
                        else:
                            res, ret = "BORDERLINE", "RETAINED"
                            reasons.append(f"{name}: within the 2-point buffer above the limit "
                                           f"({a.consecutive_periods} of 3 consecutive breaches)")
                    elif prev == "unknown":
                        res, ret = "BORDERLINE", "UNKNOWN"
                        reasons.append(f"{name}: inside the 2-point buffer; previous index status unknown")
                    ent = "INELIGIBLE"
                elif in_lower:
                    if prev == "noncompliant" and a.consecutive_periods < 3:
                        ent = "INELIGIBLE"
                        reasons.append(f"{name}: previously non-compliant and within 2 points of the limit "
                                       f"({a.consecutive_periods} of 3 consecutive passes)")
                    elif prev == "unknown":
                        ent = "UNKNOWN"
        # internal conservative margin (not a methodology rule)
        if res == "PASS" and a.internal_margin > 0 and val > thr * (1 - a.internal_margin):
            flags.append(f"{name} within {int(a.internal_margin * 100)}% of its limit (internal policy)")
        row.update(result=res, index_entry=ent, retention=ret)
        ratios[name] = row
        results.append(res)
        entries.append(ent)
        retentions.append(ret)

    for r in v["ratios"]:
        num = sum(vals[f] for f in r["numerator"])
        check(r["name"], num / vals[r["denominator"]], r["comparator"], r["threshold"], r.get("entry"), r.get("exit_buffer"))
    inc = v["income"]
    check("nonpermissible_income", vals[inc["numerator"]] / vals[inc["denominator"]], inc["comparator"], inc["threshold"],
          buffered=False)

    if a.business == "mixed":
        results.append("BORDERLINE")
        reasons.append("business has a material line that needs scholar judgement")

    screening = "FAIL" if "FAIL" in results else ("BORDERLINE" if "BORDERLINE" in results else "PASS")
    if screening == "FAIL":
        reasons.insert(0, "over the limit: " + ", ".join(k for k, x in ratios.items() if x["result"] == "FAIL"))
    if v.get("is_index"):
        index_entry = "INELIGIBLE" if "INELIGIBLE" in entries else ("UNKNOWN" if "UNKNOWN" in entries else "ELIGIBLE")
        retention = ("REMOVAL_CONDITION_MET" if "REMOVAL_CONDITION_MET" in retentions else
                     "UNKNOWN" if "UNKNOWN" in retentions else "RETAINED") if a.existing_holding else "NOT_APPLICABLE"
        if a.existing_holding:
            index_entry = "NOT_APPLICABLE"
    else:
        index_entry = retention = "NOT_APPLICABLE"
    if screening == "PASS" and index_entry == "INELIGIBLE":
        reasons.append("passes the methodology's limits but the index would not admit it now; "
                       "this is not a religious prohibition")

    if getattr(a, "auto_inputs", False):
        flags.append("numbers mapped by a script from SEC data tags, not read from the filing: first pass only")
    return out(screening, reasons, index_entry, retention, flags, **head,
               data=dict(period=a.period, data_published=a.data_published, market_cap_date=a.market_cap_date or None),
               ratios=ratios, purification=purification(a, v))


def screen(a, reg=None):
    res = _screen(a, reg)
    as_of = a.as_of or None
    expires = (dt.date.fromisoformat(a.as_of) + dt.timedelta(days=RESULT_VALID_DAYS)).isoformat() if a.as_of else None
    res.update(schema=RESULT_SCHEMA, ticker=a.ticker.upper(), isin=a.isin, entity=a.entity, asset=a.asset,
               as_of=as_of, expires_on=expires,
               inputs={k: v for k, v in vars(a).items() if k not in NOT_RECORDED},
               integrity="consistency check: the verdict is recomputed from these recorded inputs when used; "
                         "this does not prove the inputs themselves were not changed")
    return res


def recompute(res, registry_path=REGISTRY):
    """Re-run the screen from the recorded inputs; returns the fields that differ (empty list = consistent)."""
    inp = res.get("inputs")
    if not isinstance(inp, dict) or "asset" not in inp:
        return ["recorded inputs missing"]
    a = build_parser().parse_args(["--asset", inp["asset"]])
    for k, v in inp.items():
        if hasattr(a, k):
            setattr(a, k, v)
    a.registry = registry_path
    fresh = _screen(a, None if a.asset != "stock" else load_registry(registry_path))
    return [k for k in COMPARED if fresh.get(k) != res.get(k)]


def validate_result(res, ticker, as_of, registry_path=REGISTRY, expected_asset=None, isin=""):
    """Used by size_trade.py. Returns (policy_decision, reasons). Anything off -> UNVERIFIED.
    expected_asset: the result's asset type the trade needs (stock -> 'stock', etf -> 'etf-certified', ...)."""
    reasons = []
    if res.get("schema") != RESULT_SCHEMA:
        return "UNVERIFIED", ["Shariah result: unknown or missing schema"]
    for k in ("ticker", "asset", "policy_decision", "as_of", "expires_on"):
        if not res.get(k):
            reasons.append(f"Shariah result: missing '{k}'")
    if reasons:
        return "UNVERIFIED", reasons
    if res["ticker"].upper() != (ticker or "").upper():
        return "UNVERIFIED", [f"Shariah result is for {res['ticker']}, not {ticker}"]
    if expected_asset and res.get("asset") != expected_asset:
        return "UNVERIFIED", [f"Shariah result is for asset type '{res.get('asset')}', but this trade needs '{expected_asset}'"]
    if isin and res.get("isin") and res["isin"] != isin:
        return "UNVERIFIED", [f"Shariah result ISIN {res['isin']} does not match {isin}"]
    if expected_asset == "stock" and isin and not res.get("isin"):
        return "UNVERIFIED", ["Shariah result has no ISIN to match against this security"]
    if str((res.get("inputs") or {}).get("ticker", "")).upper() != res["ticker"].upper():
        return "UNVERIFIED", ["Shariah result ticker does not match its recorded inputs"]
    try:
        today = dt.date.fromisoformat(as_of)
    except (TypeError, ValueError):
        return "UNVERIFIED", ["--as-of date is required to check the Shariah result"]
    try:
        made = dt.date.fromisoformat(res["as_of"])
    except (TypeError, ValueError):
        return "UNVERIFIED", ["Shariah result has no valid as_of date"]
    if str((res.get("inputs") or {}).get("as_of", "")) != res["as_of"]:
        return "UNVERIFIED", ["Shariah result date does not match its recorded inputs"]
    expires = made + dt.timedelta(days=RESULT_VALID_DAYS)      # recomputed: the stored expires_on is not trusted
    if today > expires:
        return "UNVERIFIED", [f"Shariah result expired on {expires.isoformat()}; re-screen"]
    if today < dt.date.fromisoformat(res["as_of"]):
        return "UNVERIFIED", ["Shariah result is dated in the future"]
    if res.get("basis") == "provider":
        inp0 = res.get("inputs") or {}
        if not res.get("entity") or not (res.get("isin") or res["asset"] == "metal"):
            return "UNVERIFIED", ["Shariah result: missing provenance (isin, entity)"]
        why = provider_problem(argparse.Namespace(**{k: inp0.get(k) for k in (
            "provider", "provider_verdict", "provider_url", "provider_date", "provider_methodology", "methodology", "as_of")}), as_of)
        if why:
            return "UNVERIFIED", [f"Shariah result at trade time: provider verdict: {why}"]
    elif res["asset"] == "stock":
        try:
            reg = load_registry(registry_path)
            vs = reg["methodologies"][res["methodology_id"]]["versions"]
            v = next(x for x in vs if x["document_version"] == res["methodology"])
        except Exception as e:
            return "UNVERIFIED", [f"Shariah result: methodology not found in registry ({e})"]
        if fingerprint(v) != res.get("rule_fingerprint"):
            return "UNVERIFIED", ["Shariah result was produced under different rules (fingerprint mismatch); re-screen"]
        if not v.get("enabled"):
            return "UNVERIFIED", ["Shariah result methodology is now disabled"]
        if v.get("historical_only"):
            return "UNVERIFIED", ["Shariah result used a historical methodology version; not valid for decisions"]
        for k in ("isin", "entity", "period"):
            if not (res.get(k) or res.get("data", {}).get(k)):
                return "UNVERIFIED", [f"Shariah result: missing provenance '{k}'"]
    inp = res.get("inputs") or {}
    if res["asset"] == "stock" and (res.get("uses_market_cap") or inp.get("market_cap_date")):
        why = mcap_date_problem(inp.get("market_cap_date"), as_of)
        if why:
            return "UNVERIFIED", [f"Shariah result at trade time: {why}; re-screen with a fresh market cap"]
    if res.get("basis") != "provider" and (res["asset"] == "etf-certified" or (res["asset"] == "metal" and inp.get("certifier"))):
        why = certificate_problem(argparse.Namespace(**{k: inp.get(k, "") for k in
                                                        ("certifier", "certificate_date", "certificate_url", "as_of")}),
                                  as_of)
        if why:
            return "UNVERIFIED", [f"Shariah result at trade time: certificate: {why}"]
    try:
        diff = recompute(res, registry_path)
    except Exception as e:
        return "UNVERIFIED", [f"Shariah result could not be recomputed: {e}"]
    if diff:
        return "UNVERIFIED", [f"Shariah result does not match a recomputation from its inputs ({', '.join(diff)})"]
    return res["policy_decision"], []


def _screen(a, reg=None):
    if a.asset in ("stock", "etf-certified", "metal") and (getattr(a, "provider", None) or getattr(a, "provider_verdict", None)):
        return screen_provider(a)                    # v5.3: a provider's verdict, for stocks, funds and metal trusts
    if a.asset == "tbill":
        return out("FAIL", ["T-bill / Treasury ETFs pay interest (riba)"],
                   alternative="cash, or a Shariah-certified sukuk fund (verify availability and screen it)")
    if a.asset == "metal":
        if a.metal_structure is None:
            return out("INSUFFICIENT_DATA", ["fund structure unknown"])
        if a.metal_structure in ("futures", "leveraged"):
            return out("FAIL", [f"{a.metal_structure} exposure fails AAOIFI Shari'ah Standard 57 (spot, owned gold)"])
        checks = {"allocated bars": a.allocated, "investor ownership rights": a.ownership_rights,
                  "spot settlement / constructive possession": a.spot_settlement, "no lending of the metal": a.no_lending}
        failed = [k for k, x in checks.items() if x == "no"]
        unknown = [k for k, x in checks.items() if x == "unknown"]
        if failed:
            return out("FAIL", [f"fund documents show: no {', '.join(failed)}"])
        if unknown:
            return out("INSUFFICIENT_DATA", [f"not verified from fund documents: {', '.join(unknown)}"])
        if a.certifier or a.certificate_date or a.certificate_url:
            why = certificate_problem(a)
            if why:
                return out("INSUFFICIENT_DATA", [f"certificate: {why}"])
            return out("PASS", [f"structure verified and certified by {a.certifier} ({a.certificate_date})"],
                       certificate=dict(certifier=a.certifier, date=a.certificate_date, url=a.certificate_url))
        return out("BORDERLINE", ["structure verified from fund documents, but no Shariah certificate; "
                                  "strict scholars dispute T+1 settlement"],
                   conditions=["full cash, no margin", "no options or short selling"])
    if a.asset == "etf-certified":
        why = certificate_problem(a)
        if why:
            return out("INSUFFICIENT_DATA", [f"certificate: {why}"])
        return out("PASS", [f"certified by {a.certifier} ({a.certificate_date}), {a.certificate_url}"],
                   certificate=dict(certifier=a.certifier, date=a.certificate_date, url=a.certificate_url),
                   purification=dict(status="CHECK FUND", note="check whether the fund purifies at fund level "
                                     "(--fund-purifies) before purifying personally"),
                   boycott_note="Shariah certification does not include the boycott screen")
    try:
        reg = reg or load_registry(a.registry)
    except Exception as e:
        return out("INSUFFICIENT_DATA", [f"methodology registry invalid: {e}"])
    if getattr(a, "provider", None) or getattr(a, "provider_verdict", None):
        return screen_provider(a)
    return screen_stock(a, reg)


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        res = screen(a)
    except Exception as e:
        res = out("INSUFFICIENT_DATA", [f"screen error: {e}"], schema=RESULT_SCHEMA, ticker=a.ticker.upper())
    text = json.dumps(res, indent=2)
    if a.out:
        with open(a.out, "w") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
