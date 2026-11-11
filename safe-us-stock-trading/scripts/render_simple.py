#!/usr/bin/env python3
"""Simple ("caveman") output for the safe-us-stock-trading skill (v4.9).

Short plain lines. Every number is copied from the engine JSON; nothing is recomputed.
v4.8: every NO BUY and WAIT prints ALL its reasons in plain words, what to do about each,
and the engine's full reason text; every plan prints the sources it was built on.

  python3 render_simple.py --plans PLAN1.json PLAN2.json \
      [--market "MARKET CALM. FED WAIT."] [--metals "GOLD WAIT."] [--events "JOBS FRI. CPI TUE."] \
      [--skipped "XYZ|top holdings on boycott lists"]

v4.9: a "WHAT TO DO NOW" block comes first: numbered steps copied from the engine numbers (or, with no
buy, what to do instead and the closest idea). A plan whose only blockers are screens that were never
run is not a researched idea: it is listed once under SKIPPED instead of a red NO BUY block.
"""
import argparse, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from portfolio_state import plan_is_trade  # noqa: E402


def money(x):
    return f"${x:,.2f}"


def px(x):
    return f"{x:,.2f}"


def short_reason(r):
    r = (r or "").split(";")[0].split("(")[0].strip()
    return r[:90]


def _url(x):
    return x if str(x or "").startswith("http") else ""


def halal_ref(sh):
    """v4.9: (label, reference) for the Shariah result, e.g. ('NOT HALAL', 'SS-21: interest_debt over limit ...')."""
    if not sh or sh.get("mode") == "off" or sh.get("screened") is False:
        return "NOT CHECKED", "screen not run"
    pol = sh.get("policy_decision")
    label = {"PERMITTED": "HALAL", "REQUIRES_ACCEPTANCE": "HALAL IF YOU ACCEPT", "EXCLUDED": "NOT HALAL",
             "UNVERIFIED": "NOT CHECKED"}.get(pol, "NOT CHECKED")
    meth = (sh.get("methodology") or "").split(",")[0]
    why = "; ".join((sh.get("reasons") or [])[:2])
    src = sh.get("rules_source") if isinstance(sh.get("rules_source"), str) else (sh.get("rules_source") or {}).get("url", "")
    ref = " ".join(x for x in (f"METHOD {meth}" if meth else "", (f"- {why}" if meth else why) if why else "",
                               f"REF {_url(src)}" if _url(src) else "") if x)
    return label, ref


def boycott_ref(b):
    """v4.9: (label, reference) for the boycott result, naming each list that matched and its link."""
    if not b or b.get("mode") == "off" or b.get("screened") is False:
        return "NOT CHECKED", "screen not run"
    st = str(b.get("status", "")).lower()
    label = {"reviewed_no_match": "NOT ON LISTS", "flagged": "FLAGGED", "excluded": "ON BOYCOTT LIST",
             "unverified": "NOT FULLY CHECKED"}.get(st, "NOT CHECKED")
    srcs = b.get("sources_checked") or {}
    hits = [f"{k.upper()} {v.get('url', '')}".strip() for k, v in srcs.items() if v.get("finding") == "match"]
    checked = sorted({v.get("checked_on") for v in srcs.values() if v.get("checked_on")})
    if hits:
        ref = "LISTED BY: " + "; ".join(hits)
    elif st == "reviewed_no_match":
        ref = f"{len(srcs)} SOURCES CHECKED {checked[-1] if checked else ''}: " + ", ".join(k.upper() for k in srcs)
    else:
        ref = "; ".join((b.get("reasons") or [])[:2])
    extra = [r for r in (b.get("reasons") or [])[:2] if not r.lower().startswith("listed by")]
    if st in ("excluded", "flagged", "unverified") and extra and hits:
        ref += " - " + "; ".join(extra)
    return label, ref


def is_clean(d):
    """Passes both screens: not on a boycott list, and halal (or halal with the user's recorded OK)."""
    b, _ = boycott_ref(d.get("boycott"))
    h, _ = halal_ref(d.get("shariah"))
    return b == "NOT ON LISTS" and h in ("HALAL", "HALAL IF YOU ACCEPT")


