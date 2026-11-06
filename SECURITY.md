# Security Policy

## What counts as a security issue here

This skill never holds credentials and never places orders, so "security" mostly means **anything that could make a plan look safer than it is**. Report privately if you find a way to:

- bypass a gate (position cap, cash floor, stop distance, quote freshness, cent grid) and still get `TRADE`
- make a boycott or Shariah result file pass for a different ticker, ISIN or asset, or after it expires
- inject markup or script into the dashboard through a ticker, reason, note or source
- leak personal portfolio data into a committed file or published page

## Reporting

Use **GitHub private vulnerability reporting**: the repository's **Security** tab → **Report a vulnerability**. Please include the command, inputs and output that reproduce it.

Please don't open a public issue for these. You'll get a reply within 7 days, and a fix or a clear plan within 30 days. Reporters are credited in `CHANGELOG.md` unless they ask not to be.

## Supported versions

Only the latest release on `main` receives fixes.
