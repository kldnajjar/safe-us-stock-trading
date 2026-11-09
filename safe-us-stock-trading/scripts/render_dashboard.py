#!/usr/bin/env python3
"""Per-run dashboard for the safe-us-stock-trading skill (v4.6).

One self-contained HTML page (no scripts, no external files) built from the engine's JSON:
portfolio snapshot, limits used, one card per idea (TRADE / WATCHLIST / NO TRADE), holdings,
sector exposure, events and sources. Every number is copied from the engine output; the only
arithmetic here is the width of a progress bar. Nothing is recomputed or rounded differently.

  python3 render_dashboard.py --plans PLAN1.json PLAN2.json --state ACTUAL.json \
      [--projected PROJECTED.json] [--market "CALM. FED WAIT."] [--metals "WAIT."] \
      [--events "JOBS FRI. CPI TUE."] [--note "NVDA: on AFSC list"] \
      [--source "Title|https://..."] [--title "Trade plan"] --out dashboard.html

Publish the file as an artifact (or send it). It is a snapshot: levels are valid only for the
quoted price shown on each card.
"""
import argparse, html, json, sys
import os as _os
sys_path_dir = _os.path.dirname(_os.path.abspath(__file__))
import sys as _sys
if sys_path_dir not in _sys.path:
    _sys.path.insert(0, sys_path_dir)
import render_simple as _rs  # noqa: E402  (same WHY / FIX table as the text output)
from portfolio_state import plan_is_trade as _plan_is_trade  # noqa: E402

SAFETY_FOOTER = "YOU DECIDE. YOU PLACE ORDER. NOT ADVICE."
BOYCOTT_WORD = {"reviewed_no_match": ("Not on lists", "ok"), "flagged": ("Flagged", "warn"),
                "excluded": ("On list", "bad"), "unverified": ("Not checked", "warn")}
SHARIAH_WORD = {"PERMITTED": ("OK", "ok"), "REQUIRES_ACCEPTANCE": ("You must OK", "warn"),
                "EXCLUDED": ("No", "bad"), "UNVERIFIED": ("Not checked", "warn")}
VERDICT = {"TRADE": ("BUY", "ok"), "WATCHLIST": ("WAIT", "warn"), "NO TRADE": ("NO BUY", "bad")}

CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1b;--mute:#6b6b66;--line:#e3e2dc;--ok:#1f7a4d;--ok-bg:#e6f4ec;
--warn:#8a5a00;--warn-bg:#fdf1d8;--bad:#b42318;--bad-bg:#fde8e6;--bar:#3a6ea5;--bar-bg:#e8edf3}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;
--mute:#a3a29b;--line:#34332f;--ok:#5cc490;--ok-bg:#16301f;--warn:#e7b85a;--warn-bg:#352a12;--bad:#f2857a;
--bad-bg:#3a1a17;--bar:#7aa7d6;--bar-bg:#26303b}}
:root[data-theme="dark"]{--bg:#141413;--card:#1e1e1c;--ink:#ecebe6;--mute:#a3a29b;--line:#34332f;--ok:#5cc490;
--ok-bg:#16301f;--warn:#e7b85a;--warn-bg:#352a12;--bad:#f2857a;--bad-bg:#3a1a17;--bar:#7aa7d6;--bar-bg:#26303b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.45 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1080px;margin:0 auto;padding:24px 16px 48px}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;
color:var(--mute);margin:28px 0 10px}.sub{color:var(--mute);font-size:13px}
.banner{border-radius:8px;padding:10px 14px;margin:14px 0;font-weight:600}
.banner.bad{background:var(--bad-bg);color:var(--bad)}.banner.warn{background:var(--warn-bg);color:var(--warn)}
.ctx{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.ctx div,.tile,.card,.tbl{background:var(--card);border:1px solid var(--line);border-radius:10px}
.ctx div{padding:10px 12px}.ctx b{display:block;font-size:12px;color:var(--mute);font-weight:600}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;margin-top:10px}
.tile{padding:12px 14px}.tile .k{font-size:12px;color:var(--mute)}.tile .v{font-size:22px;font-weight:650;
font-variant-numeric:tabular-nums}.tile .s{font-size:12px;color:var(--mute)}
.meter{height:6px;background:var(--bar-bg);border-radius:3px;margin-top:8px;overflow:hidden}
.meter i{display:block;height:100%;background:var(--bar)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
.card{padding:14px 16px}.card h3{margin:0;font-size:18px;display:flex;align-items:center;gap:8px}
.badge{font-size:11px;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:99px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}
.badge.ok{background:var(--ok-bg)}.badge.warn{background:var(--warn-bg)}.badge.bad{background:var(--bad-bg)}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:12px 0;font-size:14px}
dt{color:var(--mute)}dd{margin:0;font-variant-numeric:tabular-nums;text-align:right}
.lines{list-style:none;padding:0;margin:10px 0 0;font-size:13px}.lines li{padding:3px 0;border-top:1px solid var(--line)}
.reason{font-size:14px;margin-top:8px}.tbl{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 12px;text-align:right;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}th{font-size:12px;color:var(--mute);font-weight:600}
.secrow{display:grid;grid-template-columns:140px 1fr 110px;gap:10px;align-items:center;font-size:14px;margin:6px 0}
.secrow .meter{margin:0}.secrow span:last-child{text-align:right;font-variant-numeric:tabular-nums}
.foot{margin-top:28px;font-weight:700;text-align:center}.src a{color:var(--bar)}ul.src{padding-left:18px}
@media (max-width:520px){.secrow{grid-template-columns:90px 1fr 90px}}
"""


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def money(x):
    """Numbers as $1,234.56; engine status strings (e.g. UNQUANTIFIED, BREACHED: ...) shown as-is."""
    if x is None:
        return "n/a"
    return f"${x:,.2f}" if _num(x) else str(x).split(":")[0]


def px(x):
    if x is None:
        return "n/a"
    return f"{x:,.2f}" if _num(x) else str(x).split(":")[0]


def get(d, *path):
    for p in path:
        if not isinstance(d, dict):
            return None
        d = d.get(p)
    return d


def meter(used, cap):
    """Bar width only. Labels always show the engine's own figures."""
    try:
        w = 0 if not cap or cap <= 0 else max(0.0, min(100.0, used / cap * 100))
    except TypeError:
        w = 0
    return f'<div class="meter"><i style="width:{w:.1f}%"></i></div>'


