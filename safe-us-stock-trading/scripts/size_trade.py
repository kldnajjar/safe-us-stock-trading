#!/usr/bin/env python3
"""Position sizing and trade-lifecycle engine for the safe-us-stock-trading skill (v4.5).

All money in the account currency (USD for US stocks). Fees come from a broker
profile in brokers.json (--broker ID) or an explicit --fee-model. There is no
default fee schedule: without one the result is NO TRADE.

Two paths:
  * Price trades (--asset stock|etf|metal): entry (or tranches), stop/review level, T1, T2.
  * Cash management (--asset tbill): yield, expense ratio, duration, spread, hold period.

Every numeric input is validated (finite; positive or non-negative as appropriate).
Any invalid input -> NO TRADE. An engine error -> NO TRADE.

Cash accounting:
  --cash        settled cash NOW (already reduced by every EXECUTED purchase)
  --committed   cash reserved for UNFILLED orders (open orders and accepted plans)
  available   = cash - committed - cash_floor      (the floor applies to every purchase, T-bills included)

Exposure accounting (--state from portfolio_state.py fills these):
  --ticker-exposure   $ already held or on order in THIS ticker (plus --related-tickers share classes)
  --portfolio-sectors JSON {sector: $}; --sector-weights JSON {sector: fraction} for THIS instrument,
                      each in [0, 1], summing to 1 (put any unknown share under "Unclassified")

Gates (any failure -> NO TRADE). Screen modes are REQUIRED arguments:
  --boycott-mode exclude|flag|off   exclude: needs --boycott-result from boycott_screen.py for this
                                    ticker/asset/ISIN; EXCLUDED/UNVERIFIED block; FLAGGED needs --accept-flagged
  --shariah-mode exclude|flag|off   exclude: needs --shariah-result from shariah_screen.py for this
                                    ticker/asset/ISIN; EXCLUDED/UNVERIFIED block; REQUIRES_ACCEPTANCE needs
                                    --accept-shariah-review
  Breached holdings (state)         block every new trade until reconciled
  Unquantified holdings             block new price trades unless --unquantified-loss-pct (10-100) is set
  Stop distance                     must not exceed the horizon/profile limit, for every tranche

Time and quotes (v4.3). Freshness is measured against the SYSTEM CLOCK (UTC), never the caller:
  * --as-of must be today's date (within one day of the clock's UTC date) for an executable plan.
  * --quote-time is ISO 8601 with a UTC offset. A quote more than 5 minutes in the future -> WATCHLIST.
  * live quote: at most 15 minutes old. delayed quote: stated delay <= 20 minutes and age <= delay + 15.
  * previous_close / unknown, or no source -> WATCHLIST.
  * --now replays a past moment for research/backtests; a replay is NEVER executable (WATCHLIST).
  * --market-price is the last price from the SAME quote. Required for TRADE (missing -> WATCHLIST).
    Every entry must be <= 1% above it and the stop must be below it, else NO TRADE.

A TRADE is "provisional" until --confirm-order "TICKER|limit|PRICE|SHARES" matches the first order
exactly AND, for short/medium horizons, the hard stop can be placed: --stop-orders yes, or
--stop-orders no with --manual-stop-ack (the user accepts a price alert and a manual sell).
Plans are limit orders, so only a limit confirmation counts. A confirmation never guarantees a fill.

FX: a broker's fx_pct is charged only when --instrument-currency (default USD) differs from the
account currency (--account-currency, else the broker profile's currency). There is no exchange-rate
model yet, so a cross-currency plan is never executable (WATCHLIST); hold USD in the account instead.

Prices below $1.00 are rejected (sub-penny ticks), and every order and level price (entry, tranches,
stop, targets, T-bill limit) must be on the one-cent grid, or the result is NO TRADE. Prices are never
rounded for you.

Sector caps are worst case for unclassified money: "Unclassified" portfolio exposure (including
holdings with no sector data) and the new instrument's own "Unclassified" weight are assumed to sit
in whichever single sector they would push over its cap.

T-bill ETFs follow the same market rule as price trades: --market-price is required (missing ->
WATCHLIST) and a --price more than 1% above it is NO TRADE. The share
quantity is found by a bounded binary search, so sizing time does not grow with account size.
"""
import argparse, datetime as dt, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fees import make_fee, make_fee_model, broker_profile  # noqa: E402,F401
import shariah_screen  # noqa: E402
import boycott_screen  # noqa: E402

PROFILES = {
    "safe":       dict(stock_cap=0.05, etf_cap=0.25, metals_max=0.20, risk=0.005, open_risk=0.03,
                       sector=0.20, min_rr=2.5, cash_floor=0.20, max_positions=6),
    "balanced":   dict(stock_cap=0.10, etf_cap=0.35, metals_max=0.15, risk=0.010, open_risk=0.06,
                       sector=0.30, min_rr=2.0, cash_floor=0.10, max_positions=8),
    "aggressive": dict(stock_cap=0.15, etf_cap=0.40, metals_max=0.15, risk=0.020, open_risk=0.10,
                       sector=0.40, min_rr=2.0, cash_floor=0.05, max_positions=10),
}
# Maximum stop (or review-level) distance from EVERY entry price, by horizon and profile.
MAX_STOP_DISTANCE = {
    "short":  {"safe": 0.04, "balanced": 0.06, "aggressive": 0.10},
    "medium": {"safe": 0.08, "balanced": 0.12, "aggressive": 0.18},
    "long":   {"safe": 0.12, "balanced": 0.18, "aggressive": 0.25},
}
TBILL_MAX = {"safe": 0.50, "balanced": 0.40, "aggressive": 0.30}
COUNTED_ASSETS = {"stock", "etf"}
EXECUTABLE_QUOTES = {"live", "delayed"}
HARD_STOP_HORIZONS = {"short", "medium"}
SHARIAH_ASSET = {"stock": "stock", "etf": "etf-certified", "metal": "metal", "tbill": "tbill"}
MAX_DELAY_MIN = 20
FUTURE_TOLERANCE = dt.timedelta(minutes=5)
LIVE_MAX_AGE = dt.timedelta(minutes=15)
DELAYED_EXTRA_AGE = dt.timedelta(minutes=15)
MAX_ENTRY_ABOVE_MARKET = 0.01
AS_OF_TOLERANCE_DAYS = 1


def CLOCK():
    """The system clock (UTC). Tests replace this function; nothing on the command line can."""
    return dt.datetime.now(dt.timezone.utc)
