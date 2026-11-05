#!/usr/bin/env python3
"""Simple ("caveman") output for the safe-us-stock-trading skill (v4.3).

Short plain lines. Every number is copied from the engine JSON; nothing is recomputed.

  python3 render_simple.py --plans PLAN1.json PLAN2.json \
      [--market "MARKET CALM. FED WAIT."] [--metals "GOLD WAIT."] [--events "JOBS FRI. CPI TUE."]
"""
import argparse, json, sys


def money(x):
    return f"${x:,.2f}"


def px(x):
    return f"{x:,.2f}"


def short_reason(r):
    r = (r or "").split(";")[0].split("(")[0].strip()
    return r[:90]


def halal_line(sh):
    if not sh or sh.get("mode") == "off":
        return []
    if sh.get("screened") is False:
        return ["  HALAL: NOT CHECKED. SCREEN NOT RUN."]
    word = {"PERMITTED": "OK", "REQUIRES_ACCEPTANCE": "YOU MUST OK", "EXCLUDED": "NO",
            "UNVERIFIED": "NOT CHECKED"}.get(sh.get("policy_decision"), "NOT CHECKED")
    meth = sh.get("methodology") or ""
    lines = [f"  HALAL: {word}" + (f" ({meth.split(',')[0]})" if meth else "")]
    p = sh.get("purification") or {}
    if p.get("status") == "DUE" and p.get("amount_usd") is not None:
        lines.append(f"  GIVE {money(p['amount_usd'])} TO CHARITY ({p.get('period')})")
    elif p.get("status") == "UNAVAILABLE":
        lines.append("  CHARITY AMOUNT: UNKNOWN (DATA MISSING)")
    return lines


def boycott_line(b):
    if not b or b.get("mode") == "off":
        return []
    if b.get("screened") is False:
        return ["  BOYCOTT: NOT CHECKED. SCREEN NOT RUN."]
    word = {"reviewed_no_match": "NOT ON LISTS", "flagged": "FLAGGED (YOU OK'D)",
            "excluded": "ON LIST", "unverified": "NOT CHECKED"}.get(str(b.get("status", "")).lower(), "NOT CHECKED")
    return [f"  BOYCOTT: {word}"]


def quote_line(d):
    q = d.get("quote") or {}
    if not q.get("time"):
        return ["  PRICE TIME: UNKNOWN"]
    status = q.get("status", "").upper()
    if q.get("delay_min"):
        status += f" {q['delay_min']}M"
    mp = f" PRICE {px(q['market_price'])}" if q.get("market_price") is not None else ""
    return [f"  PRICE SEEN {q['time']} ({status}, {q.get('source') or 'SOURCE?'}){mp}. GOOD ONLY FOR THIS PRICE."]


def render_trade(d, header=None):
    t = d.get("ticker") or d.get("asset", "?").upper()
    out = [header or f"BUY {t}"]
    tr = d.get("tranches") or []
    if len(tr) == 1:
        out.append(f"  PRICE {px(tr[0]['price'])} (LIMIT)  SHARES {tr[0]['shares']}  "
                   f"COST {money(d['total_order_value'] + d['total_buy_fees'])}")
    else:
        steps = ", ".join(f"{x['shares']} @ {px(x['price'])}" for x in tr)
        out.append(f"  BUY IN STEPS: {steps}")
        out.append(f"  SHARES {d['shares']}  COST {money(d['total_order_value'] + d['total_buy_fees'])}")
    dn = d["downside"]
    if d.get("horizon") == "long":
        out.append(f"  REVIEW IF BELOW {px(d['stop_level'])} (NOT AUTO SELL)  "
                   f"LOSS THERE {money(dn['long_term_review_level_downside'])}")
    else:
        out.append(f"  STOP {px(d['stop_level'])}  PLANNED LOSS AT STOP {money(dn['executable_stop_downside'])}")
    out.append(f"  LOSS CAN BE MORE. IF PRICE JUMPS DOWN: {money(d['gap_scenario']['loss'])}")
    pe = d["partial_exit_plan"]
    if pe.get("feasible"):
        out.append(f"  SELL {pe['sell_at_t1']} AT {px(d['t1_level'])}  SELL {pe['hold_for_t2']} AT {px(d['t2_level'])}")
        out.append(f"  PROFIT IF BOTH HIT {money(pe['combined_net_profit'])} (AFTER FEES)")
        st = pe["stop_after_t1"]
        line = f"  AFTER FIRST SELL: KEEP STOP {px(st['keep_at_least'])}. NEVER LOWER."
        if st.get("optional_raise_to") is not None:
            line += f" CAN RAISE TO {px(st['optional_raise_to'])} (REST NO LOSS)."
        out.append(line)
    else:
        out.append(f"  SELL ALL AT {px(d['t1_level'])}  PROFIT {money(d['net_profit_full_exit_t1'])} (AFTER FEES)")
    out += halal_line(d.get("shariah")) + boycott_line(d.get("boycott"))
    out += quote_line(d)
    if header:
        out.append("  NOT READY. GET LIVE PRICE. RUN AGAIN.")
    elif str(d.get("placement_status", "")).startswith("ready"):
        out.append("  READY. PRICE CAN STILL MOVE.")
    else:
        out.append("  CHECK PRICE IN APP FIRST.")
        if d.get("horizon") != "long" and d.get("stop_orders") != "yes":
            out.append("  CHECK APP CAN DO STOP ORDER. IF NOT: SET ALERT, SELL BY HAND.")
    return out