def screen_lines(d):
    out = []
    b = d.get("boycott") or {}
    if b and b.get("mode") != "off":
        if b.get("screened") is False:
            out.append(("BOYCOTT: NOT CHECKED. SCREEN NOT RUN.", "bad"))
        else:
            w, c = BOYCOTT_WORD.get(str(b.get("status", "")).lower(), ("Not checked", "warn"))
            out.append((f"Boycott: {w}", c))
    s = d.get("shariah") or {}
    if s and s.get("mode") != "off":
        if s.get("screened") is False:
            out.append(("HALAL: NOT CHECKED. SCREEN NOT RUN.", "bad"))
        else:
            w, c = SHARIAH_WORD.get(s.get("policy_decision"), ("Not checked", "warn"))
            meth = (s.get("methodology") or "").split(",")[0]
            out.append((f"Halal: {w}" + (f" ({meth})" if meth else ""), c))
            p = s.get("purification") or {}
            if p.get("status") == "DUE" and p.get("amount_usd") is not None:
                out.append((f"Give {money(p['amount_usd'])} to charity ({p.get('period')})", "warn"))
            elif p.get("status") == "UNAVAILABLE":
                out.append(("Charity amount: unknown (data missing)", "warn"))
    return out


def quote_line(d):
    q = d.get("quote") or {}
    if not q.get("time"):
        return "Price time: UNKNOWN"
    st = str(q.get("status", "")).upper() + (f" {q['delay_min']}M" if q.get("delay_min") else "")
    mp = f", price {px(q['market_price'])}" if q.get("market_price") is not None else ""
    return f"Price seen {q['time']} ({st}, {q.get('source') or 'source?'}){mp}. Good only for this price."