UNQ_MIN_PCT, UNQ_MAX_PCT = 10.0, 100.0
SECTOR_SUM_TOL = 0.01
TICK = 0.01
MIN_PRICE = 1.00          # below $1, US quotes use sub-penny ticks; levels here are on a one-cent grid
UNCLASSIFIED = "Unclassified"
OTHER_SECTOR = "(any other sector)"


def on_tick(x, tick=TICK):
    return abs(round(x / tick) - x / tick) < 1e-6


def off_grid(named):
    """Names of prices that are not on the cent grid."""
    return [f"{n}={v}" for n, v in named if v is not None and not on_tick(v)]


def sector_rooms(weights, port_sec, limit):
    """{sector: (room $, effective weight)} with unclassified money placed worst case.
    Portfolio "Unclassified" exposure counts against every sector; the new instrument's
    "Unclassified" weight is added to each sector's weight. OTHER_SECTOR covers any sector
    the user doesn't already hold."""
    held_unc = port_sec.get(UNCLASSIFIED, 0.0)
    new_unc = weights.get(UNCLASSIFIED, 0.0)
    rows = {}
    for s in sorted((set(port_sec) | set(weights)) - {UNCLASSIFIED}):
        rows[s] = (limit - port_sec.get(s, 0.0) - held_unc, weights.get(s, 0.0) + new_unc)
    rows[OTHER_SECTOR] = (limit - held_unc, new_unc)
    return {s: r for s, r in rows.items() if r[1] > 0}
QUOTE_VALIDITY = "this quote only: live <= 15 min old, delayed <= delay + 15 min; re-check in the app"


# --------------------------------------------------------------------------- helpers
def solve_price(target_net, n, fee, fr=0.0, tick=TICK):
    """Lowest price on the tick grid at which selling n shares nets >= target_net
    after the sell commission and exit friction. Rounded UP, then verified."""
    def net(p):
        v = n * p
        return v - fee(v, n, side="sell") - fr * v
    if target_net <= 0:
        return 0.0
    lo, hi = 0.0, max(target_net / max(n, 1), 1.0) * 2 + 100
    while net(hi) < target_net:
        hi *= 2
    for _ in range(200):
        mid = (lo + hi) / 2
        if net(mid) >= target_net:
            hi = mid
        else:
            lo = mid
    p = math.ceil(round(hi / tick, 6)) * tick
    while net(p) < target_net:
        p += tick
    return round(p, 2)


def split_shares(n, k):
    """Split n shares into k tranches as evenly as possible (larger first)."""
    base, extra = divmod(n, k)
    return [base + (1 if i < extra else 0) for i in range(k)]


def finite(x):
    return isinstance(x, (int, float)) and math.isfinite(x)


def parse_quote_time(s):
    t = dt.datetime.fromisoformat(s)
    if t.tzinfo is None:
        raise ValueError("no UTC offset")
    return t


def build_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("--asset", choices=["stock", "etf", "metal", "tbill"], required=True)
    ap.add_argument("--profile", choices=PROFILES, required=True)
    ap.add_argument("--portfolio", type=float, help="total market value incl. cash (or use --state)")
    ap.add_argument("--cash", type=float, help="settled cash now, after executed purchases (or use --state)")
    ap.add_argument("--committed", type=float, default=0.0, help="cash reserved for unfilled orders and accepted plans")
    ap.add_argument("--quote-status", choices=["live", "delayed", "previous_close", "unknown"], required=True)
    ap.add_argument("--quote-time", default="", help="ISO 8601 with UTC offset, e.g. 2026-11-05T15:30:00-05:00")
    ap.add_argument("--quote-source", default="")
    ap.add_argument("--quote-delay-min", type=int, help="stated delay in minutes for a delayed quote")
    ap.add_argument("--market-price", type=float, help="last traded price from the same quote (--quote-time/--quote-source)")
    ap.add_argument("--now", default="", help="REPLAY ONLY: ISO time with offset to evaluate a past moment; never executable")
    ap.add_argument("--stop-orders", choices=["yes", "no", "unknown"], default="unknown",
                    help="does the user's platform accept a stop order for this instrument? (user-confirmed)")
    ap.add_argument("--manual-stop-ack", action="store_true",
                    help="no stop orders: the user accepts a price alert at the stop and selling manually")
    ap.add_argument("--instrument-currency", default="USD")
    ap.add_argument("--account-currency", default="", help="default: the broker profile's currency (USD for --fee-model)")
    ap.add_argument("--ticker", type=str, default="")
    ap.add_argument("--isin", type=str, default="")
    ap.add_argument("--related-tickers", default="", help="other share classes of the same company, comma-separated")
    ap.add_argument("--confirm-order", type=str, default="",
                    help="TICKER|limit|LIMIT_PRICE|SHARES the user verified in the app for THIS order")
    ap.add_argument("--state", type=str, default="", help="portfolio_state.py output JSON")
    ap.add_argument("--as-of", default="", help="today's date YYYY-MM-DD")
    ap.add_argument("--boycott-mode", choices=["exclude", "flag", "off"], required=True)
    ap.add_argument("--boycott-result", default="", help="JSON file written by boycott_screen.py --out")
    ap.add_argument("--accept-flagged", action="store_true")
    ap.add_argument("--shariah-mode", choices=["exclude", "flag", "off"], required=True)
    ap.add_argument("--shariah-result", default="", help="JSON file written by shariah_screen.py --out")
    ap.add_argument("--accept-shariah-review", action="store_true")
    # price-trade inputs
    ap.add_argument("--horizon", choices=["short", "medium", "long"], default="short")
    ap.add_argument("--entry", type=float)
    ap.add_argument("--tranches", type=str, default="", help="comma-separated tranche prices (overrides --entry)")
    ap.add_argument("--stop", type=float, help="hard stop (short/medium) or review level (long)")
    ap.add_argument("--t1", type=float)
    ap.add_argument("--t2", type=float)
    ap.add_argument("--sector-weights", type=str, default="")
    ap.add_argument("--portfolio-sectors", type=str, default="{}")
    ap.add_argument("--ticker-exposure", type=float, default=0.0, help="$ already held or on order in this ticker")
    ap.add_argument("--open-stop-risk", type=float, default=0.0)
    ap.add_argument("--open-review-risk", type=float, default=0.0)
    ap.add_argument("--unquantified-holdings", type=int, default=0)
    ap.add_argument("--unquantified-value", type=float, default=0.0)
    ap.add_argument("--unquantified-loss-pct", type=float,
                    help=f"conservative assumed loss on unquantified holdings, {UNQ_MIN_PCT:g}-{UNQ_MAX_PCT:g}%%")
    ap.add_argument("--metals-exposure", type=float, default=0.0)
    ap.add_argument("--open-positions", type=int, default=0)
    ap.add_argument("--friction-bps", type=float, default=5.0)
    ap.add_argument("--gap-pct", type=float, default=5.0)
    # T-bill inputs
    ap.add_argument("--amount", type=float)
    ap.add_argument("--price", type=float)
    ap.add_argument("--tbill-exposure", type=float, default=0.0)
    ap.add_argument("--yield-pct", type=float)
    ap.add_argument("--yield-basis", choices=["sec", "gross"], default="sec")
    ap.add_argument("--expense-ratio-pct", type=float, default=0.0)
    ap.add_argument("--duration-yrs", type=float)
    ap.add_argument("--spread-bps", type=float, default=2.0)
    ap.add_argument("--hold-months", type=float)
    ap.add_argument("--rate-shock-pct", type=float, default=1.0)
    # fees
    ap.add_argument("--broker", default="")
    ap.add_argument("--brokers", default="")
    ap.add_argument("--fee-model", choices=["percent", "per_share", "flat", "zero"])
    ap.add_argument("--fee-rate", type=float)
    ap.add_argument("--fee-min", type=float)
    ap.add_argument("--fee-max", type=float)
    ap.add_argument("--fee-per-share", type=float)
    ap.add_argument("--fee-max-pct", type=float)
    ap.add_argument("--fee-flat", type=float)
    ap.add_argument("--fx-pct", type=float)
    ap.add_argument("--min-order", type=float)
    return ap


