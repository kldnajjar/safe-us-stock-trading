# Contributing

Thanks for helping. This project plans real-money trades, so the bar is **correctness and safety first, features second**.

## Ground rules

1. **Numbers come from code, never from the model.** Anything that sizes, prices or screens a trade lives in `scripts/` and is covered by a test. `SKILL.md` tells Claude to run the scripts, not to do the maths.
2. **Fail closed.** Missing, stale or invalid data must lead to `WATCHLIST`, `NO TRADE` or `UNVERIFIED`, never to a quiet default.
3. **Standard library only.** Python 3.9+ with no third-party packages, so the skill runs anywhere Claude can run Python.
4. **No personal data in commits.** Portfolio state, plans and screening results are git-ignored for a reason. Keep personal fee schedules in `brokers.local.json`.

## Development setup

```bash
git clone https://github.com/kldnajjar/safe-us-stock-trading
cd safe-us-stock-trading
python3 safe-us-stock-trading/scripts/run_checks.py   # must print "ok": true
```

Run one test file while you work:

```bash
cd safe-us-stock-trading/scripts
python3 -m unittest test_dashboard -v
```

## What to contribute

| Contribution | What a good PR includes |
|---|---|
| **Broker fee profile** | A new entry in `brokers.json` copied from a template, `verified_source` set to the broker's public fee page (https), and the date you checked it. |
| **Shariah methodology update** | The new version added to `methodologies.json` from the provider's official document, the old one marked `historical_only`, and what you compared recorded in `evidence`. Titles alone never prove two versions are equivalent. |
| **Bug fix** | A failing test first, then the fix. Link the issue. |
| **Engine feature** | Open an issue first. Describe the gate or calculation, how it fails closed, and the tests that prove it. |
| **Docs** | Plain English, short sentences, no jargon without a definition. |

## Pull request checklist

- [ ] `run_checks.py` prints `"ok": true`
- [ ] New behaviour has tests; new files are added to `REQUIRED` in `run_checks.py`
- [ ] No change lowers a safety gate without an issue that explains why
- [ ] `SKILL.md` and `README.md` updated when behaviour or commands change
- [ ] Entry added under **Unreleased** in `CHANGELOG.md`
- [ ] No personal holdings, balances or account details anywhere in the diff

## Style

- Small, pure functions; one responsibility per script.
- Errors are explicit messages a non-programmer can act on ("stop is 7.5% below the highest entry; the safe short-term limit is 4%").
- Keep user-facing output in the existing plain style.

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE) and that you follow the [Code of Conduct](CODE_OF_CONDUCT.md).