def trade_body(d):
    rows = []
    tr = d.get("tranches") or []
    if len(tr) == 1:
        rows.append(("Buy limit", f"{px(tr[0]['price'])} × {tr[0]['shares']}"))
    else:
        rows += [(f"Step {i}", f"{px(x['price'])} × {x['shares']}") for i, x in enumerate(tr, 1)]
    if d.get("total_order_value") is not None:
        rows.append(("Cost incl. fees", money(d["total_order_value"] + (d.get("total_buy_fees") or 0))))
    if d.get("horizon") == "long":
        rows.append(("Review level (not auto sell)", px(d.get("stop_level"))))
        rows.append(("Loss at review level", money(get(d, "downside", "long_term_review_level_downside"))))
    else:
        rows.append(("Stop", px(d.get("stop_level"))))
        rows.append(("Planned loss at stop", money(get(d, "downside", "executable_stop_downside"))))
    rows.append(("Loss if price gaps down", money(get(d, "gap_scenario", "loss"))))
    pe = d.get("partial_exit_plan") or {}
    if pe.get("feasible"):
        rows.append((f"Sell {pe['sell_at_t1']} at", px(d.get("t1_level"))))
        rows.append((f"Sell {pe['hold_for_t2']} at", px(d.get("t2_level"))))
        rows.append(("Profit if both hit (after fees)", money(pe.get("combined_net_profit"))))
    elif d.get("t1_level") is not None:
        rows.append(("Sell all at", px(d.get("t1_level"))))
        rows.append(("Profit (after fees)", money(d.get("net_profit_full_exit_t1"))))
    rows.append(("Breakeven after fees", px(d.get("fee_adjusted_breakeven_price"))))
    rows.append(("Net reward:risk", e(d.get("net_rr_of_plan"))))
    lines = []
    st = pe.get("stop_after_t1") or {}
    if st.get("keep_at_least") is not None:
        t = f"After first sell: keep stop {px(st['keep_at_least'])}. NEVER LOWER."
        if st.get("optional_raise_to") is not None:
            t += f" Can raise to {px(st['optional_raise_to'])} (rest no loss)."
        lines.append((t, ""))
    lines.append(("LOSS CAN BE MORE than the planned loss.", "warn"))
    return rows, lines


def reason_html(d, r, label="Why"):
    why, fix = _rs.explain(r)
    out = f'<div class="reason bad"><b>{e(label)}:</b> {e(why or r)}'
    details = [x.strip(" -") for x in _rs.detail_lines(d, r)]
    if details:
        out += "<br>" + "<br>".join(e(x) for x in details)
    if fix:
        out += f"<br><b>Fix:</b> {e(fix)}"
    if why:
        out += f'<br><span class="sub">Engine: {e(r)}</span>'
    return out + "</div>"


def extra_lines(d):
    """v4.8 lines, same facts as the text output: fee source, fees vs profit, dividend, earnings, trend, sources."""
    out = []
    src = (d.get("assumptions") or {}).get("fee_schedule")
    if src and src != "verified":
        out.append((f"Fee schedule: {src}, NOT verified. Check fees in your app.", "warn"))
    fc = d.get("fee_check") or {}
    if fc:
        out.append((f"Fees in and out {money(fc['round_trip_costs_at_t1'])} = {fc['costs_pct_of_gross_profit']:g}% "
                    "of profit at first target", ""))
    dv = d.get("dividend") or {}
    if dv.get("net_yield_pct") is not None:
        out.append((f"Dividend {dv['gross_yield_pct']:.2f}% -> {dv['net_yield_pct']:.2f}% after "
                    f"{dv['withholding_pct']:g}% US tax", ""))
    ea = d.get("earnings") or {}
    if ea.get("date"):
        out.append((f"Earnings {ea['date']} ({ea.get('days_away')} days)"
                    + (": price can jump past the stop" if ea.get("inside_window") else ""),
                    "warn" if ea.get("inside_window") else ""))
    sg = d.get("signals") or {}
    if sg.get("checked"):
        out.append((f"Trend: {sg.get('hint')}" + (f" ({'; '.join(sg.get('flags') or [])})" if sg.get("flags") else ""),
                    "ok" if sg.get("hint") == "OK" else "warn"))
    elif d.get("asset") != "tbill":
        out.append(("Trend: not checked (no signals run)", "warn"))
    for ln in _rs.sources_lines(d):
        out.append((ln.strip(), "bad" if "!!" in ln else ""))
    return out