def best_quantity(k, plan, planned_loss, fee, cap, available, loss_limit, min_order, min_price):
    """Largest whole-share quantity n >= k that fits every constraint, or None.

    Each tranche gets at least one share and at least min_order of value ("floor" conditions, which
    only become true as n grows). The total stays within cap, the cost with fees within available
    cash, and the planned loss within loss_limit ("ceiling" conditions, which only become false as
    n grows, because every fee model is nondecreasing in order size). So the feasible set is one
    interval, and two binary searches find its top in O(log n), whatever the share price is.
    test_v44_hardening checks this against a linear scan."""
    if cap <= 0 or min_price <= 0:
        return None
    hi = int(cap // min_price)
    if hi < k:
        return None

    def floor_ok(n):
        parts, buys = plan(n)
        return min(parts) >= 1 and min(buys) >= min_order

    def ceiling_ok(n):
        parts, buys = plan(n)
        return (sum(buys) <= cap and sum(b + fee(b, q) for q, b in zip(parts, buys)) <= available
                and planned_loss(n) <= loss_limit)

    lo_n, top = k, hi                     # smallest n meeting the floor conditions
    if not floor_ok(top):
        return None
    while lo_n < top:
        mid = (lo_n + top) // 2
        if floor_ok(mid):
            top = mid
        else:
            lo_n = mid + 1
    first = lo_n
    if not ceiling_ok(first):
        return None
    lo_n, top = first, hi                 # largest n meeting the ceiling conditions
    while lo_n < top:
        mid = (lo_n + top + 1) // 2
        if ceiling_ok(mid):
            lo_n = mid
        else:
            top = mid - 1
    return lo_n


# --------------------------------------------------------------------------- validation
def validate_inputs(a):
    """Domain checks. Returns a list of problems (empty = valid)."""
    bad = []

    def need(name, cond, msg):
        v = getattr(a, name)
        if v is not None and (not finite(v) or not cond(v)):
            bad.append(f"--{name.replace('_', '-')} {msg} (got {v})")
    pos, nonneg = (lambda v: v > 0), (lambda v: v >= 0)
    for n in ("portfolio",):
        need(n, pos, "must be a positive number")
    for n in ("cash", "committed", "ticker_exposure", "open_stop_risk", "open_review_risk", "unquantified_value",
              "metals_exposure", "tbill_exposure", "friction_bps", "expense_ratio_pct", "spread_bps", "min_order"):
        need(n, nonneg, "must be zero or more")
    for n in ("entry", "stop", "t1", "t2", "amount", "price", "hold_months", "gap_pct", "market_price"):
        need(n, pos, "must be a positive number")
    for n in ("yield_pct", "duration_yrs", "rate_shock_pct"):
        need(n, nonneg, "must be zero or more")
    for n in ("open_positions", "unquantified_holdings"):
        if getattr(a, n) < 0:
            bad.append(f"--{n.replace('_', '-')} must be zero or more")
    if a.quote_delay_min is not None and a.quote_delay_min < 0:
        bad.append("--quote-delay-min must be zero or more")
    if a.unquantified_loss_pct is not None and (not finite(a.unquantified_loss_pct)
                                                or not UNQ_MIN_PCT <= a.unquantified_loss_pct <= UNQ_MAX_PCT):
        bad.append(f"--unquantified-loss-pct must be between {UNQ_MIN_PCT:g} and {UNQ_MAX_PCT:g} (got {a.unquantified_loss_pct})")
    if a.tranches:
        try:
            ps = [float(x) for x in a.tranches.split(",") if x.strip()]
            if not ps or any(not finite(p) or p <= 0 for p in ps):
                bad.append("--tranches must be positive prices")
        except ValueError:
            bad.append("--tranches must be comma-separated numbers")
    return bad


def parse_sector_weights(a):
    """Returns (weights, port_sectors, problems)."""
    probs = []
    try:
        w = json.loads(a.sector_weights) if a.sector_weights else {}
        ps = json.loads(a.portfolio_sectors or "{}")
    except json.JSONDecodeError as e:
        return {}, {}, [f"sector JSON is invalid: {e}"]
    if not isinstance(w, dict) or not isinstance(ps, dict):
        return {}, {}, ["sector data must be JSON objects"]
    for s, x in w.items():
        if not finite(x) or not 0 <= x <= 1:
            probs.append(f"sector weight for '{s}' must be between 0 and 1 (got {x})")
    for s, x in ps.items():
        if not finite(x) or x < 0:
            probs.append(f"portfolio sector exposure for '{s}' must be zero or more (got {x})")
    if a.asset in COUNTED_ASSETS and not w:
        probs.append("--sector-weights is required for stocks and ETFs (sector data missing)")
    if w and not probs and abs(sum(w.values()) - 1) > SECTOR_SUM_TOL:
        probs.append(f"sector weights must sum to 1 (got {sum(w.values()):.4f}); "
                     "put any unknown share under \"Unclassified\"")
    return w, ps, probs


def quote_check(a):
    """Returns None if the quote supports an executable plan, else the reason it doesn't.
    The reference time is the system clock; --now is a replay and never executable."""
    if a.quote_status not in EXECUTABLE_QUOTES:
        return f"quote status '{a.quote_status}': levels are conditional, not executable"
    if not (a.quote_time and a.quote_source):
        return "quote time and source not recorded: levels are conditional, not executable"
    try:
        qt = parse_quote_time(a.quote_time)
    except ValueError:
        return "quote time must be ISO 8601 with a UTC offset (e.g. 2026-11-05T15:30:00-05:00)"
    if a.now:
        try:
            parse_quote_time(a.now)
        except ValueError:
            return "--now must be ISO 8601 with a UTC offset"
        return "replay (--now): research only, never executable; rerun without --now on a live quote"
    clock = CLOCK()
    try:
        as_of = dt.date.fromisoformat(a.as_of)
    except (TypeError, ValueError):
        return "--as-of (today's date) is required for an executable plan"
    if abs((as_of - clock.date()).days) > AS_OF_TOLERANCE_DAYS:
        return (f"--as-of {as_of} is not today ({clock.date()} UTC): research only, not executable")
    if qt > clock + FUTURE_TOLERANCE:
        return f"quote time {a.quote_time} is in the future (clock {clock.isoformat(timespec='seconds')})"
    age = clock - qt
    if a.quote_status == "live" and age > LIVE_MAX_AGE:
        return (f"live quote is {int(age.total_seconds() // 60)} minutes old (limit "
                f"{int(LIVE_MAX_AGE.total_seconds() // 60)}): refresh it")
    if a.quote_status == "delayed":
        if a.quote_delay_min is None or a.quote_delay_min > MAX_DELAY_MIN:
            return f"delayed quote without a stated delay of {MAX_DELAY_MIN} minutes or less: not executable"
        limit = dt.timedelta(minutes=a.quote_delay_min) + DELAYED_EXTRA_AGE
        if age > limit:
            return (f"delayed quote is {int(age.total_seconds() // 60)} minutes old (limit "
                    f"{int(limit.total_seconds() // 60)}): refresh it")
    return None


def market_check(a, prices):
    """(blocking_reasons, watch_reason). Ties the levels to the market price from the same quote."""
    if a.market_price is None:
        return [], "no --market-price from the same quote: cannot check the entry against the market"
    block = []
    hi = a.market_price * (1 + MAX_ENTRY_ABOVE_MARKET)
    above = [p for p in prices if p > hi + 1e-9]
    if above:
        block.append(f"entry {max(above):.2f} is more than {100 * MAX_ENTRY_ABOVE_MARKET:g}% above the market "
                     f"price {a.market_price:.2f}: re-plan the entry")
    if a.stop is not None and a.stop >= a.market_price:
        block.append(f"market price {a.market_price:.2f} is at or below the stop {a.stop:.2f}: the setup is broken")
    return block, None


def stop_capability(a):
    """None if the stop can be handled, else why the plan must stay provisional."""
    if a.horizon not in HARD_STOP_HORIZONS or a.asset == "tbill":
        return None
    if a.stop_orders == "yes":
        return None
    if a.stop_orders == "no" and a.manual_stop_ack:
        return None
    if a.stop_orders == "no":
        return ("the platform has no stop orders: the user must accept a price alert and a manual sell "
                "(--manual-stop-ack) before this is ready")
    return "stop-order support not confirmed on the user's platform (--stop-orders yes|no)"


def placement(verdict, a, first_price=None, first_shares=None):
    if verdict != "TRADE":
        return "not placeable"
    if a.confirm_order:
        stop_issue = stop_capability(a)
        parts = [x.strip() for x in a.confirm_order.split("|")]
        ok = len(parts) == 4 and a.ticker and parts[0].upper() == a.ticker.upper() and parts[1].lower() == "limit"
        if ok and first_price is not None:
            try:
                ok = abs(float(parts[2]) - first_price) < 0.005 and int(parts[3]) == first_shares
            except ValueError:
                ok = False
        if ok and stop_issue:
            return f"provisional: order confirmed, but {stop_issue}"
        if ok and a.asset == "tbill":
            return ("ready to place: the user confirmed this exact limit order in the app; no stop applies to this "
                    "cash-management fund, but its price moves with interest rates (see rate_shock_loss); "
                    "fills are not guaranteed")
        if ok:
            how = ("place the stop order right after the fill" if a.stop_orders == "yes" else
                   "set a price alert at the stop and sell manually" if a.horizon in HARD_STOP_HORIZONS
                   else "review level only, no stop order")
            return (f"ready to place: the user confirmed this exact limit order in the app; {how}; "
                    "fills and stop executions are not guaranteed")
        return ("provisional: --confirm-order does not match this plan (it must be a LIMIT order with the same "
                "ticker, price and shares); re-confirm in the app")
    if a.asset == "tbill":
        return ("provisional: confirm in the app the fund's live price and that a limit order is available for this "
                "exact order (--confirm-order); no stop applies; fills are not guaranteed")
    return ("provisional: confirm in the app that the live quote is inside the entry zone and that a limit order "
            "(and a stop, where used) is available for this exact order (--confirm-order, --stop-orders); "
            "fills are not guaranteed")


# --------------------------------------------------------------------------- screens
def shariah_check(a):
    if a.shariah_mode == "off":
        return dict(mode="off"), []
    if not a.shariah_result:
        pol, why, res = "UNVERIFIED", ["no --shariah-result file from shariah_screen.py"], {}
    else:
        try:
            with open(a.shariah_result) as f:
                res = json.load(f)
            pol, why = shariah_screen.validate_result(res, a.ticker, a.as_of,
                                                      expected_asset=SHARIAH_ASSET[a.asset], isin=a.isin)
        except Exception as e:
            pol, why, res = "UNVERIFIED", [f"Shariah result unreadable: {e}"], {}
    screened = not why
    summary = dict(mode=a.shariah_mode, policy_decision=pol, screened=screened, methodology=res.get("methodology"),
                   screening_result=res.get("screening_result"), purification=res.get("purification"),
                   validation=why or ["valid"])
    block = []
    if a.shariah_mode == "exclude":
        if pol in ("EXCLUDED", "UNVERIFIED"):
            block.append(f"Shariah screen: {pol.lower()}" + (f" ({'; '.join(why)})" if why else ""))
        elif pol == "REQUIRES_ACCEPTANCE" and not a.accept_shariah_review:
            block.append("Shariah screen: requires acceptance; user has not accepted it")
    return summary, block


def boycott_check(a):
    if a.boycott_mode == "off":
        return dict(mode="off"), []
    if not a.boycott_result:
        status, why, res = "UNVERIFIED", ["no --boycott-result file from boycott_screen.py"], {}
    else:
        try:
            with open(a.boycott_result) as f:
                res = json.load(f)
            status, why = boycott_screen.validate_result(res, a.ticker, a.asset, a.isin, a.as_of)
        except Exception as e:
            status, why, res = "UNVERIFIED", [f"boycott result unreadable: {e}"], {}
    screened = not why
    summary = dict(mode=a.boycott_mode, status=status, screened=screened, strictness=res.get("strictness"),
                   reasons=res.get("reasons"), ohchr_involvement=res.get("ohchr_involvement"),
                   validation=why or ["valid"])
    block = []
    if a.boycott_mode == "exclude":
        if status in ("EXCLUDED", "UNVERIFIED"):
            block.append(f"boycott screen: {status.lower()}" + (f" ({'; '.join(why)})" if why else ""))
        elif status == "FLAGGED" and not a.accept_flagged:
            block.append("boycott screen: flagged; user has not accepted it")
    return summary, block


def gate_reasons(a):
    if (a.shariah_mode != "off" or a.boycott_mode != "off") and a.asset in COUNTED_ASSETS and not a.isin:
        identity = ["--isin is required when a screen is on, so results can be matched to this security"]
    else:
        identity = []
    a._boycott_summary, b = boycott_check(a)
    a._shariah_summary, s = shariah_check(a)
    a._screen_warnings = [f"SCREEN NOT RUN: {name} is set to flag but has no valid result file; "
                          f"this {a.asset} has NOT been {name}-screened"
                          for name, summ in (("boycott", a._boycott_summary), ("Shariah", a._shariah_summary))
                          if summ.get("mode") == "flag" and not summ.get("screened")]
    return identity + b + s


# --------------------------------------------------------------------------- state
def load_state(a):
    if not a.state:
        return []
    with open(a.state) as f:
        st = json.load(f)
    if st.get("error"):
        return [f"portfolio state error: {st['error']}"]
    args = st["size_trade_args"]
    a.portfolio, a.cash, a.committed = args["portfolio"], args["cash"], args["committed"]
    a.portfolio_sectors = json.dumps(args["portfolio_sectors"])
    a.open_stop_risk, a.open_review_risk = args["open_stop_risk"], args["open_review_risk"]
    a.unquantified_holdings = args["unquantified_holdings"]
    a.unquantified_value = args.get("unquantified_value", 0.0)
    a.metals_exposure, a.tbill_exposure = args["metals_exposure"], args["tbill_exposure"]
    a.open_positions = args["open_positions"]
    by_ticker = args.get("ticker_exposure", {})
    names = [a.ticker.upper()] + [t.strip().upper() for t in a.related_tickers.split(",") if t.strip()]
    a.ticker_exposure = sum(by_ticker.get(t, 0.0) for t in names)
    if st.get("reconciliation_required"):
        return ["a holding is at or below its stop/review level: reconcile it before any new trade"]
    return []


def common(a, p):
    floor = p["cash_floor"] * a.portfolio
    available = a.cash - a.committed - floor
    warnings = []
    if a.unquantified_holdings > 0:
        warnings.append(f"{a.unquantified_holdings} existing holding(s) have no stop/review level: risk UNQUANTIFIED, not zero")
    accounting = dict(settled_cash=round(a.cash, 2), unfilled_commitments=round(a.committed, 2),
                      cash_floor=round(floor, 2), available_cash=round(available, 2))
    return available, accounting, warnings


def reservation(order_value, buy_fees, first_total, later_total):
    return dict(order_value=round(order_value, 2), buy_fees=round(buy_fees, 2),
                total=round(order_value + buy_fees, 2),
                first_order_total=round(first_total, 2), later_orders_total=round(later_total, 2))


# --------------------------------------------------------------------------- T-bill path
def compute_tbill(a, fee, p):
    reasons = []
    available, accounting, warnings = common(a, p)
    if a.shariah_mode == "exclude":
        return dict(verdict="NO TRADE", asset="tbill", cash_accounting=accounting, warnings=warnings,
                    reasons=["Shariah screen: T-bill ETFs are interest-bearing; keep cash or use a certified sukuk fund"])
    reasons.extend(gate_reasons(a))
    warnings.extend(w for w in a._screen_warnings if not w.startswith("SCREEN NOT RUN: Shariah"))
    if a.shariah_mode == "flag":
        warnings.append("Shariah flag: T-bill ETFs pay interest and are non-compliant under every registered "
                        "methodology; shown because the screen is set to flag, not exclude")
    for name in ("amount", "price", "yield_pct", "duration_yrs", "hold_months"):
        if getattr(a, name) is None:
            reasons.append(f"--{name.replace('_', '-')} is required for --asset tbill")
    if a.price is not None:
        if a.price < MIN_PRICE:
            reasons.append(f"prices under ${MIN_PRICE:.2f} are not supported")
        reasons.extend(f"price must be on the one-cent grid (not rounded for you): {x}"
                       for x in off_grid([("price", a.price)]))
        if a.market_price is not None:
            if a.price > a.market_price * (1 + MAX_ENTRY_ABOVE_MARKET) + 1e-9:
                reasons.append(f"limit {a.price:.2f} is more than {100 * MAX_ENTRY_ABOVE_MARKET:g}% above the market "
                               f"price {a.market_price:.2f}: re-plan the order")
    mwatch = None if a.market_price is not None else \
        "no --market-price from the same quote: cannot check the limit against the market"
    base_out = dict(asset="tbill", cash_accounting=accounting, warnings=warnings,
                    shariah=getattr(a, "_shariah_summary", None), boycott=getattr(a, "_boycott_summary", None))
    if reasons:
        return dict(verdict="NO TRADE", reasons=reasons, **base_out)

    cap_room = TBILL_MAX[a.profile] * a.portfolio - a.tbill_exposure
    n = int(max(0.0, min(a.amount, cap_room, available)) // a.price)
    value = n * a.price
    while n > 0 and value + fee(value, n) > available:
        n -= 1
        value = n * a.price
    if n < 1 or value < a.min_order:
        reasons.append(f"after the cash floor, commitments and the T-bill cap, no order of at least "
                       f"${a.min_order:,.0f} fits")
        return dict(verdict="NO TRADE", reasons=reasons, limits=dict(tbill_cap_room=round(cap_room, 2)), **base_out)

    buy_fee, sell_fee = fee(value, n), fee(value, n, side="sell")
    spread_cost = value * a.spread_bps / 10000
    yrs = a.hold_months / 12
    gross_income = value * (a.yield_pct / 100) * yrs
    expense = value * (a.expense_ratio_pct / 100) * yrs if a.yield_basis == "gross" else 0.0
    net = gross_income - expense - buy_fee - sell_fee - spread_cost
    net_yield = a.yield_pct - (a.expense_ratio_pct if a.yield_basis == "gross" else 0.0)
    daily_net_carry = value * net_yield / 100 / 365
    breakeven_days = (buy_fee + sell_fee + spread_cost) / daily_net_carry if daily_net_carry > 0 else None
    rate_shock = value * a.duration_yrs * a.rate_shock_pct / 100

    if net <= 0:
        reasons.append("fees and spread exceed expected income over the holding period; keep it as cash")
    q = quote_check(a)
    fxw = (f"account currency differs from {a.instrument_currency.upper()}: no exchange-rate model, so amounts "
           "and limits are not normalized; plan is research only" if a._convert else None)
    watch = [x for x in (q, mwatch, fxw) if x]
    if reasons:
        verdict = "NO TRADE"
    elif watch:
        verdict = "WATCHLIST"
        reasons.extend(watch)
    else:
        verdict = "TRADE"
    res = reservation(value, buy_fee, value + buy_fee, 0.0)
    return dict(
        verdict=verdict, reasons=reasons, profile=a.profile, ticker=a.ticker.upper(),
        placement_status=placement(verdict, a, a.price, n),
        shares=n, order_value=res["order_value"], buy_fee=res["buy_fees"],
        total_order_value=res["order_value"], total_buy_fees=res["buy_fees"], reservation=res,
        sell_fee_est=round(sell_fee, 2), spread_cost=round(spread_cost, 2),
        expected_gross_income=round(gross_income, 2), expense_ratio_cost=round(expense, 2),
        expense_ratio_note=("SEC yield is already net of fund expenses; expense ratio shown for information only"
                            if a.yield_basis == "sec" else "gross yield: expense ratio deducted"),
        expected_net_return=round(net, 2), expected_net_return_pct=round(100 * net / value, 3),
        breakeven_holding_days=None if breakeven_days is None else round(breakeven_days, 1),
        rate_shock_loss=dict(shock_pct=a.rate_shock_pct, loss=round(rate_shock, 2),
                             note="approximate price loss = value x duration x rate rise"),
        downside=dict(executable_stop_downside=0.0, long_term_review_level_downside=0.0,
                      note="no stop: cash-management holding; see rate_shock_loss"),
        limits=dict(tbill_cap_room=round(cap_room, 2)), broker=a._broker_name,
        quote=dict(time=a.quote_time or None, source=a.quote_source or None, status=a.quote_status,
                   delay_min=a.quote_delay_min, market_price=a.market_price, valid_for=QUOTE_VALIDITY),
        note="T-bill ETF value is NOT settled cash; selling it is required before the cash can be used",
        assumptions=dict(fee_schedule=a._fee_source, fx_conversion_charged=a._convert, yield_basis=a.yield_basis,
                         estimate="historical yield, not a guaranteed forward return; price and distributions vary"),
        **{k: v for k, v in base_out.items() if k not in ("asset",)},
    )


# --------------------------------------------------------------------------- price-trade path
def compute_price(a, fee, p):
    reasons = []
    available, accounting, warnings = common(a, p)
    fr = a.friction_bps / 10000.0

    prices = [float(x) for x in a.tranches.split(",") if x.strip()] if a.tranches else ([a.entry] if a.entry else [])
    if not prices:
        reasons.append("--entry or --tranches is required")
    bad_ticks = off_grid([(f"tranche {i + 1}" if a.tranches else "entry", x) for i, x in enumerate(prices)] +
                         [("stop", a.stop), ("t1", a.t1), ("t2", a.t2)])
    if bad_ticks:
        reasons.append("prices must be on the one-cent grid (not rounded for you): " + ", ".join(bad_ticks))
    levels = prices + [x for x in (a.stop, a.t1, a.t2, a.market_price) if x is not None]
    if levels and min(levels) < MIN_PRICE:
        reasons.append(f"prices under ${MIN_PRICE:.2f} trade in sub-penny increments and are not supported "
                       "(the engine rounds levels to the cent)")
    for name in ("stop", "t1", "t2"):
        if getattr(a, name) is None:
            reasons.append(f"--{name} is required")
    weights, port_sec, wprobs = parse_sector_weights(a)
    reasons.extend(wprobs)
    reasons.extend(gate_reasons(a))
    warnings.extend(a._screen_warnings)
    base = dict(profile=a.profile, asset=a.asset, horizon=a.horizon, quote_status=a.quote_status,
                quote=dict(time=a.quote_time or None, source=a.quote_source or None, status=a.quote_status,
                           delay_min=a.quote_delay_min, market_price=a.market_price, valid_for=QUOTE_VALIDITY),
                stop_orders=a.stop_orders, cash_accounting=accounting, warnings=warnings, broker=a._broker_name,
                shariah=getattr(a, "_shariah_summary", None), boycott=getattr(a, "_boycott_summary", None),
                assumptions=dict(fee_schedule=a._fee_source, fx_conversion_charged=a._convert, friction_bps_per_side=a.friction_bps, gap_pct=a.gap_pct))
    if reasons:
        return dict(verdict="NO TRADE", reasons=reasons, placement_status="not placeable", **base)

    if max(prices) >= a.t1 or a.stop >= min(prices):
        reasons.append("levels must satisfy stop < every entry and every entry < T1")
    if a.t1 > a.t2:
        reasons.append("T1 must be <= T2")
    mblock, mwatch = market_check(a, prices)
    reasons.extend(mblock)
    max_dist = MAX_STOP_DISTANCE[a.horizon][a.profile]
    worst = (max(prices) - a.stop) / max(prices)
    if worst > max_dist + 1e-9:
        reasons.append(f"stop is {100 * worst:.1f}% below the highest entry; the {a.profile} {a.horizon}-term "
                       f"limit is {100 * max_dist:g}%")

    if a.asset == "stock":
        asset_cap = p["stock_cap"] * a.portfolio - a.ticker_exposure
    elif a.asset == "etf":
        asset_cap = p["etf_cap"] * a.portfolio - a.ticker_exposure
    else:
        asset_cap = p["metals_max"] * a.portfolio - a.metals_exposure
    sector_limit = p["sector"] * a.portfolio
    rooms = sector_rooms(weights, port_sec, sector_limit) if a.asset in COUNTED_ASSETS else {}
    sector_room = {s: r for s, (r, _) in rooms.items()}
    sector_cap_value = min((r / w for r, w in rooms.values()), default=float("inf"))
    if port_sec.get(UNCLASSIFIED, 0) > 0 and a.asset in COUNTED_ASSETS:
        warnings.append(f"${port_sec[UNCLASSIFIED]:,.2f} of current stock/ETF exposure has no sector data; it is "
                        "counted against every sector (worst case). Add sector weights to free up room.")

    risk_budget = p["risk"] * a.portfolio
    assumed_unq = 0.0
    if a.unquantified_holdings > 0:
        if a.unquantified_loss_pct is None:
            reasons.append(f"{a.unquantified_holdings} holding(s) have unquantified risk: set a stop/review level "
                           f"or pass --unquantified-loss-pct ({UNQ_MIN_PCT:g}-{UNQ_MAX_PCT:g}) before adding new price risk")
        else:
            assumed_unq = a.unquantified_value * a.unquantified_loss_pct / 100
            warnings.append(f"unquantified holdings counted at an assumed {a.unquantified_loss_pct:g}% loss "
                            f"(${assumed_unq:,.2f}) against the open-risk limit")
    open_room = p["open_risk"] * a.portfolio - (a.open_stop_risk + a.open_review_risk + assumed_unq)

    base["limits"] = dict(position_cap_total=round(asset_cap + (a.ticker_exposure if a.asset in COUNTED_ASSETS else 0), 2),
                          existing_ticker_exposure=round(a.ticker_exposure, 2), position_room=round(asset_cap, 2),
                          risk_budget_per_idea=round(risk_budget, 2), open_risk_room=round(open_room, 2),
                          sector_room={s: round(r, 2) for s, r in sector_room.items()},
                          max_position_from_sectors=None if sector_cap_value == float("inf") else round(sector_cap_value, 2),
                          max_stop_distance_pct=100 * max_dist,
                          open_positions=a.open_positions, max_positions=p["max_positions"])

    if not reasons:
        if a.asset in COUNTED_ASSETS and a.ticker_exposure == 0 and a.open_positions >= p["max_positions"]:
            reasons.append("maximum number of stock/ETF positions reached")
        if open_room <= 0:
            reasons.append("portfolio open-risk limit already used")
        breached = [s for s, r in sector_room.items() if r <= 0]
        if breached:
            reasons.append(f"sector cap reached: {', '.join(breached)}")
        if asset_cap < a.min_order:
            reasons.append(f"{a.asset} position cap reached for {a.ticker.upper() or 'this asset'} "
                           f"(already ${a.ticker_exposure:,.2f})" if a.asset in COUNTED_ASSETS
                           else "metals allocation cap reached")
        if available < a.min_order:
            reasons.append("cash floor and unfilled commitments leave less than the minimum order")

    k = len(prices)

    def plan(n):
        parts = split_shares(n, k)
        return parts, [q * px for q, px in zip(parts, prices)]

    def planned_loss(n):
        parts, buys = plan(n)
        cost = sum(b + fee(b, q) + fr * b for q, b in zip(parts, buys))
        out = n * a.stop
        return cost - (out - fee(out, n, side="sell") - fr * out)

    best = None
    if not reasons:
        best = best_quantity(k, plan, planned_loss, fee, min(asset_cap, sector_cap_value, available),
                             available, min(risk_budget, open_room), a.min_order, min(prices))
        if best is None:
            reasons.append(f"no whole-share quantity fits the caps, risk budget, cash and the ${a.min_order:,.0f} "
                           "minimum per order")
    if best is None:
        return dict(verdict="NO TRADE", reasons=reasons, placement_status="not placeable", **base)

    n = best
    parts, buys = plan(n)
    buy_fees = [fee(b, q) for q, b in zip(parts, buys)]
    cost_basis = sum(b + f + fr * b for b, f in zip(buys, buy_fees))
    total_value = sum(buys)

    def net_exit(shares, price):
        v = shares * price
        return v - fee(v, shares, side="sell") - fr * v

    loss = planned_loss(n)
    gap_price = a.stop * (1 - a.gap_pct / 100)
    gap_loss = cost_basis - net_exit(n, gap_price)
    full_t1 = net_exit(n, a.t1) - cost_basis
    full_t2 = net_exit(n, a.t2) - cost_basis

    n1, n2 = n // 2, n - n // 2
    if n1 >= 1:
        bps = cost_basis / n
        realized_t1 = net_exit(n1, a.t1) - bps * n1
        rest_t2 = net_exit(n2, a.t2) - bps * n2
        combined = realized_t1 + rest_t2
        remaining_be = solve_price(bps * n2, n2, fee, fr)
        rem_check = net_exit(n2, remaining_be) - bps * n2
        whole_basis = bps * n2 - realized_t1
        whole_be = solve_price(whole_basis, n2, fee, fr) if whole_basis > 0 else 0.0
        can_raise = a.stop < remaining_be < a.t1
        partial = dict(feasible=True, sell_at_t1=n1, hold_for_t2=n2,
                       sell_fee_t1=round(fee(n1 * a.t1, n1, side="sell"), 2),
                       sell_fee_t2=round(fee(n2 * a.t2, n2, side="sell"), 2),
                       realized_at_t1=round(realized_t1, 2), remaining_at_t2=round(rest_t2, 2),
                       combined_net_profit=round(combined, 2),
                       stop_after_t1=dict(
                           keep_at_least=a.stop,
                           optional_raise_to=remaining_be if can_raise else None,
                           rule="never lower the stop after T1; raising it is optional and should fit the thesis"),
                       remaining_position_breakeven=remaining_be,
                       remaining_position_net_at_breakeven=round(rem_check, 4),
                       whole_trade_breakeven_after_t1=whole_be,
                       whole_trade_note="information only: NOT a stop level")
    else:
        combined = full_t1
        partial = dict(feasible=False, note="1-share position: single exit at T1")

    plan_rr = combined / loss
    if plan_rr < p["min_rr"]:
        reasons.append(f"net reward:risk of the exit plan {plan_rr:.3f} is below profile minimum {p['min_rr']}")

    q = quote_check(a)
    fxw = (f"account currency differs from {a.instrument_currency.upper()}: no exchange-rate model, so amounts "
           "and limits are not normalized; plan is research only" if a._convert else None)
    watch = [x for x in (q, mwatch, fxw) if x]
    if reasons:
        verdict = "NO TRADE"
    elif watch:
        verdict = "WATCHLIST"
        reasons.extend(watch)
    else:
        verdict = "TRADE"

    hard = a.horizon in HARD_STOP_HORIZONS
    downside = dict(
        executable_stop_downside=round(loss, 2) if hard else 0.0,
        long_term_review_level_downside=0.0 if hard else round(loss, 2),
        note=("planned loss at a hard stop; not a guaranteed maximum" if hard else
              "scenario only: a review level is not an exit and the position can fall further"))
    proj_sectors = {s: round(port_sec.get(s, 0.0) + total_value * w, 2) for s, w in weights.items()}
    tranche_rows = [dict(price=px, shares=q_, order_value=round(b, 2), buy_fee=round(f, 2))
                    for px, q_, b, f in zip(prices, parts, buys, buy_fees)]
    res = reservation(total_value, sum(buy_fees), buys[0] + buy_fees[0],
                      sum(b + f for b, f in zip(buys[1:], buy_fees[1:])))

    return dict(
        verdict=verdict, reasons=reasons, placement_status=placement(verdict, a, prices[0], parts[0]), **base,
        ticker=a.ticker.upper(), isin=a.isin, stop_level=a.stop, t1_level=a.t1, t2_level=a.t2,
        shares=n, average_entry=round(total_value / n, 4), tranches=tranche_rows,
        total_order_value=res["order_value"], total_buy_fees=res["buy_fees"], reservation=res,
        cash_for_first_order=res["first_order_total"], commit_for_later_tranches=res["later_orders_total"],
        total_cost_incl_est_friction=round(cost_basis, 2),
        fee_adjusted_breakeven_price=solve_price(cost_basis, n, fee, fr),
        downside=downside, downside_pct_portfolio=round(100 * loss / a.portfolio, 3),
        portfolio_open_risk_after=dict(
            executable_stop=round(a.open_stop_risk + downside["executable_stop_downside"], 2),
            review_level=round(a.open_review_risk + downside["long_term_review_level_downside"], 2),
            unquantified_holdings=a.unquantified_holdings),
        gap_scenario=dict(fill_price=round(gap_price, 2), loss=round(gap_loss, 2)),
        net_profit_full_exit_t1=round(full_t1, 2), net_profit_full_exit_t2=round(full_t2, 2),
        net_rr_full_t1=round(full_t1 / loss, 3), net_rr_full_t2=round(full_t2 / loss, 3),
        partial_exit_plan=partial, net_rr_of_plan=round(plan_rr, 3),
        projected_sector_exposure=proj_sectors,
        projected_ticker_exposure=round(a.ticker_exposure + total_value, 2),
        position_pct_portfolio=round(100 * (a.ticker_exposure + total_value) / a.portfolio, 2),
    )


# --------------------------------------------------------------------------- entry points
def setup_fees(a):
    if a.broker:
        path = a.brokers or os.path.join(os.path.dirname(os.path.abspath(__file__)), "brokers.json")
        prof, _ = broker_profile(a.broker, path)
        acct = (a.account_currency or prof.get("currency") or "USD").upper()
        a._convert = acct != a.instrument_currency.upper()
        prof, fee = broker_profile(a.broker, path, convert=a._convert)
        a._broker_name, a._fee_source = prof["name"], prof.get("source", "unknown")
        if a.min_order is None:
            a.min_order = prof.get("min_order") or 0.0
        return fee
    if a.fee_model:
        spec = dict(model=a.fee_model, rate=a.fee_rate, min=a.fee_min, max=a.fee_max,
                    per_share=a.fee_per_share, max_pct=a.fee_max_pct, flat=a.fee_flat, fx_pct=a.fx_pct)
        a._convert = (a.account_currency or "USD").upper() != a.instrument_currency.upper()
        fee = make_fee_model({k: v for k, v in spec.items() if v is not None}, convert=a._convert)
        a._broker_name, a._fee_source = "custom", "user-provided"
        if a.min_order is None:
            a.min_order = 0.0
        return fee
    raise ValueError("no fee schedule: pass --broker ID or --fee-model with its fields")


def compute(a):
    res = _compute(a)
    res.setdefault("ticker", (a.ticker or "").upper())
    res.setdefault("asset", a.asset)
    res.setdefault("placement_status", "not placeable")
    return res


def _compute(a):
    a._broker_name, a._fee_source, a._convert, a._screen_warnings = None, None, False, []
    try:
        fee = setup_fees(a)
    except ValueError as e:
        return dict(verdict="NO TRADE", reasons=[f"fee schedule: {e}"])
    p = PROFILES[a.profile]
    blocks = load_state(a)
    if blocks:
        return dict(verdict="NO TRADE", reasons=blocks)
    if a.portfolio is None or a.cash is None:
        return dict(verdict="NO TRADE", reasons=["--portfolio and --cash are required unless --state is given"])
    bad = validate_inputs(a)
    if bad:
        return dict(verdict="NO TRADE", reasons=["invalid input: " + "; ".join(bad)])
    return compute_tbill(a, fee, p) if a.asset == "tbill" else compute_price(a, fee, p)


def main(argv=None):
    try:
        out = compute(build_parser().parse_args(argv))
    except SystemExit:
        raise
    except Exception as e:  # fail safe: never let a crash look like a result
        out = dict(verdict="NO TRADE", reasons=[f"engine error: {e}"], placement_status="not placeable")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