def warning_lines(d):
    out = []
    for w in d.get("warnings") or []:
        if w.startswith("SCREEN NOT RUN"):
            name = "HALAL" if "Shariah" in w else "BOYCOTT"
            out.append(f"  !! NOT SCREENED FOR {name}. YOU ASKED FLAG, BUT NO CHECK DONE. !!")
    return out


def render_tbill(d):
    sh = d.get("shariah") or {}
    extra = ["  HALAL: NO (INTEREST). SHOWN BECAUSE YOU SET FLAG ONLY."] if sh.get("mode") == "flag" else []
    return [f"PARK CASH IN {d.get('ticker') or 'T-BILL FUND'}"] + extra + [
            f"  SHARES {d['shares']}  COST {money(d['order_value'] + d['buy_fee'])}",
            f"  EARN ABOUT {money(d['expected_net_return'])} AFTER FEES (GUESS, NOT PROMISE)",
            f"  NEED {d['breakeven_holding_days']} DAYS JUST TO PAY FEES",
            "  CHECK PRICE IN APP FIRST."] + quote_line(d)


def render(plans, market="", metals="", events=""):
    lines = []
    first = next((d for d in plans if d.get("profile")), None)
    if first:
        lines.append(f"RISK: {str(first.get('profile')).upper()}. HOLD: {str(first.get('horizon') or 'n/a').upper()}.")
    if market:
        lines.append(f"MARKET: {market.upper()}")
    if metals:
        lines.append(f"GOLD/SILVER: {metals.upper()}")
    if events:
        lines.append(f"WATCH: {events.upper()}")
    if lines:
        lines.append("")
    buys, waits, nos = [], [], []
    for d in plans:
        t = (d.get("ticker") or d.get("asset", "?")).upper()
        v = d.get("verdict")
        if v == "TRADE":
            buys += (render_tbill(d) if d.get("asset") == "tbill" else render_trade(d)) + warning_lines(d) + [""]
        elif v == "WATCHLIST" and d.get("tranches"):
            head = f"WAIT {t}: {short_reason((d.get('reasons') or [''])[0])}"
            waits += render_trade(d, header=head + "\n  IF READY LATER, PLAN IS:") + warning_lines(d) + [""]
        elif v == "WATCHLIST":
            waits.append(f"WAIT {t}: {short_reason((d.get('reasons') or [''])[0])}")
        else:
            nos.append(f"NO BUY {t}: {short_reason((d.get('reasons') or ['no reason given'])[0])}")
    if not buys:
        lines += ["NO BUY TODAY. CASH OK.", ""]
    while waits and waits[-1] == "":
        waits.pop()
    lines += buys + waits + nos
    if waits or nos:
        lines.append("")
    lines.append("YOU DECIDE. YOU PLACE ORDER. NOT ADVICE.")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", nargs="+", required=True)
    ap.add_argument("--market", default="")
    ap.add_argument("--metals", default="")
    ap.add_argument("--events", default="")
    a = ap.parse_args(argv)
    plans = []
    for p in a.plans:
        with open(p) as f:
            plans.append(json.load(f))
    sys.stdout.write(render(plans, a.market, a.metals, a.events))


if __name__ == "__main__":
    main()