def card(d):
    t = (d.get("ticker") or d.get("asset") or "?").upper()
    v = d.get("verdict") or "NO TRADE"
    if v == "TRADE" and not _plan_is_trade(d):          # an edited plan file is never shown as a BUY
        d = dict(d, verdict="NO TRADE", reasons=list(d.get("reasons") or []) +
                 ["plan says TRADE but carries reasons or is not placeable (edited file?): re-run the engine"])
        v = "NO TRADE"
    word, cls = VERDICT.get(v, ("NO BUY", "bad"))
    has_levels = bool(d.get("tranches"))
    head = f'<h3>{e(t)} <span class="badge {cls}">{e(word)}</span></h3>'
    sub = f'<div class="sub">{e(d.get("asset"))} · {e(d.get("profile"))} · {e(d.get("horizon"))}</div>'
    body, lines = "", []
    reasons = d.get("reasons") or []
    if v != "TRADE":
        for r in reasons or ["no reason given by the engine"]:
            body += reason_html(d, r)
        if v == "NO TRADE":
            for r in d.get("also_needed") or []:
                body += reason_html(d, r, "Also needed")
    if has_levels and d.get("asset") != "tbill":
        if v == "WATCHLIST":
            body += '<div class="sub" style="margin-top:8px">IF READY LATER, PLAN IS:</div>'
        rows, lines = trade_body(d)
        body += "<dl>" + "".join(f"<dt>{e(k)}</dt><dd>{e(x)}</dd>" for k, x in rows) + "</dl>"
    elif d.get("asset") == "tbill" and v == "TRADE":
        rows = [("Shares", d.get("shares")), ("Cost", money((d.get("order_value") or 0) + (d.get("buy_fee") or 0))),
                ("Est. net return (guess, not promise)", money(d.get("expected_net_return"))),
                ("Days just to pay fees", d.get("breakeven_holding_days"))]
        body += "<dl>" + "".join(f"<dt>{e(k)}</dt><dd>{e(x)}</dd>" for k, x in rows) + "</dl>"
    lines += screen_lines(d) + extra_lines(d)
    for w in d.get("warnings") or []:
        if str(w).startswith("SCREEN NOT RUN"):
            lines.append((f"!! {w}", "bad"))
    lines.append((quote_line(d), ""))
    if v == "TRADE":
        if str(d.get("placement_status", "")).startswith("ready"):
            lines.append(("READY. Price can still move.", "ok"))
        else:
            lines.append(("CHECK PRICE IN APP FIRST.", "warn"))
            if d.get("asset") != "tbill" and d.get("horizon") != "long" and d.get("stop_orders") != "yes":
                lines.append(("CHECK APP CAN DO STOP ORDER. IF NOT: SET ALERT, SELL BY HAND.", "warn"))
    elif v == "WATCHLIST":
        lines.append(("NOT READY. Get live price. Run again.", "warn"))
    body += '<ul class="lines">' + "".join(f'<li class="{c}">{e(x)}</li>' for x, c in lines) + "</ul>"
    return f'<article class="card">{head}{sub}{body}</article>'


def tiles(plans, state):
    a = (state or {}).get("actual") or {}
    first = next((p for p in plans if p.get("limits")), {})
    lim, cash = first.get("limits") or {}, first.get("cash_accounting") or {}
    out = []
    if a.get("portfolio_value") is not None:
        out.append(("Portfolio value", money(a["portfolio_value"]),
                    f"cash {money(a.get('cash'))} · holdings {money(a.get('holdings_value'))}", None))
    if cash:
        out.append(("Cash free to use", money(cash.get("available_cash")),
                    f"floor kept {money(cash.get('cash_floor'))} · on order {money(cash.get('unfilled_commitments'))}",
                    None))
    used = a.get("executable_stop_downside")
    unknown = len(a.get("unquantified") or []) + len(a.get("breached") or [])
    if used is not None and lim.get("open_risk_room") is not None:
        sub = f"room left {money(lim['open_risk_room'])} (before new buys)"
        if unknown:
            sub = f"+ {unknown} holding(s) with NO STOP: real risk unknown · " + sub
        out.append(("Open risk at stops", money(used), sub, (used, used + lim["open_risk_room"])))
    if lim.get("risk_budget_per_idea") is not None:
        out.append(("Loss budget per idea", money(lim["risk_budget_per_idea"]),
                    f"max per stock {money(lim.get('position_cap_total'))} · stop ≤ {e(lim.get('max_stop_distance_pct'))}%",
                    None))
    if lim.get("max_positions") is not None:
        n = lim.get("open_positions") or 0
        out.append(("Stock + ETF positions", f"{n} / {lim['max_positions']}", "", (n, lim["max_positions"])))
    h = ""
    for k, v, s, m in out:
        h += (f'<div class="tile"><div class="k">{e(k)}</div><div class="v">{e(v)}</div>'
              f'<div class="s">{e(s)}</div>{meter(*m) if m else ""}</div>')
    return f'<div class="tiles">{h}</div>' if h else ""


def holdings_table(state):
    a = (state or {}).get("actual") or {}
    rows = a.get("holdings") or []
    if not rows:
        return '<div class="sub">No holdings reported.</div>'
    bad = set(a.get("breached") or []) | set(a.get("unquantified") or [])
    body = ""
    for r in rows:
        t = r.get("ticker")
        flag = ' <span class="badge bad">CHECK</span>' if t in bad or not _num(r.get("downside")) else ""
        body += (f"<tr><td>{e(t)}{flag}</td><td>{e(r.get('asset'))}</td><td>{money(r.get('market_value'))}</td>"
                 f"<td>{money(r.get('unrealized_pnl'))}</td><td>{money(r.get('downside'))}</td>"
                 f"<td>{e(r.get('downside_type'))}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>Ticker</th><th>Type</th><th>Value</th><th>Gain/loss</th>'
            f'<th>Loss at level</th><th>Level</th></tr></thead><tbody>{body}</tbody></table></div>')


