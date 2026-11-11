#!/usr/bin/env python3
"""Money plan for the whole account (v5.2): WHEN to invest and in WHAT KIND of thing.

Built only from the user's own state and the limits of their risk level (the same PROFILES the sizing
engine enforces). It names no stock and predicts nothing: each step is "run the skill on this day with up
to this much", and the names come from that day's fresh prices and checks. Spreading the money over
several steps is the user's choice (--steps); it lowers the risk of putting everything in on a bad day,
it does not raise the expected return.

  python3 money_plan.py --state ACTUAL.json --profile safe|balanced|aggressive \\
      [--amount USD] [--steps 4] [--every-days 7] [--start YYYY-MM-DD] > MONEY_PLAN.json
"""
import argparse, datetime as dt, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_clock as mc  # noqa: E402
from size_trade import PROFILES  # noqa: E402


def next_session(day):
    """The first NYSE trading day on or after `day`."""
    for _ in range(15):
        if mc.session(day)[0]:
            return day
        day += dt.timedelta(days=1)
    return day


def down2(x):
    return math.floor(x * 100) / 100.0


def build(state, profile, amount=None, steps=4, every_days=7, start=None):
    p, a = PROFILES[profile], (state or {}).get("actual") or {}
    pv, cash = a.get("portfolio_value"), a.get("cash")
    if not isinstance(pv, (int, float)) or not isinstance(cash, (int, float)) or pv <= 0:
        raise ValueError("state has no portfolio value / cash: build it with portfolio_state.py first")
    if not 1 <= steps <= 12 or not 1 <= every_days <= 90:
        raise ValueError("--steps must be 1 to 12 and --every-days 1 to 90")
    floor = p["cash_floor"] * pv
    free = max(0.0, cash - (a.get("open_order_commitments") or 0.0) - floor)
    if amount is not None and (not math.isfinite(amount) or amount <= 0):
        raise ValueError("--amount must be a positive number")
    invest = free if amount is None else min(amount, free)
    positions_left = max(0, p["max_positions"] - (a.get("stock_etf_positions") or 0))
    metals_room = max(0.0, p["metals_max"] * pv - (a.get("metals_exposure") or 0.0))
    used_risk = (a.get("executable_stop_downside") or 0.0) + (a.get("review_level_downside") or 0.0)
    sectors = a.get("sector_exposure") or {}
    top = max(sectors.items(), key=lambda kv: kv[1]) if sectors else (None, 0.0)
    blockers = []
    if state.get("reconciliation_required") or a.get("breached"):
        blockers.append("a holding is past its stop: fix it before any new buy")
    if a.get("unquantified"):
        blockers.append("holding(s) with no stop: " + ", ".join(a["unquantified"])
                        + ". Set a stop, or their risk is counted with an assumed loss")
    limits = dict(
        safety_cash=round(floor, 2), free_to_invest=down2(free), planned_amount=down2(invest),
        max_one_company=down2(p["stock_cap"] * pv), max_one_fund=down2(p["etf_cap"] * pv),
        gold_silver_room=down2(metals_room), max_one_sector=down2(p["sector"] * pv),
        biggest_sector=dict(name=top[0], amount=round(top[1], 2)) if top[0] else None,
        positions_left=positions_left, loss_limit_per_idea=down2(p["risk"] * pv),
        total_risk_room=down2(max(0.0, p["open_risk"] * pv - used_risk)))
    first = next_session(start or mc.to_new_york(mc.CLOCK()).date())
    per_step = down2(invest / steps) if steps else 0.0
    rows, day = [], first
    for i in range(1, steps + 1):
        rows.append(dict(step=i, day=day.isoformat(), weekday=day.strftime("%A"),
                         opens_new_york=f"{day.isoformat()} 09:30", up_to=per_step))
        day = next_session(day + dt.timedelta(days=every_days))
    kinds = []
    if metals_room > 0:
        kinds.append(dict(kind="gold or silver fund (real metal)", up_to=limits["gold_silver_room"]))
    kinds.append(dict(kind="broad fund that passes both checks", up_to=limits["max_one_fund"]))
    kinds.append(dict(kind="single company that passes both checks", up_to=limits["max_one_company"],
                      note=f"each; {positions_left} more thing(s) allowed"))
    return dict(schema="money-plan/1", profile=profile, portfolio_value=round(pv, 2), cash=round(cash, 2),
                limits=limits, kinds=kinds, steps=rows, steps_count=steps, every_days=every_days,
                blockers=blockers,
                rules=["each step = run the skill that day after the US market opens; names come from that "
                       "day's prices and checks",
                       "money not used in a step stays cash; it does not roll into a bigger next step",
                       "a step with no idea that passes is skipped: no buy is fine",
                       "stop adding when the total-risk room is used up",
                       "steps spread the timing risk; they do not make a profit more likely"])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--state", required=True)
    ap.add_argument("--profile", choices=sorted(PROFILES), required=True)
    ap.add_argument("--amount", type=float)
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--every-days", type=int, default=7)
    ap.add_argument("--start", default="", help="YYYY-MM-DD; default: the next NYSE trading day")
    a = ap.parse_args(argv)
    try:
        with open(a.state) as f:
            state = json.load(f)
        out = build(state, a.profile, a.amount, a.steps, a.every_days,
                    dt.date.fromisoformat(a.start) if a.start else None)
    except (OSError, ValueError) as e:
        print(json.dumps(dict(error=str(e)), indent=1))
        sys.exit(1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
