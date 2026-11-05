#!/usr/bin/env python3
"""One-command dependency and test check for the safe-us-stock-trading skill (v4.5).

  python3 "$SKILL_DIR/scripts/run_checks.py"

Checks every required file exists, both registries parse and pass schema
validation, then runs every test_*.py in this folder. Prints JSON; exit code 0
only if everything passes. On any failure the skill runs in WATCHLIST-only mode.
"""
import io, json, os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ["size_trade.py", "portfolio_state.py", "shariah_screen.py", "boycott_screen.py", "fees.py",
            "render_simple.py", "methodologies.json", "brokers.json",
            "test_size_trade.py", "test_audit_regressions.py", "test_integration.py",
            "test_v42_followup.py", "test_v43_policy.py",
            "test_v43_independent.py", "test_v44_hardening.py",
            "test_v44_independent_followup.py", "test_v45_hardening.py"]


def _iter_tests(suite):
    for t in suite:
        if isinstance(t, unittest.TestSuite):
            yield from _iter_tests(t)
        else:
            yield t


def main():
    report = dict(ok=False, missing=[], registry="not checked", brokers="not checked", tests="not run")
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

    if "--no-tests" in sys.argv:
        report["tests"] = "skipped (--no-tests)"
        report["ok"] = bool(report["registry"].get("valid") and report["brokers"].get("valid"))
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
                    and result.wasSuccessful() and result.testsRun > 0)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