def halal_line(sh):
    if sh and sh.get("mode") == "flag" and sh.get("screened") is not False:
        label, ref = halal_ref(sh)
        if label in ("NOT HALAL", "HALAL IF YOU ACCEPT", "NOT CHECKED"):
            out = [f"  HALAL: {label}" + (" (FLAG ONLY: YOU DECIDE)" if label != "HALAL IF YOU ACCEPT" else "")]
            if ref:
                out.append(f"    {ref}")
            return out
    if not sh or sh.get("mode") == "off":
        return ["  HALAL: NOT CHECKED. SCREEN WAS OFF."]
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
    if b and b.get("mode") == "flag" and b.get("screened") is not False:
        label, ref = boycott_ref(b)
        if label != "NOT ON LISTS":
            return [f"  BOYCOTT: {label} (FLAG ONLY: YOU DECIDE)", f"    {ref}"]
    if not b or b.get("mode") == "off":
        return ["  BOYCOTT: NOT CHECKED. SCREEN WAS OFF."]
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


# v4.8: plain-language reasons. (pattern in the engine text, lower case) -> (why, what to do)
EXPLAIN = [
    # specific patterns first: explain() stops at the first match
    ("edited file?", "THIS PLAN FILE WAS CHANGED AFTER THE ENGINE MADE IT.", "RUN THE ENGINE AGAIN. NEVER EDIT PLAN FILES."),
    ("does not match a recomputation from its own prices", "SIGNALS FILE WAS CHANGED AFTER IT WAS MADE.",
     "RUN SIGNALS AGAIN. NEVER EDIT IT."),
    ("no usable recorded prices", "SIGNALS FILE HAS NO PRICES INSIDE (OLD OR EDITED).", "RUN SIGNALS AGAIN."),
    ("after today: wrong price file", "PRICE FILE HAS FUTURE DATES.", "USE THE REAL PRICE HISTORY."),
    ("a company is a stock", "THIS IS A COMPANY, NOT A GOLD/SILVER OR T-BILL FUND.", "PLAN IT AS A STOCK."),
    ("before today's open", "PRICE IS FROM BEFORE TODAY'S OPEN.", "GET A PRICE FROM TODAY'S SESSION."),
    ("holiday list not loaded", "MARKET HOLIDAYS FOR THIS YEAR NOT LOADED.", "UPDATE THE NYSE CALENDAR (MAINTAINER)."),
    ("earliest earnings date", "EARNINGS DATE GIVEN IS NOT THE EARLIEST ONE ON RECORD.", "USE THE EARLIEST RECORDED DATE."),
    ("portfolio state error", "YOUR HOLDINGS DATA HAS AN ERROR.", "CHECK HOLDINGS AND ORDERS AGAINST YOUR APP."),
    ("does not match the earnings date in the source ledger", "EARNINGS DATE GIVEN DOESN'T MATCH THE RECORDED SOURCE.",
     "USE THE DATE FROM THE SOURCE."),
    ("earnings date not recorded in the source ledger", "EARNINGS DATE HAS NO SOURCE.",
     "RECORD WHERE THE DATE CAME FROM, THEN PLAN AGAIN."),
    ("signals file price", "PRICE FILE LOOKS WRONG (FAR FROM TODAY'S PRICE).", "CHECK IT IS THIS TICKER'S PRICES. RUN SIGNALS AGAIN."),
    ("signals not run", "TREND NOT CHECKED. SHORT TRADES NEED IT.", "RUN SIGNALS WITH A YEAR OF PRICES."),
    ("signals unknown", "NOT ENOUGH PRICE HISTORY FOR THE TREND CHECK.", "GET A YEAR OF PRICES, OR PLAN MEDIUM/LONG TERM."),
    ("at or below its stop/review level", "A HOLDING IS ALREADY AT OR UNDER ITS STOP.", "SORT THAT HOLDING FIRST."),
    ("metals allocation cap", "GOLD/SILVER LIMIT FOR YOUR RISK LEVEL IS USED UP.", "NONE. ENOUGH METALS."),
    ("--sector-weights is required", "SECTOR DATA MISSING.", "GIVE THE SECTOR (OR ETF SECTOR WEIGHTS)."),
    ("--as-of (today's date) is required", "TODAY'S DATE MISSING.", "RUN AGAIN WITH TODAY'S DATE."),
    ("signals say avoid", "PRICE TREND IS DOWN (SIGNALS SAY AVOID).", "WAIT UNTIL PRICE IS BACK ABOVE ITS 200-DAY AVERAGE."),
    ("signals say caution", "TREND IS WEAK. NO SHORT-TERM BUY.", "WAIT, OR PLAN IT AS MEDIUM/LONG TERM."),
    ("signals file", "SIGNALS FILE IS WRONG OR FOR ANOTHER TICKER.", "RUN SIGNALS AGAIN FOR THIS TICKER."),
    ("re-run signals.py", "SIGNALS USE OLD PRICES.", "RUN SIGNALS AGAIN WITH TODAY'S PRICES."),
    ("inside the short-term holding window", "EARNINGS COME BEFORE THIS SHORT TRADE WOULD END.",
     "WAIT UNTIL AFTER EARNINGS, OR SAY YOU ACCEPT THE JUMP RISK."),
    ("next earnings date not given", "NEXT EARNINGS DATE NOT CHECKED.", "LOOK UP THE EARNINGS DATE."),
    ("has passed: look up the next one", "EARNINGS DATE IS OLD.", "LOOK UP THE NEXT EARNINGS DATE."),
    ("fees and spread take", "FEES EAT TOO MUCH OF THE PROFIT FOR A SHORT TRADE.",
     "HOLD LONGER WITH A BIGGER TARGET, OR SKIP."),
    ("screen is mandatory", "SCREEN WAS SET TO OFF. BOYCOTT AND HALAL CHECKS ALWAYS RUN.",
     "RUN BOTH SCREENS, THEN PLAN AGAIN."),
    ("screen not run", "SCREEN NOT DONE YET FOR THIS TICKER.", "RUN THE SCREEN, THEN PLAN AGAIN."),
    ("boycott screen: excluded", "COMPANY IS ON A BOYCOTT LIST.", "NONE. SKIP IT."),
    ("boycott screen: unverified", "BOYCOTT CHECK NOT COMPLETE (A SOURCE MISSING, OLD OR DOWN).",
     "CHECK ALL 5 BOYCOTT SOURCES AGAIN."),
    ("boycott screen: flagged", "BOYCOTT: FLAGGED (ISRAEL OPERATIONS IN ITS FILINGS). YOU HAVE NOT SAID OK.",
     "SAY OK TO ACCEPT IT, OR SKIP IT."),
    ("interest-bearing", "T-BILL FUND PAYS INTEREST. NOT HALAL.", "KEEP CASH, OR USE A CERTIFIED SUKUK FUND."),
    ("shariah screen: excluded", "NOT HALAL UNDER YOUR METHOD.", "NONE. SKIP IT."),
    ("shariah screen: unverified", "HALAL CHECK NOT COMPLETE (DATA MISSING, OLD, OR FOR ANOTHER SECURITY).",
     "GET THE LATEST 10-Q/10-K NUMBERS AND RE-SCREEN."),
    ("shariah screen: requires acceptance", "HALAL: BORDERLINE (NEAR A LIMIT). YOU HAVE NOT SAID OK.",
     "SAY OK TO ACCEPT IT, OR SKIP IT."),
    ("--isin is required", "NO ISIN. SCREEN CAN'T BE MATCHED TO THIS SECURITY.", "GIVE THE ISIN."),
    ("sources not checked", "SOURCES NOT CHECKED.", "RUN THE SOURCE CHECK."),
    ("sources not fresh or incomplete", "SOME DATA IS OLD, MISSING, OR SOURCES DISAGREE.",
     "RE-READ THE SOURCES LISTED BELOW, THEN PLAN AGAIN."),
    ("source check unreadable", "SOURCE CHECK FILE IS BROKEN.", "RUN THE SOURCE CHECK AGAIN."),
    ("net reward:risk", "PROFIT TOO SMALL FOR THE RISK.", "WAIT FOR A LOWER PRICE. DON'T FORCE IT."),
    ("stop is", "STOP TOO FAR BELOW THE BUY PRICE FOR YOUR RISK LEVEL.", "WAIT FOR A PRICE NEARER SUPPORT."),
    ("is more than 1% above the market", "BUY PRICE TOO FAR ABOVE TODAY'S PRICE.", "PLAN A NEW ENTRY."),
    ("at or below the stop", "PRICE ALREADY AT OR UNDER THE STOP. SETUP BROKEN.", "NONE. SKIP IT."),
    ("levels must satisfy", "PRICES DON'T MAKE SENSE (STOP < BUY < TARGET).", "FIX THE LEVELS."),
    ("t1 must be", "FIRST TARGET IS ABOVE SECOND TARGET.", "FIX THE TARGETS."),
    ("one-cent grid", "A PRICE IS NOT IN WHOLE CENTS.", "USE CENT PRICES."),
    ("sub-penny", "PRICE UNDER $1. NOT SUPPORTED.", "NONE. SKIP IT."),
    ("prices under", "PRICE UNDER $1. NOT SUPPORTED.", "NONE. SKIP IT."),
    ("unquantified risk", "A HOLDING HAS NO STOP OR REVIEW LEVEL, SO ITS RISK IS UNKNOWN.",
     "SET A STOP FOR IT, OR AGREE A LOSS % FOR IT."),
    ("breached", "A HOLDING IS ALREADY UNDER ITS STOP.", "SORT THAT HOLDING FIRST."),
    ("maximum number of", "TOO MANY POSITIONS ALREADY.", "SELL ONE FIRST, OR SKIP."),
    ("open-risk limit", "TOTAL RISK ON OPEN POSITIONS IS ALREADY AT YOUR LIMIT.", "WAIT, OR TIGHTEN OTHER STOPS."),
    ("sector cap", "TOO MUCH MONEY IN THIS SECTOR ALREADY.", "PICK ANOTHER SECTOR."),
    ("position cap", "YOU ALREADY HOLD AS MUCH OF THIS AS YOUR RISK LEVEL ALLOWS.", "NONE. ENOUGH OF IT."),
    ("cash floor", "NOT ENOUGH CASH AFTER THE SAFETY CASH AND OPEN ORDERS.", "ADD CASH OR WAIT FOR FILLS."),
    ("no whole-share quantity", "NOT EVEN 1 SHARE FITS YOUR LIMITS AND FEES.", "SKIP, OR USE A CHEAPER FUND."),
    ("fees and spread exceed", "FEES EAT ALL THE INCOME.", "KEEP IT AS CASH."),
    ("fee schedule", "NO FEE SCHEDULE FOR YOUR PLATFORM.", "GIVE YOUR PLATFORM'S FEES."),
    ("sector weights", "SECTOR DATA MISSING OR WRONG.", "GIVE THE SECTOR (OR ETF SECTOR WEIGHTS)."),
    ("sector weight", "SECTOR DATA MISSING OR WRONG.", "GIVE THE SECTOR (OR ETF SECTOR WEIGHTS)."),
    ("nyse is closed", "US MARKET IS CLOSED NOW. PRICES CAN JUMP BEFORE THE OPEN.",
     "RUN AGAIN WHEN THE MARKET IS OPEN, WITH A FRESH PRICE."),
    ("quote status", "NO LIVE PRICE (MARKET CLOSED OR OLD PRICE).", "GET A LIVE PRICE, RUN AGAIN."),
    ("quote is", "PRICE IS TOO OLD.", "GET A FRESH PRICE, RUN AGAIN."),
    ("quote time", "PRICE TIME MISSING OR WRONG.", "GET A FRESH PRICE WITH ITS TIME."),
    ("delayed quote", "DELAYED PRICE WITHOUT A STATED DELAY.", "GET A LIVE PRICE."),
    ("no --market-price", "NO MARKET PRICE TO CHECK THE BUY PRICE AGAINST.", "GET A FRESH PRICE."),
    ("is not today", "DATE IS NOT TODAY.", "RUN AGAIN TODAY."),
    ("replay", "THIS IS A REPLAY OF A PAST DAY. RESEARCH ONLY.", "RUN ON A LIVE PRICE."),
    ("account currency differs", "YOUR ACCOUNT IS NOT IN USD. NO FX MODEL YET.", "HOLD USD IN THE ACCOUNT."),
    ("invalid input", "A NUMBER IS MISSING OR WRONG.", "CHECK THE INPUTS."),
    ("is required", "A NEEDED NUMBER IS MISSING.", "GIVE THE MISSING NUMBER."),
    ("engine error", "THE ENGINE FAILED. NO TRADE FOR SAFETY.", "RUN THE ENGINE CHECK."),
]


