#!/usr/bin/env python3
"""One-command dependency and test check for the safe-us-stock-trading skill (v4.8).

  python3 "$SKILL_DIR/scripts/run_checks.py"

Checks every required file exists, both registries parse and pass schema
validation, then runs every test_*.py in this folder. Prints JSON; exit code 0
only if everything passes. On any failure the skill runs in WATCHLIST-only mode.
"""
import io, json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ["size_trade.py", "portfolio_state.py", "shariah_screen.py", "boycott_screen.py", "fees.py",
            "render_simple.py", "render_dashboard.py", "methodologies.json", "brokers.json",
            "sources_check.py", "sources.json", "signals.py", "market_clock.py", "ledger.py", "journal.py",
            "test_v48_mandatory.py", "test_v49_actions.py", "test_v50_ingest.py", "ingest.py", "browser_fetch.js", "money_plan.py",
            "test_size_trade.py", "test_audit_regressions.py", "test_integration.py",
            "test_v42_followup.py", "test_v43_policy.py",
            "test_v43_independent.py", "test_v44_hardening.py",
            "test_v44_independent_followup.py", "test_v45_hardening.py", "test_dashboard.py"]


WARN_DAYS = 30


def expiry_report(today=None):
    """Dates after which parts of the skill stop working, so they can be refreshed in time."""
    import datetime as dt
    import market_clock
    today = today or market_clock.CLOCK().date()
    items = []
    try:
        import shariah_screen
        reg = shariah_screen.load_registry()
        for k, m in reg["methodologies"].items():
            v = next(x for x in m["versions"] if x.get("current"))
            items.append((f"Shariah methodology {k} ({v['document_version']})",
                          dt.date.fromisoformat(v["verified_on"]) + dt.timedelta(days=reg["max_age_days"]),
                          "re-verify against the provider's document, update methodologies.json"))
    except Exception:
        pass
    try:
        import sources_check
        sreg = sources_check.load_registry()
        items.append(("source registry sources.json",
                      dt.date.fromisoformat(sreg["verified_on"]) + dt.timedelta(days=sreg.get("max_age_days", 180)),
                      "re-check the sources and domains, update verified_on"))
    except Exception:
        pass
    items.append(("NYSE holiday calendar", dt.date(max(market_clock.CALENDAR_YEARS), 12, 31),
                  f"add next year's holidays and early closes from {market_clock.CALENDAR_SOURCE}"))
    out, warnings = [], []
    for name, exp, todo in items:
        left = (exp - today).days
        status = "expired" if left < 0 else "expires soon" if left <= WARN_DAYS else "ok"
        out.append(dict(item=name, expires_on=exp.isoformat(), days_left=left, status=status))
        if status != "ok":
            warnings.append(f"{name} {status} ({exp.isoformat()}): {todo}")
    return out, warnings


def _iter_tests(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _iter_tests(t)
        else:
            yield t


def main():
    report = dict(ok=False, missing=[], registry="not checked", brokers="not checked", sources="not checked",
                  tests="not run")
    report["missing"] = [f for f in REQUIRED if not os.path.isfile(os.path.join(HERE, f))]
    if report["missing"]:
        print(json.dumps(report, indent=2))
        return 1
    sys.path.insert(0, HERE)
    try:
        import shariah_screen
        reg = shariah_screen.load_registry()
        report["registry"] = dict(valid=True, methodologies={
            k: next(v["document_version"] for v in m["versions"] if v.get("current"))
            for k, m in reg["methodologies"].items()})
    except Exception as e:
        report["registry"] = dict(valid=False, error=str(e))
    try:
        import fees
        b = fees.load_brokers()
        report["brokers"] = dict(valid=True, profiles=[k for k, v in b["brokers"].items() if not v.get("template")])
    except Exception as e:
        report["brokers"] = dict(valid=False, error=str(e))

    try:
        import sources_check
        sreg = sources_check.load_registry()
        report["sources"] = dict(valid=True, verified_on=sreg.get("verified_on"), registered=len(sreg["sources"]),
                                 categories=sorted(sreg["categories"]))
    except Exception as e:
        report["sources"] = dict(valid=False, error=str(e))

    try:
        import market_clock
        report["market_clock"] = market_clock.status()
    except Exception as e:
        report["market_clock"] = dict(error=str(e))

    report["expiry"], report["warnings"] = expiry_report()
    if "--no-tests" in sys.argv:
        report["tests"] = "skipped (--no-tests)"
        report["ok"] = bool(report["registry"].get("valid") and report["brokers"].get("valid")
                            and report["sources"].get("valid"))
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    suite = unittest.defaultTestLoader.discover(HERE, pattern="test_*.py")
    per_file = {}
    for t in _iter_tests(suite):
        mod = t.id().split(".")[0]
        per_file[mod] = per_file.get(mod, 0) + 1
    buf = io.StringIO()
    result = unittest.TextTestRunner(stream=buf, verbosity=0).run(suite)
    report["tests"] = dict(run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                           by_file=per_file, failed=[str(t) for t, _ in result.failures + result.errors][:20])
    report["ok"] = (report["registry"].get("valid") and report["brokers"].get("valid")
                    and report["sources"].get("valid") and result.wasSuccessful() and result.testsRun > 0)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
