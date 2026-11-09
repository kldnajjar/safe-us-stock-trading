#!/usr/bin/env python3
"""Portfolio state engine for the safe-us-stock-trading skill (v4.5).

Builds the ACTUAL portfolio from what the user's app shows, then optionally a
PROJECTED portfolio that adds accepted-but-unexecuted plans. Recommendations only
ever change the projected state; the actual state changes only when the user
reports executed fills.

Input JSON (--input FILE):
{
  "cash": 9000,                         settled cash shown in the app
  "cash_includes_open_orders": false,   true if the app already holds back cash for open orders
  "holdings": [                         exactly what the app shows (includes every fill so far)
    {"ticker": "ABC", "asset": "stock|etf|metal|tbill", "shares": 10, "avg_cost": 100,
     "price": 104, "level": 94, "level_type": "hard|review|none",
     "sector_weights": {"Tech": 1}}
  ],
  "orders": [                           working orders; filled orders are already in holdings
    {"id": "ABC-2", "ticker": "ABC", "asset": "etf", "side": "buy|sell", "limit": 97, "shares": 6,
     "status": "open|partial|filled|cancelled", "filled_shares": 0,
     "level": 88, "level_type": "review", "sector_weights": {"Tech": 0.5, "Health": 0.5}}
  ]
}

Usage:
  python3 portfolio_state.py --input state.json --broker ID               -> actual state
  python3 portfolio_state.py --input state.json --broker ID --plans a.json b.json  -> projected state
     (each plan file is a size_trade.py JSON output with verdict TRADE)

The output's "size_trade_args" block can be passed to size_trade.py with --state.

Validation (v4.4): any invalid input is an error, which makes the state unusable (reconciliation required):
  * sector_weights: an object of finite weights, each 0-1, summing to 1 (+/- 0.01; put any unknown share
    under "Unclassified")
  * holdings and buy orders in stocks/ETFs with no sector_weights are counted under "Unclassified",
    which size_trade.py treats as possibly being in any sector (worst case), never as zero
  * every working order states "side": "buy" or "sell", and a status of open|partial|filled|cancelled
  * shares is a positive whole number; filled_shares a whole number with 0 <= filled_shares <= shares;
    open means nothing filled, partial means some but not all filled
  * BUY orders reserve cash and add pending exposure and risk
  * SELL orders reserve nothing and add no exposure: the shares stay in holdings until the sale executes.
    They are reported as shares reserved for sale and must not exceed the shares held (no short selling).
"""
import argparse, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fees import broker_profile  # noqa: E402

COUNTED = {"stock", "etf"}
STATUSES = ("open", "partial", "filled", "cancelled")
SECTOR_SUM_TOL = 0.01


def check_weights(where, weights):
    """Raise ValueError unless weights is None/empty or a valid {sector: fraction} summing to 1."""
    if weights in (None, {}):
        return
    if not isinstance(weights, dict):
        raise ValueError(f"{where}: sector_weights must be an object")
    for k, w in weights.items():
        if not isinstance(k, str) or not k.strip():
            raise ValueError(f"{where}: sector names must be non-empty text")
        if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or not 0 <= w <= 1:
            raise ValueError(f"{where}: invalid sector weight {k}={w} (must be between 0 and 1)")
    if abs(sum(weights.values()) - 1) > SECTOR_SUM_TOL:
        raise ValueError(f"{where}: invalid sector weights, they sum to {sum(weights.values()):.4f}, not 1 "
                         "(put any unknown share under \"Unclassified\")")


VALID_ASSETS = {"stock", "etf", "metal", "tbill"}


def plan_is_trade(pl):
    """A real TRADE plan: verdict TRADE, no reasons, placeable, with shares. Guards against edited files."""
    return (pl.get("verdict") == "TRADE" and not pl.get("reasons") and (pl.get("shares") or 0) >= 1
            and str(pl.get("placement_status", "")).startswith(("provisional", "ready")))


def add_sectors(acc, weights, value):
    for s, w in (weights or {}).items():
        acc[s] = acc.get(s, 0.0) + value * w