def explain(reason):
    low = (reason or "").lower()
    for pat, why, fix in EXPLAIN:
        if pat in low:
            return why, fix
    return None, None


def detail_lines(d, reason):
    """Extra facts behind a screen reason: which boycott lists matched, why not halal."""
    low = reason.lower()
    out = []
    if low.startswith("boycott screen"):
        b = d.get("boycott") or {}
        hits = [k.upper() for k, v in (b.get("sources_checked") or {}).items() if v.get("finding") == "match"]
        if hits:
            out.append(f"    FOUND ON: {', '.join(hits)}")
        out += [f"    - {r}" for r in (b.get("reasons") or [])[:4]]
    if low.startswith("shariah screen"):
        sh = d.get("shariah") or {}
        if sh.get("methodology"):
            out.append(f"    METHOD: {sh['methodology']}")
        out += [f"    - {r}" for r in (sh.get("reasons") or [])[:4]]
    if low.startswith("sources not fresh"):
        out += [f"    - {p}" for p in ((d.get("sources") or {}).get("problems") or [])[:6]]
    return out


def _one(d, r, label="WHY"):
    why, fix = explain(r)
    out = [f"  {label}: {why or r.upper()}"] + detail_lines(d, r)
    if fix:
        out.append(f"  FIX: {fix}")
    if why:
        out.append(f"  (ENGINE: {r})")
    return out