def sectors(state, projected):
    src = get(projected, "projected", "sector_exposure") or get(state, "actual", "sector_exposure") or {}
    label = "projected (plans added as orders, not executed)" if get(projected, "projected") else "actual"
    if not src:
        return ""
    top = max(src.values()) or 1
    rows = "".join(f'<div class="secrow"><span>{e(k)}</span>{meter(v, top)}<span>{money(v)}</span></div>'
                   for k, v in sorted(src.items(), key=lambda kv: -kv[1]))
    return f'<h2>Sector exposure — {e(label)}</h2>{rows}'


def render(plans, state=None, projected=None, market="", metals="", events="", notes=(), sources=(),
           title="Trade plan"):
    first = next((p for p in plans if p.get("profile")), {})
    asof = next((get(p, "quote", "time") for p in plans if get(p, "quote", "time")), "")
    p = [f'<h1>{e(title)}</h1><div class="sub">Risk {e(str(first.get("profile") or "n/a").upper())} · '
         f'hold {e(str(first.get("horizon") or "n/a").upper())} · broker {e(first.get("broker") or "n/a")}'
         + (f" · first quote {e(asof)}" if asof else "") + "</div>"]
    if (state or {}).get("reconciliation_required"):
        p.append('<div class="banner bad">A holding is past its stop or review level. No new trades until '
                 'you fix it in the app.</div>')
    mc = next((x.get("market_clock") for x in plans if x.get("market_clock")), None)
    if mc and not mc.get("open"):
        p.append(f'<div class="banner warn">NYSE closed ({e(mc.get("reason"))}). Next open '
                 f'{e(mc.get("next_open_new_york", "?"))} New York time. Plans are conditional.</div>')
    if not any(x.get("verdict") == "TRADE" and _plan_is_trade(x) for x in plans):
        p.append('<div class="banner warn">NO BUY TODAY. CASH OK.</div>')
    ctx = [(k, v) for k, v in (("Market", market), ("Gold / silver", metals), ("Watch", events)) if v]
    if ctx:
        p.append('<div class="ctx">' + "".join(f"<div><b>{e(k)}</b>{e(v)}</div>" for k, v in ctx) + "</div>")
    p.append(tiles(plans, state))
    order = {"TRADE": 0, "WATCHLIST": 1}
    p.append("<h2>Ideas</h2><div class=\"cards\">"
             + "".join(card(x) for x in sorted(plans, key=lambda x: order.get(x.get("verdict"), 2))) + "</div>")
    if state:
        p.append("<h2>Holdings</h2>" + holdings_table(state))
        p.append(sectors(state, projected))
    if notes:
        p.append("<h2>Notes</h2><ul>" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>")
    links, seen = [], set()
    for x in plans:                                       # every market-wide source the plans were built on
        for it in (x.get("sources") or {}).get("market_items") or []:
            u = it.get("url") or ""
            if u in seen or not u.startswith("https://"):
                continue
            seen.add(u)
            when = it.get("published_at") or it.get("observed_at") or ""
            links.append(f'<li><a href="{e(u)}" rel="noopener noreferrer">{e(it.get("source_name"))}: '
                         f'{e(it.get("what") or it.get("category"))}</a> <span class="sub">{e(when)}</span></li>')
    for s in sources:
        t, _, u = s.partition("|")
        if u.startswith("https://") or u.startswith("http://"):
            links.append(f'<li><a href="{e(u)}" rel="noopener noreferrer">{e(t or u)}</a></li>')
    if links:
        p.append('<h2>Sources</h2><ul class="src">' + "".join(links) + "</ul>")
    p.append(f'<div class="foot">{SAFETY_FOOTER}</div>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><main>'
            + "".join(p) + "</main></body></html>\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", nargs="+", required=True)
    ap.add_argument("--state", help="portfolio_state.py output (actual)")
    ap.add_argument("--projected", help="portfolio_state.py output built with --plans")
    ap.add_argument("--market", default="")
    ap.add_argument("--metals", default="")
    ap.add_argument("--events", default="")
    ap.add_argument("--note", action="append", default=[])
    ap.add_argument("--source", action="append", default=[], help='"Title|https://url"')
    ap.add_argument("--title", default="Trade plan")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    def load(f):
        with open(f) as fh:
            return json.load(fh)
    page = render([load(f) for f in a.plans], load(a.state) if a.state else None,
                  load(a.projected) if a.projected else None, a.market, a.metals, a.events,
                  a.note, a.source, a.title)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(page)
    else:
        sys.stdout.write(page)


if __name__ == "__main__":
    main()