def build(state, plans=(), fee=None):
    if fee is None:
        raise ValueError("a broker fee schedule is required (--broker)")
    for k in ("cash",):
        if not isinstance(state.get(k), (int, float)) or state[k] < 0:
            raise ValueError("state 'cash' must be a number >= 0")
    warnings, breached, unquantified = [], [], []
    seen_h = [str(h.get("ticker", "")).upper() for h in state.get("holdings") or []]
    dup_h = sorted({t for t in seen_h if seen_h.count(t) > 1})
    if dup_h:
        raise ValueError(f"holdings list {', '.join(dup_h)} more than once: combine the lots into one row "
                         "(total shares, weighted average cost), exactly as the app shows the position")
    seen_o = [o.get("id") for o in state.get("orders") or [] if o.get("id")]
    dup_o = sorted({i for i in seen_o if seen_o.count(i) > 1})
    if dup_o:
        raise ValueError(f"order id(s) {', '.join(map(str, dup_o))} appear more than once: each working order once")
    acc = dict(sectors={}, tickers={}, metals=0.0, tbill=0.0, stop=0.0, review=0.0, unq_value=0.0, positions=set())

    def add_exposure(ticker, asset, value, weights):
        t = ticker.upper()
        acc["tickers"][t] = acc["tickers"].get(t, 0.0) + value
        if asset in COUNTED:
            acc["positions"].add(t)
            if not weights:
                warnings.append(f"{t}: no sector weights; its ${value:,.2f} is counted as Unclassified, which the "
                                "engine treats as possibly being in any sector")
                weights = {"Unclassified": 1.0}
            add_sectors(acc["sectors"], weights, value)
        elif asset == "metal":
            acc["metals"] += value
        elif asset == "tbill":
            acc["tbill"] += value

    def add_risk(ticker, asset, shares, price, level, level_type, value, buy_fee=0.0):
        """Downside from `price` to `level` (plus the buy fee still to be paid, for unfilled buy orders)."""
        if asset == "tbill":
            return "rate risk only (see size_trade tbill path)"
        if level_type == "none" or level is None:
            unquantified.append(ticker)
            acc["unq_value"] += value
            return "UNQUANTIFIED"
        if level >= price:
            breached.append(ticker)
            acc["unq_value"] += value
            return "BREACHED: price is at or below the stop/review level; reconcile before any new trade"
        d = shares * (price - level) + fee(shares * level, shares, side="sell") + buy_fee
        acc["stop" if level_type == "hard" else "review"] += d
        return round(d, 2)

    market_value, rows = 0.0, []
    for h in state.get("holdings", []):
        for k in ("shares", "price"):
            if not isinstance(h.get(k), (int, float)) or h[k] <= 0:
                raise ValueError(f"holding {h.get('ticker')}: '{k}' must be a positive number")
        check_weights(f"holding {h.get('ticker')}", h.get("sector_weights"))
        mv = h["shares"] * h["price"]
        market_value += mv
        asset = h.get("asset", "stock")
        if asset not in VALID_ASSETS:
            raise ValueError(f"holding {h.get('ticker')}: asset must be one of {', '.join(sorted(VALID_ASSETS))} "
                             f"(got {asset!r})")
        add_exposure(h["ticker"], asset, mv, h.get("sector_weights"))
        row = dict(ticker=h["ticker"].upper(), asset=asset, market_value=round(mv, 2),
                   unrealized_pnl=round(mv - h["shares"] * h.get("avg_cost", h["price"]), 2))
        row["downside"] = add_risk(h["ticker"].upper(), asset, h["shares"], h["price"], h.get("level"),
                                   h.get("level_type", "none"), mv)
        if isinstance(row["downside"], float):
            row["downside_type"] = h.get("level_type")
        rows.append(row)

    # working orders: BUYS reserve cash AND count as pending exposure and risk; SELLS reserve nothing
    held = {}
    for h in state.get("holdings", []):
        held[h["ticker"].upper()] = held.get(h["ticker"].upper(), 0) + h["shares"]
    to_sell = {}
    committed, order_rows = 0.0, []
    for o in state.get("orders", []):
        st = o.get("status")
        if st not in STATUSES:
            raise ValueError(f"order {o.get('id')}: unknown status {st!r} (use one of {', '.join(STATUSES)})")
        sh_, fl_ = o.get("shares"), o.get("filled_shares", 0)
        if isinstance(sh_, bool) or not isinstance(sh_, (int, float)) or sh_ != int(sh_) or sh_ <= 0:
            raise ValueError(f"order {o.get('id')}: 'shares' must be a positive whole number (got {sh_!r})")
        if isinstance(fl_, bool) or not isinstance(fl_, (int, float)) or fl_ != fl_ or fl_ != int(fl_) or fl_ < 0:
            raise ValueError(f"order {o.get('id')}: 'filled_shares' must be a whole number >= 0 (got {fl_!r})")
        if fl_ > sh_:
            raise ValueError(f"order {o.get('id')}: filled_shares {fl_} is more than the order's {sh_} shares; "
                             "reconcile with the app")
        if st == "open" and fl_ != 0:
            raise ValueError(f"order {o.get('id')}: status 'open' but {fl_} shares filled; use 'partial'")
        if st == "partial" and not 0 < fl_ < sh_:
            raise ValueError(f"order {o.get('id')}: status 'partial' needs 0 < filled_shares < shares (got {fl_}/{sh_})")
        side = o.get("side")
        if side not in ("buy", "sell"):
            raise ValueError(f"order {o.get('id')}: 'side' must be 'buy' or 'sell' (got {side!r})")
        check_weights(f"order {o.get('id')}", o.get("sector_weights"))
        if st in ("filled", "cancelled"):
            order_rows.append(dict(id=o.get("id"), status=st, commitment=0.0,
                                   note="filled orders are in holdings; cancelled orders release their reservation"))
            continue
        remaining = o["shares"] - o.get("filled_shares", 0)
        if remaining <= 0:
            order_rows.append(dict(id=o.get("id"), status=st, commitment=0.0, note="nothing left to fill"))
            continue
        if not isinstance(o.get("limit"), (int, float)) or o["limit"] <= 0:
            raise ValueError(f"order {o.get('id')}: 'limit' must be a positive number")
        if side == "sell":
            t = o["ticker"].upper()
            to_sell[t] = to_sell.get(t, 0) + remaining
            if to_sell[t] > held.get(t, 0):
                raise ValueError(f"order {o.get('id')}: sell orders for {t} ({to_sell[t]} shares) exceed the "
                                 f"{held.get(t, 0)} shares held; short selling is not supported")
            order_rows.append(dict(id=o.get("id"), side="sell", status=st, remaining_shares=remaining,
                                   commitment=0.0, note="sell order: no cash reserved and no exposure added; "
                                   "the shares stay in holdings until the sale executes"))
            continue
        value = remaining * o["limit"]
        c = value + fee(value, remaining)
        if value < 100:
            warnings.append(f"order {o.get('id')}: remaining {remaining} shares (${value:.2f}) is below the $100 minimum; cancel or resize")
        committed += c
        asset = o.get("asset", "stock")
        if asset not in VALID_ASSETS:
            raise ValueError(f"order {o.get('id') or o.get('ticker')}: asset must be one of "
                             f"{', '.join(sorted(VALID_ASSETS))} (got {asset!r})")
        add_exposure(o["ticker"], asset, value, o.get("sector_weights"))
        risk = add_risk(o["ticker"].upper(), asset, remaining, o["limit"], o.get("level"), o.get("level_type", "none"), value,
                        buy_fee=fee(value, remaining))     # treasury audit: the unpaid buy fee is part of the loss
        order_rows.append(dict(id=o.get("id"), side="buy", status=st, remaining_shares=remaining,
                               commitment=round(c, 2), pending_downside=risk))

    cash = state["cash"]
    app_reserves = bool(state.get("cash_includes_open_orders"))
    committed_for_engine = 0.0 if app_reserves else committed
    if app_reserves:
        warnings.append("app already reserves cash for open orders: commitments are not subtracted again")

    actual = dict(
        label="actual (holdings + working orders as shown in the app)", cash=round(cash, 2),
        holdings_value=round(market_value, 2),
        portfolio_value=round(cash + market_value + (committed if app_reserves else 0), 2),
        open_order_commitments=round(committed, 2),
        executable_stop_downside=round(acc["stop"], 2), review_level_downside=round(acc["review"], 2),
        unquantified=unquantified, breached=breached, unquantified_value=round(acc["unq_value"], 2),
        sector_exposure={k: round(v, 2) for k, v in acc["sectors"].items()},
        ticker_exposure={k: round(v, 2) for k, v in acc["tickers"].items()},
        metals_exposure=round(acc["metals"], 2), tbill_exposure=round(acc["tbill"], 2),
        stock_etf_positions=len(acc["positions"]), holdings=rows, orders=order_rows,
        shares_reserved_for_sale=to_sell,
    )

    # projected: accepted plans are added as reserved orders, never as holdings
    proj = None
    if plans:
        p_sec, p_tick = dict(actual["sector_exposure"]), dict(actual["ticker_exposure"])
        p_stop, p_rev, p_comm = acc["stop"], acc["review"], committed_for_engine
        p_metals, p_tbill, p_pos = acc["metals"], acc["tbill"], set(acc["positions"])
        planned, seen = [], set()
        for pl in plans:
            if pl.get("verdict") == "TRADE" and not plan_is_trade(pl):
                raise ValueError(f"plan for {pl.get('ticker')} says TRADE but carries reasons or is not placeable "
                                 "(edited?): re-run size_trade.py")
            key = (str(pl.get("ticker")).upper(), json.dumps(pl.get("tranches"), sort_keys=True),
                   (pl.get("quote") or {}).get("time"))
            if pl.get("verdict") == "TRADE" and key in seen:
                raise ValueError(f"plan for {pl.get('ticker')} is listed twice: pass each plan once")
            seen.add(key)
            if pl.get("verdict") != "TRADE":
                warnings.append(f"plan for {pl.get('ticker') or pl.get('asset')} skipped: verdict {pl.get('verdict')}")
                continue
            r = pl.get("reservation")
            if not r:
                raise ValueError(f"plan for {pl.get('ticker')} has no 'reservation' block (made by an older engine?)")
            t, asset = (pl.get("ticker") or "").upper(), pl.get("asset")
            p_comm += r["total"]
            p_tick[t] = p_tick.get(t, 0.0) + r["order_value"]
            if asset in COUNTED:
                w = pl.get("sector_weights")
                if not isinstance(w, dict):
                    raise ValueError(f"plan for {t} has no sector_weights (made by an older engine?): re-run size_trade.py")
                add_sectors(p_sec, w, r["order_value"])     # add this plan's own money, independent of order
            dn = pl.get("downside") or {}
            p_stop += dn.get("executable_stop_downside", 0.0)
            p_rev += dn.get("long_term_review_level_downside", 0.0)
            if asset in COUNTED:
                p_pos.add(t)
            elif asset == "metal":
                p_metals += r["order_value"]
            elif asset == "tbill":
                p_tbill += r["order_value"]
            planned.append(dict(ticker=t, asset=asset, reserved=r["total"]))
        proj = dict(label="projected (not executed)", planned=planned,
                    commitments_incl_plans=round(p_comm, 2),
                    executable_stop_downside=round(p_stop, 2), review_level_downside=round(p_rev, 2),
                    sector_exposure={k: round(v, 2) for k, v in p_sec.items()},
                    ticker_exposure={k: round(v, 2) for k, v in p_tick.items()},
                    metals_exposure=round(p_metals, 2), tbill_exposure=round(p_tbill, 2),
                    stock_etf_positions=len(p_pos))

    base = proj or {}
    args = dict(
        portfolio=actual["portfolio_value"], cash=actual["cash"],
        committed=base.get("commitments_incl_plans", committed_for_engine),
        portfolio_sectors=base.get("sector_exposure", actual["sector_exposure"]),
        ticker_exposure=base.get("ticker_exposure", actual["ticker_exposure"]),
        open_stop_risk=base.get("executable_stop_downside", actual["executable_stop_downside"]),
        open_review_risk=base.get("review_level_downside", actual["review_level_downside"]),
        unquantified_holdings=len(unquantified) + len(breached),
        unquantified_value=round(acc["unq_value"], 2),
        metals_exposure=base.get("metals_exposure", actual["metals_exposure"]),
        tbill_exposure=base.get("tbill_exposure", actual["tbill_exposure"]),
        open_positions=base.get("stock_etf_positions", actual["stock_etf_positions"]),
    )
    return dict(reconciliation_required=bool(breached), actual=actual, projected=proj,
                size_trade_args=args, warnings=warnings)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--plans", nargs="*", default=[])
    ap.add_argument("--broker", required=True, help="profile id in brokers.json")
    ap.add_argument("--brokers", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "brokers.json"))
    a = ap.parse_args(argv)
    try:
        with open(a.input) as f:
            state = json.load(f)
        plans = []
        for p in a.plans:
            with open(p) as f:
                plans.append(json.load(f))
        _, fee = broker_profile(a.broker, a.brokers)
        out = build(state, plans, fee)
    except Exception as e:
        out = dict(reconciliation_required=True, error=f"state error: {e}",
                   warnings=["state could not be built; treat as WATCHLIST only"])
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