def reason_block(d):
    reasons = d.get("reasons") or ["no reason given by the engine"]
    out = []
    for r in reasons:
        out += _one(d, r)
    if d.get("verdict") == "NO TRADE":
        for r in d.get("also_needed") or []:      # v4.8: what would still be missing once the above is fixed
            out += _one(d, r, label="ALSO NEEDED")
    return out


def _short_time(s):
    return (s or "?").replace("T", " ")[:16]


def sources_lines(d):
    s = d.get("sources") or {}
    if not s.get("checked"):
        return ["  !! SOURCES NOT CHECKED. DON'T TRUST THESE NUMBERS YET. !!"]
    out = []
    by = {}
    for it in s.get("ticker_items") or []:
        by.setdefault(it.get("category"), []).append(it)
    q = by.get("quote") or []
    if q:
        match = "MATCH" if len(q) > 1 and all(x.get("status") == "FRESH" for x in q) else (
            "ONE SOURCE ONLY" if len(q) == 1 else "CHECK")
        out.append("  PRICE FROM: " + " + ".join(f"{x.get('source_name')} {_short_time(x.get('observed_at'))}"
                                                 for x in q) + f" ({match})")
    for cat, label in (("fundamentals", "NUMBERS FROM"), ("price_history", "CHART DATA FROM"),
                       ("consensus", "ANALYSTS FROM"), ("fund_holdings", "FUND HOLDINGS FROM")):
        for x in by.get(cat) or []:
            extra = f" {x.get('form')} FILED {x.get('published_at')}" if cat == "fundamentals" else (
                f" {x.get('published_at')}" if x.get("published_at") else f" READ {_short_time(x.get('observed_at'))}")
            out.append(f"  {label}: {x.get('source_name')}{extra}")
    if not s.get("ok"):
        out.append("  !! SOME SOURCES OLD OR MISSING. SEE WHY. !!")
    return out


