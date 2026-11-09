#!/usr/bin/env python3
"""Trade journal for the safe-us-stock-trading skill (v4.6): does the skill actually make money?

Records every plan the user acted on and every real fill, then reports results after fees and
purification, in R (multiples of the planned loss at the stop), and against a benchmark fund
held over the same days. Paper and real trades are kept apart.

  python3 journal.py open   --journal JOURNAL.json --plan PLAN.json [--paper] [--id ID]
  python3 journal.py fill   --journal JOURNAL.json --id ID --side buy|sell --shares N --price P --fee F --date YYYY-MM-DD
  python3 journal.py purify --journal JOURNAL.json --id ID --amount USD          # charity paid for this trade
  python3 journal.py cancel --journal JOURNAL.json --id ID                        # plan not filled
  python3 journal.py report --journal JOURNAL.json [--benchmark BENCH.csv] [--paper|--real] [--json]

Fills are what the app shows (shares, price, the fee charged), never the plan's numbers.
A trade is closed when every bought share is sold. Open trades are listed, not scored.
The benchmark is a daily close file (date,close, oldest first) of a fund that passes both screens.
JOURNAL.json holds personal trades: it is git-ignored.
"""
import argparse, datetime as dt, hashlib, json, math, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import signals  # noqa: E402  (price file loader)
from portfolio_state import plan_is_trade  # noqa: E402

SCHEMA = "trade-journal/1"
MIN_SAMPLE = 20


class JournalError(Exception):
    pass


def load(path):
    if not os.path.isfile(path):
        return dict(schema=SCHEMA, trades=[])
    with open(path) as f:
        j = json.load(f)
    if j.get("schema") != SCHEMA:
        raise JournalError(f"{path} is not a trade journal")
    return j


def save(path, j):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(j, f, indent=2)
    os.replace(tmp, path)


def find(j, tid):
    for t in j["trades"]:
        if t["id"] == tid:
            return t
    raise JournalError(f"no trade with id {tid}")