def market_sources(plans):
    seen, out = set(), []
    for d in plans:
        for it in (d.get("sources") or {}).get("market_items") or []:
            key = it.get("url")
            if key in seen:
                continue
            seen.add(key)
            when = it.get("published_at") or _short_time(it.get("observed_at"))
            tier = {1: "OFFICIAL", 2: "NEWS", 3: "DATA SITE"}.get(it.get("tier"), "?")
            out.append(f"- {it.get('source_name')} [{tier}] {when}: {it.get('what') or it.get('category')} "
                       f"{it.get('url')}")
    checked = next(((d.get("sources") or {}).get("checked_at") for d in plans if (d.get("sources") or {}).get("checked")),
                   None)
    if not out:
        return []
    return [f"SOURCES (CHECKED {_short_time(checked)} UTC):"] + out


def screen_source_line(d):
    b, sh = d.get("boycott") or {}, d.get("shariah") or {}
    parts = []
    dates = sorted(v.get("checked_on") for v in (b.get("sources_checked") or {}).values() if v.get("checked_on"))
    if dates:
        parts.append(f"BOYCOTT LISTS CHECKED {dates[0]}" + (f" TO {dates[-1]}" if dates[-1] != dates[0] else ""))
    if sh.get("data_published"):
        parts.append(f"HALAL DATA {sh.get('period')} FILED {sh['data_published']}")
        if sh.get("market_cap_date"):
            parts.append(f"MARKET CAP {sh['market_cap_date']}")
    return [f"  SCREEN DATA: {'. '.join(parts)}."] if parts else []


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
    src = (d.get("assumptions") or {}).get("fee_schedule")
    if src and src != "verified":
        out.append(f"  FEE SCHEDULE: {str(src).upper()}, NOT VERIFIED. CHECK FEES IN YOUR APP.")
    fc = d.get("fee_check") or {}
    if fc:
        out.append(f"  FEES: {money(fc['round_trip_costs_at_t1'])} IN AND OUT = {fc['costs_pct_of_gross_profit']:g}% "
                   f"OF PROFIT AT FIRST TARGET")
    dv = d.get("dividend") or {}
    if dv.get("net_yield_pct") is not None:
        out.append(f"  DIVIDEND: {dv['gross_yield_pct']:.2f}% -> {dv['net_yield_pct']:.2f}% AFTER "
                   f"{dv['withholding_pct']:g}% US TAX (ABOUT {money(dv['est_annual_net'])} A YEAR)")
    ea = d.get("earnings") or {}
    if ea.get("date"):
        out.append(f"  EARNINGS: {ea['date']} ({ea.get('days_away')} DAYS)"
                   + (". PRICE CAN JUMP PAST THE STOP." if ea.get("inside_window") else "."))
    sg = d.get("signals") or {}
    if sg.get("checked"):
        out.append(f"  TREND: {sg.get('hint')}" + (f" ({'; '.join(sg.get('flags') or [])})".upper() if sg.get("flags") else ""))
    else:
        out.append("  TREND: NOT CHECKED (NO SIGNALS RUN).")

    out += halal_line(d.get("shariah")) + boycott_line(d.get("boycott")) + screen_source_line(d)
    out += quote_line(d) + sources_lines(d)
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
            "  CHECK PRICE IN APP FIRST."] + boycott_line(d.get("boycott")) + quote_line(d) + sources_lines(d)


def signal_no_buys(signals, planned):
    """v4.8: tickers dropped by the signals (151 Trading Strategies filters) still get a NO BUY with the why."""
    out = []
    for sg in signals or []:
        t = str(sg.get("ticker", "?")).upper()
        if t in planned or sg.get("hint") != "AVOID":
            continue
        out.append(f"NO BUY {t}")
        for f in sg.get("flags") or ["signals say avoid"]:
            out.append(f"  WHY: {f.upper()}.")
        out.append("  FIX: WAIT UNTIL PRICE IS BACK ABOVE ITS 200-DAY AVERAGE.")
        out.append(f"  (SIGNALS: price {sg.get('price')}, 200-day avg {(sg.get('sma') or {}).get('ma200')}, "
                   f"12-1 month return {sg.get('momentum_12_1')}, data through {sg.get('history_through')})")
        out.append("")
    return out


UNRUN = ("screen not run", "screen is mandatory", "sources not checked", "quote status 'unknown'",
         "no --market-price", "sources not fresh or incomplete")


def never_researched(d):
    """v4.9: True when the plan was blocked only because its screens/data were never gathered."""
    rs = [str(r).lower() for r in (d.get("reasons") or [])]
    return bool(rs) and any("screen not run" in r for r in rs) and all(any(u in r for u in UNRUN) for r in rs)


def screen_rows(plans):
    """v4.9: one row per screened ticker: (ticker, boycott label, boycott ref, halal label, halal ref)."""
    rows = []
    order = sorted(plans, key=lambda x: (x.get("verdict") != "TRADE", not is_clean(x)))
    for d in order:
        bl, br = boycott_ref(d.get("boycott"))
        hl, hr = halal_ref(d.get("shariah"))
        rows.append(((d.get("ticker") or "?").upper(), bl, br, hl, hr))
    return rows


GREEN, YELLOW, RED = "\U0001F7E2", "\U0001F7E1", "\U0001F534"


def mark(*labels):
    """v5.0: one coloured dot for a line. Red = on a list / not halal, yellow = your call, green = good."""
    if any(l in ("ON BOYCOTT LIST", "NOT HALAL") for l in labels):
        return RED
    return GREEN if all(l in ("NOT ON LISTS", "HALAL") for l in labels) else YELLOW


def screen_table_lines(plans):
    rows = screen_rows(plans)
    if not rows:
        return []
    out = ["SCREENS (EVERY IDEA, WITH REFERENCES):"]
    for t, bl, br, hl, hr in rows:
        out.append(f"  {mark(bl, hl)} {t}: BOYCOTT {bl} | HALAL {hl}")
        out.append(f"    BOYCOTT REF: {br}")
        out.append(f"    HALAL REF: {hr}")
    return out + [""]


def option_rows(plans):
    """v4.9: every idea as a lettered option, plus KEEP CASH. Returns (rows, recommended_letter)."""
    rows, rec = [], None
    trades = [d for d in plans if d.get("verdict") == "TRADE" and plan_is_trade(d) and d.get("asset") != "tbill"]
    others = [d for d in plans if d not in trades]
    letters = iter("ABCDEFGHIJ")
    for d in sorted(trades, key=lambda x: not is_clean(x)) + others:
        L, t = next(letters), (d.get("ticker") or "?").upper()
        bl, _ = boycott_ref(d.get("boycott"))
        hl, _ = halal_ref(d.get("shariah"))
        labels = f"BOYCOTT {bl} / HALAL {hl}"
        if d in trades:
            tr = d.get("tranches") or [{}]
            pe = d.get("partial_exit_plan") or {}
            profit = pe.get("combined_net_profit") if pe.get("feasible") else d.get("net_profit_full_exit_t1")
            text = (f"BUY {d['shares']} {t} AT {px(tr[0].get('price', 0))} LIMIT. RISK {money(d['downside']['executable_stop_downside'])} "
                    f"(GAP {money(d['gap_scenario']['loss'])}). PROFIT IF TARGETS HIT {money(profit or 0)}.")
            if rec is None and is_clean(d):
                rec = L
        else:
            why, _ = explain((d.get("reasons") or [""])[0])
            text = f"{t}: ENGINE SAYS NO. {why or (d.get('reasons') or ['?'])[0]}"
        dot = (mark(bl, hl) if is_clean(d) else YELLOW) if d in trades else RED
        rows.append((L, text, labels, d in trades, dot))
    L = next(letters)
    rows.append((L, "KEEP CASH. $0 RISK, $0 GAIN.", "", True, GREEN))
    return rows, rec or L