def open_trade(j, plan, paper=False, tid=None):
    if plan.get("verdict") != "TRADE":
        raise JournalError(f"only a TRADE plan can be opened (this one is {plan.get('verdict')})")
    if not plan_is_trade(plan):
        raise JournalError("plan says TRADE but carries reasons or is not placeable (edited?): re-run size_trade.py")
    if plan.get("asset") == "tbill":
        raise JournalError("T-bill cash parking is not a scored trade")
    dn = plan.get("downside") or {}
    planned = dn.get("executable_stop_downside") or dn.get("long_term_review_level_downside")
    if not planned or planned <= 0:
        raise JournalError("plan has no planned loss at the stop")
    day = str((plan.get("quote") or {}).get("time") or dt.date.today().isoformat())[:10]
    tid = tid or f"{plan['ticker']}-{day}-{1 + sum(1 for t in j['trades'] if t['ticker'] == plan['ticker'])}"
    if any(t["id"] == tid for t in j["trades"]):
        raise JournalError(f"id {tid} already used")
    pe = plan.get("partial_exit_plan") or {}
    t = dict(id=tid, ticker=plan["ticker"], asset=plan.get("asset"), paper=bool(paper), status="open",
             plan=dict(horizon=plan.get("horizon"), profile=plan.get("profile"), entry=[x["price"] for x in plan.get("tranches") or []],
                       stop=plan.get("stop_level"), t1=plan.get("t1_level"), t2=plan.get("t2_level"),
                       shares=plan.get("shares"), planned_loss=planned,
                       planned_profit_both_targets=pe.get("combined_net_profit"),
                       quote_time=(plan.get("quote") or {}).get("time"),
                       shariah=(plan.get("shariah") or {}).get("policy_decision"),
                       boycott=(plan.get("boycott") or {}).get("status")),
             fills=[], purification_paid=0.0,
             audit=dict(plan_sha256=hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest(),
                        broker=plan.get("broker"), fee_schedule=(plan.get("assumptions") or {}).get("fee_schedule"),
                        placement_status=plan.get("placement_status"),
                        recorded_at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
    j["trades"].append(t)
    return t


def held(t):
    return sum(f["shares"] if f["side"] == "buy" else -f["shares"] for f in t["fills"])


def add_fill(j, tid, side, shares, price, fee, date):
    t = find(j, tid)
    if t["status"] != "open":
        raise JournalError(f"trade {tid} is {t['status']}")
    if side not in ("buy", "sell"):
        raise JournalError("side must be buy or sell")
    if not (isinstance(shares, int) and shares > 0):
        raise JournalError("shares must be a whole number above 0")
    for name, v in (("price", price), ("fee", fee)):
        if not math.isfinite(v) or v < 0 or (name == "price" and v == 0):
            raise JournalError(f"{name} must be a positive number" + (" or zero" if name == "fee" else ""))
    dt.date.fromisoformat(date)
    if not t["fills"] and side != "buy":
        raise JournalError("the first fill must be a buy")
    if t["fills"] and date < max(f["date"] for f in t["fills"]):
        raise JournalError(f"fill dated {date} is before an earlier recorded fill: add fills in order")
    if side == "sell" and shares > held(t):
        raise JournalError(f"cannot sell {shares}: only {held(t)} held (no short selling)")
    t["fills"].append(dict(side=side, shares=shares, price=price, fee=fee, date=date))
    if held(t) == 0 and any(f["side"] == "sell" for f in t["fills"]):
        t["status"] = "closed"
    return t


def score(t):
    buys = [f for f in t["fills"] if f["side"] == "buy"]
    sells = [f for f in t["fills"] if f["side"] == "sell"]
    cost = sum(f["shares"] * f["price"] + f["fee"] for f in buys)
    proceeds = sum(f["shares"] * f["price"] - f["fee"] for f in sells)
    fees = sum(f["fee"] for f in t["fills"])
    pnl = proceeds - cost - t.get("purification_paid", 0.0)
    bought = sum(f["shares"] for f in buys)
    planned_shares = t["plan"].get("shares") or bought or 1
    risk = t["plan"]["planned_loss"] * bought / planned_shares     # R scales with the shares actually bought
    dates = sorted(f["date"] for f in t["fills"])
    days = (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[0])).days if dates else 0
    return dict(id=t["id"], ticker=t["ticker"], paper=t["paper"], opened=dates[0] if dates else None,
                closed=dates[-1] if dates else None, days_held=days, cost=round(cost, 2), proceeds=round(proceeds, 2),
                fees=round(fees, 2), purification=round(t.get("purification_paid", 0.0), 2), pnl=round(pnl, 2),
                r=round(pnl / risk, 3) if risk > 0 else None, shares_bought=bought, planned_shares=planned_shares, return_pct=round(100 * pnl / cost, 2) if cost else None,
                hit_stop=bool(sells) and min(f["price"] for f in sells) <= (t["plan"]["stop"] or 0) + 1e-9)


def close_on_or_before(rows, day):
    best = None
    for r in rows:
        if r["date"] <= day:
            best = r
        else:
            break
    return best


def reconcile(j, state):
    """Treasury control: the journal's open real positions must match the shares the app shows."""
    app = {}
    for h in state.get("holdings") or []:
        app[str(h["ticker"]).upper()] = app.get(str(h["ticker"]).upper(), 0) + h["shares"]
    book = {}
    for t in j["trades"]:
        if t["status"] == "open" and not t["paper"]:
            book[t["ticker"]] = book.get(t["ticker"], 0) + held(t)
    rows = []
    for tk in sorted(set(app) | set(book)):
        a, b = app.get(tk, 0), book.get(tk, 0)
        rows.append(dict(ticker=tk, app_shares=a, journal_shares=b, difference=a - b,
                         status="MATCH" if a == b else "BREAK"))
    breaks = [r for r in rows if r["status"] == "BREAK"]
    return dict(schema="journal-reconcile/1", ok=not breaks, rows=rows,
                note=("every open real position matches the app" if not breaks else
                      "record the missing fills (or positions held before the journal) until the shares match"))


def report(j, bench_rows=None, which="all"):
    trades = [t for t in j["trades"] if which == "all" or (which == "paper") == t["paper"]]
    closed = [score(t) for t in trades if t["status"] == "closed"]
    opened = [dict(id=t["id"], ticker=t["ticker"], shares_held=held(t), paper=t["paper"])
              for t in trades if t["status"] == "open"]
    out = dict(schema="journal-report/1", which=which, closed_trades=len(closed), open_trades=opened,
               cancelled=sum(1 for t in trades if t["status"] == "cancelled"), trades=closed)
    if not closed:
        out["verdict"] = "no closed trades yet"
        return out
    wins = [c for c in closed if c["pnl"] > 0]
    losses = [c for c in closed if c["pnl"] <= 0]
    gross_win, gross_loss = sum(c["pnl"] for c in wins), -sum(c["pnl"] for c in losses)
    equity, peak, mdd = 0.0, 0.0, 0.0
    for c in sorted(closed, key=lambda c: c["closed"]):
        equity += c["pnl"]
        peak = max(peak, equity)
        mdd = max(mdd, peak - equity)
    n = len(closed)
    out.update(
        win_rate_pct=round(100 * len(wins) / n, 1),
        total_pnl=round(sum(c["pnl"] for c in closed), 2),
        total_fees=round(sum(c["fees"] for c in closed), 2),
        total_purification=round(sum(c["purification"] for c in closed), 2),
        avg_win=round(gross_win / len(wins), 2) if wins else None,
        avg_loss=round(-gross_loss / len(losses), 2) if losses else None,
        expectancy_usd=round(sum(c["pnl"] for c in closed) / n, 2),
        expectancy_r=round(sum(c["r"] for c in closed if c["r"] is not None) / max(1, sum(1 for c in closed if c["r"] is not None)), 3),
        profit_factor=round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        max_drawdown_usd=round(mdd, 2),
        stops_hit=sum(1 for c in closed if c["hit_stop"]),
        avg_days_held=round(sum(c["days_held"] for c in closed) / n, 1))
    if bench_rows:
        diffs, missing = [], 0
        for c in closed:
            a, b = close_on_or_before(bench_rows, c["opened"]), close_on_or_before(bench_rows, c["closed"])
            if not a or not b:
                missing += 1
                continue
            bench_pnl = c["cost"] * (b["close"] / a["close"] - 1)
            c["benchmark_pnl_same_days"] = round(bench_pnl, 2)
            diffs.append(c["pnl"] - bench_pnl)
        matched = [c for c in closed if "benchmark_pnl_same_days" in c]
        out["benchmark"] = dict(trades_compared=len(diffs), trades_without_prices=missing,
                                available=bool(diffs),
                                skill_pnl_on_compared=round(sum(c["pnl"] for c in matched), 2),
                                benchmark_pnl=round(sum(c["benchmark_pnl_same_days"] for c in matched), 2),
                                skill_minus_benchmark=round(sum(diffs), 2) if diffs else None,
                                note="same money in the benchmark fund over each compared trade's own days"
                                     + ("" if not missing else f"; {missing} trade(s) had no benchmark prices"))
    if n < MIN_SAMPLE:
        out["verdict"] = (f"too few closed trades to judge ({n}; need at least {MIN_SAMPLE}): keep paper trading "
                          "and logging")
    else:
        positive = out["expectancy_r"] > 0 and out["total_pnl"] > 0
        b = out.get("benchmark") or {}
        if not positive:
            out["verdict"] = "not working: results are not above zero after costs"
        elif not b.get("available"):
            out["verdict"] = "positive after costs (benchmark unavailable: no benchmark prices for these dates)"
        elif b["skill_minus_benchmark"] > 0:
            out["verdict"] = "positive after costs and ahead of the benchmark"
        else:
            out["verdict"] = "profitable but behind simply holding the benchmark fund"
    return out


def text(rep):
    if not rep["closed_trades"]:
        return f"JOURNAL: {rep['verdict'].upper()}. OPEN: {len(rep['open_trades'])}.\n"
    L = [f"JOURNAL ({rep['which'].upper()} TRADES): {rep['closed_trades']} CLOSED, {len(rep['open_trades'])} OPEN",
         f"  WIN RATE {rep['win_rate_pct']}%   AVERAGE RESULT {rep['expectancy_r']:+.2f}R (${rep['expectancy_usd']:,.2f})",
         f"  TOTAL ${rep['total_pnl']:,.2f} AFTER FEES ${rep['total_fees']:,.2f} AND CHARITY ${rep['total_purification']:,.2f}",
         f"  WORST DROP ${rep['max_drawdown_usd']:,.2f}   STOPS HIT {rep['stops_hit']}   AVG HOLD {rep['avg_days_held']} DAYS"]
    if rep.get("profit_factor") is not None:
        L.append(f"  PROFIT FACTOR {rep['profit_factor']} (WINS / LOSSES)")
    b = rep.get("benchmark")
    if b and b.get("available"):
        L.append(f"  BENCHMARK SAME DAYS ${b['benchmark_pnl']:,.2f} ON {b['trades_compared']} TRADES. "
                 f"SKILL MINUS BENCHMARK ${b['skill_minus_benchmark']:,.2f}")
    elif b:
        L.append("  BENCHMARK: NO PRICES FOR THESE DATES")
    L.append(f"  VERDICT: {rep['verdict'].upper()}")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("--plan", required=True)
    o.add_argument("--paper", action="store_true")
    o.add_argument("--id", default="")
    f = sub.add_parser("fill")
    f.add_argument("--id", required=True)
    f.add_argument("--side", required=True, choices=["buy", "sell"])
    f.add_argument("--shares", type=int, required=True)
    f.add_argument("--price", type=float, required=True)
    f.add_argument("--fee", type=float, required=True)
    f.add_argument("--date", required=True)
    pu = sub.add_parser("purify")
    pu.add_argument("--id", required=True)
    pu.add_argument("--amount", type=float, required=True)
    rc = sub.add_parser("reconcile")
    rc.add_argument("--state", required=True, help="STATE_IN.json: holdings exactly as the app shows them")
    c = sub.add_parser("cancel")
    c.add_argument("--id", required=True)
    r = sub.add_parser("report")
    r.add_argument("--benchmark", default="")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--paper", action="store_true")
    g.add_argument("--real", action="store_true")
    r.add_argument("--json", action="store_true")
    for p in (o, f, pu, c, r, rc):
        p.add_argument("--journal", required=True)
    a = ap.parse_args(argv)
    try:
        j = load(a.journal)
        if a.cmd == "reconcile":
            with open(a.state) as fh:
                out = reconcile(j, json.load(fh))
            print(json.dumps(out, indent=2))
            return 0 if out["ok"] else 1
        if a.cmd == "report":
            rep = report(j, signals.load_prices(a.benchmark) if a.benchmark else None,
                         "paper" if a.paper else "real" if a.real else "all")
            sys.stdout.write(json.dumps(rep, indent=2) + "\n" if a.json else text(rep))
            return 0
        if a.cmd == "open":
            with open(a.plan) as fh:
                t = open_trade(j, json.load(fh), a.paper, a.id or None)
        elif a.cmd == "fill":
            t = add_fill(j, a.id, a.side, a.shares, a.price, a.fee, a.date)
        elif a.cmd == "purify":
            t = find(j, a.id)
            if not math.isfinite(a.amount) or a.amount < 0:
                raise JournalError("amount must be zero or more")
            t["purification_paid"] = round(t.get("purification_paid", 0.0) + a.amount, 2)
        else:
            t = find(j, a.id)
            if t["fills"]:
                raise JournalError("trade has fills: sell the shares instead of cancelling")
            t["status"] = "cancelled"
        save(a.journal, j)
        print(json.dumps(dict(ok=True, id=t["id"], status=t["status"], shares_held=held(t)), indent=2))
        return 0
    except (JournalError, ValueError, OSError) as e:
        print(json.dumps(dict(ok=False, error=str(e)), indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