def option_lines(plans):
    rows, rec = option_rows(plans)
    out = ["YOUR OPTIONS:"]
    for L, text, labels, _, dot in rows:
        out.append(f"  {dot} {L}. {text}" + (f" [{labels}]" if labels else ""))
    rtext = next(r[1] for r in rows if r[0] == rec)
    rdot = next(r[4] for r in rows if r[0] == rec)
    good = ("CLEAN ON BOTH SCREENS AND PASSES YOUR RISK RULES." if rdot == GREEN
            else "NOT ON BOYCOTT LISTS. HALAL ONLY IF YOU ACCEPT IT. PASSES YOUR RISK RULES.")
    out.append(f"  RECOMMENDED: {rec}. {good if 'KEEP CASH' not in rtext else 'NO CLEAN TRADE PASSES TODAY.'}")
    flagged = [L for L, t, lab, ok, _ in rows if ok and lab and ("ON BOYCOTT LIST" in lab or "NOT HALAL" in lab or "FLAGGED" in lab)]
    if flagged:
        out.append(f"  FLAGGED OPTIONS {', '.join(flagged)}: SHOWN BECAUSE YOU CHOSE FLAG. YOUR DECISION.")
    return out + [""]


def action_lines(plans, events="", skipped=()):
    """v4.9: numbered steps the user can follow in the app. Numbers copied from the engine."""
    out, n = ["WHAT TO DO NOW:"], 0

    def step(text):
        nonlocal n
        n += 1
        out.append(f"  {n}. {text}")

    trades = [d for d in plans if d.get("verdict") == "TRADE" and plan_is_trade(d)]
    rows, rec = option_rows(plans)
    rec_t = next((r[1] for r in rows if r[0] == rec), "")
    trades = [d for d in trades if d.get("asset") == "tbill" or (f" {(d.get('ticker') or '').upper()} AT " in rec_t)]
    for d in trades:
        t = (d.get("ticker") or "?").upper()
        if d.get("asset") == "tbill":
            step(f"BUY {d['shares']} {t} WITH A LIMIT ORDER, ABOUT {money(d['order_value'] + d['buy_fee'])} (CASH PARKING).")
            continue
        tr = d.get("tranches") or []
        if len(tr) == 1:
            step(f"IN YOUR APP: LIMIT BUY {tr[0]['shares']} {t} AT {px(tr[0]['price'])}, GOOD-TILL-CANCEL.")
        else:
            step(f"IN YOUR APP: LIMIT BUYS {t}: " + ", ".join(f"{x['shares']} @ {px(x['price'])}" for x in tr) + ".")
        if d.get("horizon") == "long":
            step(f"SET A PRICE ALERT AT {px(d['stop_level'])}. IF HIT: REVIEW, NOT AUTO SELL.")
        else:
            step(f"WHEN IT FILLS: STOP ORDER AT {px(d['stop_level'])} FOR ALL SHARES.")
        pe = d.get("partial_exit_plan") or {}
        if pe.get("feasible"):
            step(f"THEN SELL ORDERS: {pe['sell_at_t1']} AT {px(d['t1_level'])}, {pe['hold_for_t2']} AT {px(d['t2_level'])}.")
        else:
            step(f"THEN SELL ORDER: ALL AT {px(d['t1_level'])}.")
        step(f"IF {t} NEVER DIPS TO YOUR PRICE: NO FILL, CASH STAYS. THAT IS FINE.")
    if trades:
        step("TELL ME WHEN IT FILLS. I RECORD IT AND RE-CHECK RISK.")
    else:
        step("DO NOTHING TODAY. KEEP CASH. NO TRADE IS A GOOD RESULT.")
        near = [d for d in plans if d.get("verdict") in ("WATCHLIST", "NO TRADE") and d.get("tranches")
                and not never_researched(d)]
        for d in near[:2]:
            t = (d.get("ticker") or "?").upper()
            why, fix = explain((d.get("reasons") or [""])[0])
            step(f"CLOSEST IDEA: {t}. BLOCKED: {why or 'SEE BELOW'} {('NEXT: ' + fix) if fix else ''}".rstrip())
        step("RE-RUN ME" + (f" AFTER: {events.upper()}" if events else " TOMORROW") + ".")
    return out + [""]


def render(plans, market="", metals="", events="", signals=None, skipped=()):
    lines = [f"{GREEN} GOOD   {YELLOW} WAIT / YOUR CALL   {RED} STOP"]
    first = next((d for d in plans if d.get("profile")), None)
    if first:
        lines.append(f"RISK: {str(first.get('profile')).upper()}. HOLD: {str(first.get('horizon') or 'n/a').upper()}.")
    mc = next((d.get("market_clock") for d in plans if d.get("market_clock")), None)
    if mc:
        if mc.get("open"):
            line = f"NYSE: OPEN. CLOSES {mc.get('closes')} NEW YORK TIME"
            line += " (EARLY CLOSE TODAY)." if mc.get("early_close") else "."
        else:
            line = (f"NYSE: CLOSED ({str(mc.get('reason', '')).upper()}). "
                    f"NEXT OPEN {mc.get('next_open_new_york', '?')} NEW YORK TIME.")
        lines.append(line)
        if mc.get("warning"):
            lines.append("  !! HOLIDAY LIST NOT LOADED FOR THIS YEAR. CHECK NYSE.COM. !!")
    if market:
        lines.append(f"MARKET: {market.upper()}")
    if metals:
        lines.append(f"GOLD/SILVER: {metals.upper()}")
    if events:
        lines.append(f"WATCH: {events.upper()}")
    if lines:
        lines.append("")
    skip_lines = [f"  {x.split('|')[0].strip().upper()}: {x.split('|', 1)[1].strip().upper() if '|' in x else 'NOT A CANDIDATE'}"
                  for x in skipped]
    kept = []
    for d in plans:
        if never_researched(d):
            skip_lines.append(f"  {(d.get('ticker') or '?').upper()}: NOT RESEARCHED (SCREENS NOT RUN). NOT A CANDIDATE.")
        else:
            kept.append(d)
    plans = kept
    lines += screen_table_lines(plans) + option_lines(plans) + action_lines(plans, events)
    buys, waits, nos = [], [], []
    plans = sorted(plans, key=lambda x: (x.get("verdict") != "TRADE", not is_clean(x)))
    for d in plans:
        t = (d.get("ticker") or d.get("asset", "?")).upper()
        v = d.get("verdict")
        if v == "TRADE" and not plan_is_trade(d):
            d = dict(d, verdict="NO TRADE", reasons=list(d.get("reasons") or []) +
                     ["plan says TRADE but carries reasons or is not placeable (edited file?): re-run the engine"])
            v = "NO TRADE"
        if v == "TRADE":
            buys += (render_tbill(d) if d.get("asset") == "tbill" else render_trade(d)) + warning_lines(d) + [""]
        elif v == "WATCHLIST" and d.get("tranches"):
            head = "\n".join([f"WAIT {t}"] + reason_block(d) + ["  IF READY LATER, PLAN IS:"])
            waits += render_trade(d, header=head) + warning_lines(d) + [""]
        elif v == "WATCHLIST":
            waits += [f"WAIT {t}"] + reason_block(d) + sources_lines(d) + [""]
        else:
            nos += [f"NO BUY {t}"] + reason_block(d) + [""]
    if not buys:
        lines += ["NO BUY TODAY. CASH OK.", ""]
    while waits and waits[-1] == "":
        waits.pop()
    nos += signal_no_buys(signals, {str(d.get("ticker") or "").upper() for d in plans})
    while nos and nos[-1] == "":
        nos.pop()
    lines += buys + waits + ([""] if waits and nos else []) + nos
    if waits or nos:
        lines.append("")
    if skip_lines:
        lines += ["SKIPPED:"] + skip_lines + [""]
    ms = market_sources(plans)
    if ms:
        lines += ms + [""]
    lines.append("YOU DECIDE. YOU PLACE ORDER. NOT ADVICE.")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", nargs="+", required=True)
    ap.add_argument("--market", default="")
    ap.add_argument("--metals", default="")
    ap.add_argument("--events", default="")
    ap.add_argument("--signals", nargs="*", default=[], help="signals.py outputs; AVOID names get a NO BUY with the why")
    ap.add_argument("--skipped", action="append", default=[],
                    help='v4.9: "TICKER|why it was dropped before screening", one line each under SKIPPED')
    a = ap.parse_args(argv)
    plans = []
    for p in a.plans:
        with open(p) as f:
            d = json.load(f)
        if not isinstance(d, dict):
            sys.exit(f"{p} is not a size_trade.py plan")
        plans.append(d)
    sigs = []
    for p in a.signals:
        with open(p) as f:
            sigs.append(json.load(f))
    sys.stdout.write(render(plans, a.market, a.metals, a.events, sigs, a.skipped))


if __name__ == "__main__":
    main()
