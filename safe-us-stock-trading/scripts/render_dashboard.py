#!/usr/bin/env python3
"""Per-run dashboard for the safe-us-stock-trading skill (v5.0).

v5.0 layout, top to bottom: TODAY (one coloured answer) -> DO THIS NOW -> YOUR CHOICES -> CHECKS ->
YOUR MONEY -> full numbers (folded). Colour always means the same thing, and every colour also has a
sign, so it reads without colour: green + = good / can win, yellow ! = wait / your call,
red x = stop / can lose, blue i = info.

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
import argparse
import datetime as _dt, html, json, sys
import os as _os
sys_path_dir = _os.path.dirname(_os.path.abspath(__file__))
import sys as _sys
if sys_path_dir not in _sys.path:
    _sys.path.insert(0, sys_path_dir)
import market_clock as _mc  # noqa: E402
import render_simple as _rs  # noqa: E402  (same WHY / FIX table as the text output)
from portfolio_state import plan_is_trade as _plan_is_trade  # noqa: E402

SAFETY_FOOTER = "YOU DECIDE. YOU PLACE ORDER. NOT ADVICE."
BOYCOTT_WORD = {"reviewed_no_match": ("Not on lists", "ok"), "flagged": ("Flagged", "warn"),
                "excluded": ("On list", "bad"), "unverified": ("Not checked", "warn")}
SHARIAH_WORD = {"PERMITTED": ("OK", "ok"), "REQUIRES_ACCEPTANCE": ("only if you accept", "warn"),
                "EXCLUDED": ("No", "bad"), "UNVERIFIED": ("Not checked", "warn")}
VERDICT = {"TRADE": ("BUY", "ok"), "WATCHLIST": ("WAIT", "warn"), "NO TRADE": ("NO BUY", "bad")}

CSS = """
:root{--bg:#f6f6f3;--card:#fff;--ink:#1b1b19;--mute:#66665f;--line:#e2e1da;
--ok:#17693f;--ok-bg:#e2f3e9;--warn:#7d5200;--warn-bg:#fcefcf;--bad:#a81f14;--bad-bg:#fde5e2;
--info:#1f5c99;--info-bg:#e4eef8}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#131312;--card:#1d1d1b;--ink:#eceae4;
--mute:#a5a49c;--line:#35342f;--ok:#62c896;--ok-bg:#153021;--warn:#e9bb5e;--warn-bg:#362b12;--bad:#f48a7f;
--bad-bg:#3b1a17;--info:#84b4e3;--info-bg:#17283a}}
:root[data-theme="dark"]{--bg:#131312;--card:#1d1d1b;--ink:#eceae4;--mute:#a5a49c;--line:#35342f;--ok:#62c896;
--ok-bg:#153021;--warn:#e9bb5e;--warn-bg:#362b12;--bad:#f48a7f;--bad-bg:#3b1a17;--info:#84b4e3;--info-bg:#17283a}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:20px 14px 48px}
h1{font-size:20px;margin:0 0 2px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;
color:var(--mute);margin:30px 0 10px}.sub{color:var(--mute);font-size:13px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.info{color:var(--info)}
.legend{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 0;font-size:12px;opacity:.85}
.chip{display:inline-block;font-size:12px;font-weight:700;padding:2px 9px;border-radius:99px;white-space:nowrap}
.chip.ok,.badge.ok{background:var(--ok-bg)}.chip.warn,.badge.warn{background:var(--warn-bg)}
.chip.bad,.badge.bad{background:var(--bad-bg)}.chip.info{background:var(--info-bg)}
.badge{font-size:11px;font-weight:700;letter-spacing:.05em;padding:2px 8px;border-radius:99px}
.banner{border-radius:10px;padding:10px 14px;margin:12px 0;font-weight:600}
.banner.bad{background:var(--bad-bg);color:var(--bad)}.banner.warn{background:var(--warn-bg);color:var(--warn)}
.banner.info{background:var(--info-bg);color:var(--ink);font-weight:500}.banner.ok{background:var(--ok-bg);color:var(--ok)}
.hero{border-radius:14px;padding:18px 20px;margin:14px 0 0;border-left:8px solid}
.hero.ok{background:var(--ok-bg);border-color:var(--ok)}.hero.warn{background:var(--warn-bg);border-color:var(--warn)}
.hero .k{font-size:12px;font-weight:700;letter-spacing:.08em}.hero .big{font-size:30px;font-weight:800;line-height:1.15}
.hero .say{color:var(--ink);font-size:16px;margin-top:6px}
.steps{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:6px 16px 6px 44px;margin:0}
.steps li{padding:10px 4px;border-top:1px solid var(--line);font-weight:650;font-size:17px}
.steps.fix{border-left:6px solid var(--bad)}.steps li:first-child{border-top:0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.opt,.tile,.card,.tbl,.ctx div{background:var(--card);border:1px solid var(--line);border-radius:12px}
.opt{padding:14px 16px;border-top:5px solid var(--line)}.opt.t-ok{border-top-color:var(--ok)}
.opt.t-warn{border-top-color:var(--warn)}.opt.t-bad{border-top-color:var(--bad)}.opt.t-info{border-top-color:var(--info)}
.opt h3{margin:0 0 2px;font-size:18px}.opt .tag{float:right}
.nums{margin:12px 0 10px;border-radius:8px;background:var(--bg);padding:2px 10px}
.nums>div{display:flex;justify-content:space-between;align-items:baseline;padding:6px 0;border-top:1px solid var(--line)}
.nums>div:first-child{border-top:0}.nums .k{font-size:12px;font-weight:700;letter-spacing:.05em;color:var(--mute)}
.nums .v{font-size:18px;font-weight:750;font-variant-numeric:tabular-nums}
.opt .chips{display:flex;flex-wrap:wrap;gap:6px}.odds{margin:6px 0 8px;font-size:13px;color:var(--mute)}
.hero .odds{color:var(--ink);font-size:14px;margin:8px 0 0}.opt .why{font-size:14px;margin-top:8px}
.ctx{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}
.ctx div{padding:10px 12px;border-left:5px solid var(--info)}.ctx b{display:block;font-size:12px;color:var(--info)}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.tile{padding:12px 14px}.tile .k{font-size:12px;font-weight:700;color:var(--mute)}.tile .v{font-size:22px;font-weight:750;
font-variant-numeric:tabular-nums}.tile .s{font-size:12px;color:var(--mute)}
.meter{height:8px;background:var(--line);border-radius:4px;margin-top:8px;overflow:hidden}
.meter i{display:block;height:100%;background:var(--info)}.meter i.ok{background:var(--ok)}
.meter i.warn{background:var(--warn)}.meter i.bad{background:var(--bad)}
.card{padding:14px 16px}.card h3{margin:0;font-size:18px;display:flex;align-items:center;gap:8px}
dl{display:grid;grid-template-columns:auto 1fr;gap:4px 12px;margin:12px 0;font-size:14px}
dt{color:var(--mute)}dd{margin:0;font-variant-numeric:tabular-nums;text-align:right;font-weight:600}
.lines{list-style:none;padding:0;margin:10px 0 0;font-size:13px}.lines li{padding:3px 0;border-top:1px solid var(--line)}
.reason{font-size:14px;margin-top:8px}.tbl{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:8px 12px;text-align:right;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
th:first-child,td:first-child{text-align:left}th{font-size:12px;color:var(--mute);font-weight:700}
table.chk td,table.chk th{text-align:left;vertical-align:top}table.chk td.ref{font-size:13px;color:var(--mute);word-break:break-word}
.secrow{display:grid;grid-template-columns:140px 1fr 110px;gap:10px;align-items:center;font-size:14px;margin:6px 0}
.secrow .meter{margin:0}.secrow span:last-child{text-align:right;font-variant-numeric:tabular-nums}
details{margin:10px 0}summary{cursor:pointer;font-weight:700;padding:8px 0}details .card{margin-top:6px}
a{color:var(--info)}ul.src{padding-left:18px;font-size:14px}
.foot{margin-top:28px;font-weight:800;text-align:center}
.more{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.more .row{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.more button{font:inherit;font-weight:650;padding:8px 14px;border-radius:99px;border:1px solid var(--line);
background:var(--info-bg);color:var(--ink);cursor:pointer}.more button:hover{border-color:var(--info)}
.more .mkt{align-items:center;font-weight:750;color:var(--warn)}.more .mkt.open{color:var(--ok)}
.more .mkt.open button{background:var(--ok);color:var(--bg);border-color:var(--ok)}
.more input{font:inherit;padding:8px 12px;border-radius:8px;border:1px solid var(--line);background:var(--bg);
color:var(--ink);flex:1;min-width:160px}
.more textarea{width:100%;min-height:74px;margin-top:8px;font:13px/1.4 ui-monospace,monospace;padding:8px;border-radius:8px;
border:1px solid var(--line);background:var(--bg);color:var(--ink)}.more .said{font-weight:700;min-height:1.4em}
@media print{.more,.more-h{display:none}}
@media (max-width:520px){.secrow{grid-template-columns:90px 1fr 90px}.hero .big{font-size:24px}}
@media print{:root,:root[data-theme="dark"],:root:not([data-theme="light"]){--bg:#fff;--card:#fff;--ink:#111;--mute:#555;
--line:#cfcfc8;--ok:#17693f;--ok-bg:#e2f3e9;--warn:#7d5200;--warn-bg:#fcefcf;--bad:#a81f14;--bad-bg:#fde5e2;
--info:#1f5c99;--info-bg:#e4eef8}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}main{max-width:none;padding:0}
.opt,.tile,.card,.hero,.steps,.ctx div,tr,.secrow{break-inside:avoid}h2{break-after:avoid}
details::details-content{content-visibility:visible;display:block}summary{list-style:none}}
"""


def e(x):
    return html.escape("" if x is None else str(x), quote=True)


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def money(x):
    """Numbers as $1,234.56; engine status strings (e.g. UNQUANTIFIED, BREACHED: ...) shown as-is."""
    if x is None:
        return "n/a"
    if not _num(x):
        word = str(x).split(":")[0]
        return {"UNQUANTIFIED": "NO STOP SET", "BREACHED": "PAST ITS STOP"}.get(word, word)
    return f"-${-x:,.2f}" if x < 0 else f"${x:,.2f}"


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


def meter(used, cap, tone=False):
    """Bar width only. Labels always show the engine's own figures. tone=True colours the bar by how full
    it is: green under 60%, yellow under 90%, red above."""
    try:
        w = 0 if not cap or cap <= 0 else max(0.0, min(100.0, used / cap * 100))
    except TypeError:
        w = 0
    cls = ("ok" if w < 60 else "warn" if w < 90 else "bad") if tone else ""
    return f'<div class="meter"><i class="{cls}" style="width:{w:.1f}%"></i></div>'


SIGN = {"ok": "+", "warn": "!", "bad": "x", "info": "i"}


def chip(text, cls):
    """Coloured label that also carries a sign, so it reads without colour."""
    return f'<span class="chip {cls}">{SIGN.get(cls, "")} {e(text)}</span>'


def tone(label):
    if label in ("NOT ON LISTS", "HALAL"):
        return "ok"
    return "bad" if label in ("ON BOYCOTT LIST", "NOT HALAL") else "warn"


def linkify(text):
    """Escaped text; https links become clickable. Nothing else is trusted."""
    out = []
    for tok in str(text or "").split(" "):
        if tok.startswith("https://"):
            u = tok.rstrip(".,;)")
            out.append(f'<a href="{e(u)}" rel="noopener noreferrer">link</a>{e(tok[len(u):])}')
        else:
            out.append(e(tok))
    return " ".join(out)


def best_pick(plans):
    """Same rule as the text output (render_simple.recommended_plan): a clean price trade, else None (cash)."""
    return _rs.recommended_plan(plans)


def _chips(d):
    bl, _ = _rs.boycott_ref(d.get("boycott"))
    hl, _ = _rs.halal_ref(d.get("shariah"))
    return (chip(bl if "BOYCOTT" in bl else f"BOYCOTT: {bl}", tone(bl))
            + chip(hl if "HALAL" in hl else f"HALAL: {hl}", tone(hl)))


def _buy_say(d):
    tr = d.get("tranches") or [{}]
    if len(tr) > 1:
        return (f'{e(d.get("shares"))} shares in {len(tr)} steps: '
                + ", ".join(f'{e(x.get("shares"))} at {px(x.get("price"))}' for x in tr))
    return f'{e(d.get("shares"))} shares at {px(tr[0].get("price"))} or lower'


def _nums(rows):
    return '<div class="nums">' + "".join(
        f'<div><div class="k">{e(k)}</div><div class="v {c}">{e(v)}</div></div>' for k, v, c in rows) + "</div>"


def hero(plans):
    d = best_pick(plans)
    if d is not None:
        t = (d.get("ticker") or "?").upper()
        cost = (d.get("total_order_value") or 0) + (d.get("total_buy_fees") or 0)
        rl, ra = _rs.plan_risk(d)
        at = " (at your review price, not an auto sell)" if d.get("horizon") == "long" else ""
        return (f'<div class="hero ok"><div class="k ok">TODAY</div><div class="big ok">BUY {e(t)}</div>'
                f'<div class="say">{_buy_say(d)}. Pay {money(cost)}. '
                f'<b class="bad">Can lose {money(ra)}</b>{at}. '
                f'<b class="ok">Can win {money(_rs.plan_profit(d))}</b>. Not on boycott lists. '
                + ("Halal only if you accept it (see CHECKS)." if _rs.halal_ref(d.get("shariah"))[0] != "HALAL" else "Halal.")
                + (f'<div class="odds">{e(sentence(_rs.odds_words(d)))}</div>' if _rs.odds_words(d) else "")
                + "</div></div>")
    yours = [x for x in plans if _rs.plan_kind(x) in ("buy", "park")]
    if yours:
        names = ", ".join((x.get("ticker") or "?").upper() for x in yours)
        return (f'<div class="hero warn"><div class="k warn">TODAY</div><div class="big warn">YOUR CALL: {e(names)}</div>'
                '<div class="say">These fit your money rules, but a check failed, was not run, or the fund pays interest. '
                'Look at CHECKS below. Keeping cash is also fine.</div></div>')
    why = []
    for x in plans[:2]:
        w, _f = _rs.explain((x.get("reasons") or [""])[0])
        if w:
            why.append(f'<b>{e((x.get("ticker") or "?").upper())}</b>: {e(w.capitalize())}')
    return ('<div class="hero warn"><div class="k warn">TODAY</div><div class="big warn">NO BUY TODAY. KEEP CASH.</div>'
            '<div class="say">Nothing passed today. Keeping cash is a good result.'
            + (" Why: " + " ".join(why) if why else "") + '</div></div>')


def option_cards(plans):
    """One card per option, in the same order and with the same letters as the text output."""
    rows, rec = _rs.option_rows(plans)
    out = []
    for L, _text, _labels, _ok, _dot, d in rows:
        if d is None:
            cls = "ok" if rec == L else "info"
            out.append(f'<div class="opt t-{cls}"><span class="tag">{chip("BEST PICK" if rec == L else "ALWAYS OK", cls)}</span>'
                       f'<h3>{L}. KEEP CASH</h3><div class="sub">Do nothing. Pay $0. Can lose $0. Can win $0.</div></div>')
            continue
        t, kind = (d.get("ticker") or d.get("asset") or "?").upper(), _rs.plan_kind(d)
        if kind == "buy":
            clean = _rs.is_clean(d)
            cls = "ok" if clean else "warn"
            tag = chip("BEST PICK", "ok") if rec == L else (chip("OK", "ok") if clean else chip("YOUR CALL", "warn"))
            cost = (d.get("total_order_value") or 0) + (d.get("total_buy_fees") or 0)
            _rl, ra = _rs.plan_risk(d)
            lose = "CAN LOSE (AT REVIEW PRICE)" if d.get("horizon") == "long" else "CAN LOSE"
            out.append(f'<div class="opt t-{cls}"><span class="tag">{tag}</span><h3>{L}. BUY {e(t)}</h3>'
                       f'<div class="sub">{_buy_say(d)}</div>'
                       + _nums([("PAY", money(cost), ""), (lose, money(ra), "bad"),
                                ("CAN WIN", money(_rs.plan_profit(d)), "ok")])
                       + (f'<div class="sub odds">{e(sentence(_rs.odds_words(d)))}</div>' if _rs.odds_words(d) else "")
                       + f'<div class="chips">{_chips(d)}</div>'
                       + ('' if clean else '<div class="why warn">Failed a check. Shown because you chose FLAG. You decide.</div>')
                       + '</div>')
        elif kind == "park":
            cost = (d.get("order_value") or 0) + (d.get("buy_fee") or 0)
            out.append(f'<div class="opt t-warn"><span class="tag">{chip("YOUR CALL", "warn")}</span>'
                       f'<h3>{L}. PARK CASH IN {e(t)}</h3><div class="sub">{e(d.get("shares"))} shares. Pays interest. Not a price trade.</div>'
                       + _nums([("PAY", money(cost), ""), ("MAY EARN (GUESS)", money(d.get("expected_net_return")), "")])
                       + f'<div class="chips">{_chips(d)}</div></div>')
        else:
            why, fix = _rs.fix_for(d, (d.get("reasons") or [""])[0])
            cls = "warn" if kind == "wait" else "bad"
            out.append(f'<div class="opt t-{cls}"><span class="tag">{chip("WAIT" if kind == "wait" else "NO BUY", cls)}</span>'
                       f'<h3>{L}. {e(t)}</h3><div class="why {cls}"><b>Why:</b> {e(why or (d.get("reasons") or ["?"])[0])}</div>'
                       + (f'<div class="why"><b>Fix:</b> {e(fix)}</div>' if fix else '')
                       + f'<div class="chips" style="margin-top:8px">{_chips(d)}</div></div>')
    return '<div class="grid">' + "".join(out) + "</div>"


def account_todos(state):
    """Things to fix in the user's own account, from the state the user gave. Plain words, no numbers invented."""
    a = (state or {}).get("actual") or {}
    out = [f"{t} IS PAST ITS STOP. IN YOUR APP: SELL IT, OR SET A NEW STOP. NO NEW BUYS UNTIL THEN."
           for t in a.get("breached") or []]
    out += [f"{t} HAS NO STOP. PICK A PRICE WHERE YOU WOULD SELL AND SET IT IN YOUR APP. THEN TELL ME THE PRICE."
            for t in a.get("unquantified") or []]
    return out


def sentence(text):
    """'TWO WORDS. MORE.' -> 'Two words. More.'"""
    return ". ".join(x.strip().capitalize() for x in str(text).split(". ") if x.strip())


MOODS = {"RISK-ON": ("ok", "PEOPLE ARE BUYING. PRICES TEND TO RISE."),
         "NEUTRAL": ("info", "MIXED. NO CLEAR DIRECTION."),
         "RISK-OFF": ("bad", "PEOPLE ARE CAREFUL. PRICES FALL MORE EASILY.")}


FACT_MAX_AGE_DAYS = 7


def fact_age_days(text, today=None):
    """Days since a fact's YYYY-MM-DD date, or None when the date cannot be read or is in the future."""
    try:
        d = _dt.date.fromisoformat(str(text or "").strip()[:10])
    except ValueError:
        return None
    age = ((today or _dt.date.today()) - d).days
    return age if age >= 0 else None


def clean_analysis(an, today=None):
    """Keep only what can be stood behind. A fact needs words, an https source link and a YYYY-MM-DD date
    no more than FACT_MAX_AGE_DAYS old; anything else is dropped and counted. Returns (analysis, dropped)."""
    if not isinstance(an, dict):
        return None, 0
    facts, dropped = [], 0
    for f in an.get("facts") or []:
        age = fact_age_days(f.get("date"), today) if isinstance(f, dict) else None
        ok = (isinstance(f, dict) and str(f.get("what") or "").strip() and str(f.get("url") or "").startswith("https://")
              and age is not None and age <= FACT_MAX_AGE_DAYS)
        if ok:
            facts.append(f)
        else:
            dropped += 1
    out = dict(an, facts=facts, mood=str(an.get("mood") or "").upper())
    return (out if out["mood"] in MOODS and facts else None), dropped


def analysis_section(an):
    """'My read of the market': the analyst's view, every fact with its source and date, both sides,
    what would change the view. An opinion built on cited facts, never a promise."""
    an, dropped = clean_analysis(an)
    if an is None:
        return ""
    cls, mood_words = MOODS[an["mood"]]
    out = ('<h2>My read of the market</h2>'
           f'<div class="hero t-{cls}" style="border-left-color:var(--{cls});background:var(--{cls}-bg)">'
           f'<div class="k {cls}">MARKET MOOD</div><div class="big {cls}" style="font-size:24px">{e(an["mood"])}</div>'
           f'<div class="say">{e(mood_words)} {e(an.get("one_line") or "")}</div></div>')
    rows = "".join(
        f'<tr><td><b>{e(f.get("what"))}</b></td><td>{e(f.get("means") or "")}</td>'
        f'<td class="ref"><a href="{e(f["url"])}" rel="noopener noreferrer">{e(f.get("source") or "source")}</a> '
        f'{e(_dt.date.fromisoformat(str(f["date"])[:10]).strftime("%d %b %Y"))}</td></tr>' for f in an["facts"])
    out += ('<div class="tbl" style="margin-top:10px"><table class="chk"><thead><tr><th>What happened</th>'
            f'<th>What it means</th><th>Proof</th></tr></thead><tbody>{rows}</tbody></table></div>')
    if dropped:
        out += f'<div class="sub">{dropped} point(s) left out: no source I could show, or older than {FACT_MAX_AGE_DAYS} days.</div>'

    def lst(title, items, cls_):
        items = [x for x in items or [] if isinstance(x, dict) and x.get("kind")]
        if not items:
            return ""
        return (f'<div class="opt t-{cls_}"><h3>{e(title)}</h3>' + "".join(
            f'<div class="why"><b>{e(str(x["kind"]).upper())}</b>: {e(x.get("why") or "")}</div>' for x in items) + "</div>")
    two = lst("Conditions help", an.get("favours"), "ok") + lst("Conditions hurt", an.get("against"), "bad")
    if two:
        out += f'<div class="grid" style="margin-top:10px">{two}</div>'
    sc = [x for x in an.get("scenarios") or [] if isinstance(x, dict) and x.get("name")]
    if sc:
        out += ('<div class="tbl" style="margin-top:10px"><table class="chk"><thead><tr><th>If this happens</th>'
                '<th>Then likely</th><th>Watch</th></tr></thead><tbody>' + "".join(
                    f'<tr><td><b>{e(str(x["name"]).upper())}</b></td><td>{e(x.get("then") or "")}</td>'
                    f'<td>{e(x.get("watch") or "")}</td></tr>' for x in sc) + "</tbody></table></div>")
    cm = [str(x) for x in an.get("change_my_mind") or [] if str(x).strip()]
    if cm:
        out += '<div class="sub" style="margin-top:8px"><b>I would change this view if:</b> ' + e("; ".join(cm)) + ".</div>"
    out += ('<div class="sub" style="margin-top:6px">This is my reading of the facts above. Markets often do the '
            'opposite of what the facts suggest. It is not a promise and not licensed advice.</div>')
    return out


def money_plan_section(mp):
    """'Your money plan: when and what kind' from money_plan.py. Numbers copied; times in the user's zone."""
    if not isinstance(mp, dict) or not mp.get("steps"):
        return ""
    lim = mp.get("limits") or {}
    out = ('<h2>Your money plan: when, and what kind</h2>'
           f'<div class="banner info">i Keep <b>{money(lim.get("safety_cash"))}</b> as safety cash. '
           f'<b>{money(lim.get("planned_amount"))}</b> to invest, in {e(mp.get("steps_count"))} step(s). '
           'You chose the steps. They spread the timing risk. They do not make a profit more likely.</div>')
    for bl in mp.get("blockers") or []:
        out += f'<div class="banner bad">x FIRST: {e(str(bl).upper())}</div>'
    rows = ""
    for r in mp["steps"]:
        iso = _rs.ny_wall(r.get("opens_new_york"))
        when = _rs.when(iso) if (_rs.LOCAL and iso) else f'{r.get("day")} 09:30 NEW YORK TIME'
        rows += (f'<tr><td><b>STEP {e(r.get("step"))}</b></td><td>ASK ME ON OR AFTER {e(when)}</td>'
                 f'<td>{money(r.get("up_to"))}</td></tr>')
    out += ('<div class="tbl"><table class="chk"><thead><tr><th>Step</th><th>When</th><th>Use up to</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')
    kinds = "".join(f'<tr><td>{e(str(k.get("kind")).upper())}</td><td>{money(k.get("up_to"))}'
                    + (f' <span class="sub">{e(k.get("note"))}</span>' if k.get("note") else "") + "</td></tr>"
                    for k in mp.get("kinds") or [])
    out += ('<div class="tbl" style="margin-top:10px"><table class="chk"><thead><tr><th>What kind of thing</th>'
            f'<th>Most you may put in</th></tr></thead><tbody>{kinds}</tbody></table></div>')
    out += ('<div class="sub" style="margin-top:8px">Which exact name? I pick it on the day, from fresh prices and both '
            f'checks. A step with nothing good is skipped. Most you can lose on one idea: {money(lim.get("loss_limit_per_idea"))}. '
            f'Room for risk in total: {money(lim.get("total_risk_room"))}.</div>')
    return out


def results_section(journal):
    """'Is this making you money?' from a journal.py report. Always shown: with no record it says so."""
    head = "<h2>Is this making you money?</h2>"
    if not isinstance(journal, dict):
        return (head + '<div class="banner warn">! NO RECORD YET. A plan only makes money if you follow it and '
                'check the results. Tell me each fill (shares, price, fee) and this box will show the truth.</div>')
    cls, words = _rs.journal_words(journal)
    out = head + f'<div class="banner {cls}">{SIGN.get(cls, "")} {e(words)}</div>'
    n = journal.get("closed_trades") or 0
    if not n:
        return out
    pnl = journal.get("total_pnl")
    b = journal.get("benchmark") or {}
    rows = [("Trades finished", str(n), ""),
            ("Money made or lost, after fees", ("+" if _num(pnl) and pnl > 0 else "") + money(pnl),
             "ok" if _num(pnl) and pnl > 0 else "bad"),
            ("Trades that made money", f"{journal.get('win_rate_pct')}%", ""),
            ("Fees paid", money(journal.get("total_fees")), "")]
    if b.get("available"):
        d_ = b.get("skill_minus_benchmark")
        rows.append(("Compared with just holding the fund", ("+" if _num(d_) and d_ > 0 else "") + money(d_),
                     "ok" if _num(d_) and d_ > 0 else "bad"))
    return out + '<div class="tiles">' + "".join(
        f'<div class="tile"><div class="k">{e(k)}</div><div class="v {c}">{e(v)}</div></div>' for k, v, c in rows) + "</div>"


def checks_table(plans):
    rows = _rs.screen_rows(plans)
    if not rows:
        return ""
    body = "".join(f'<tr><td><b>{e(t)}</b></td><td>{chip(bl, tone(bl))}</td><td class="ref">{linkify(br)}</td>'
                   f'<td>{chip(hl, tone(hl))}</td><td class="ref">{linkify(hr)}</td></tr>' for t, bl, br, hl, hr in rows)
    return ('<h2>Checks: boycott and halal</h2><div class="tbl"><table class="chk"><thead><tr><th>What</th><th>Boycott</th>'
            '<th>Proof</th><th>Halal</th><th>Proof</th></tr></thead><tbody>' + body + "</tbody></table></div>")


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
    return f"Price seen {_rs.when(q['time'])} ({st}, {q.get('source') or 'source?'}){mp}. Good only for this price."


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
    why, fix = _rs.fix_for(d, r)
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
        out.append(("All your money here", money(a["portfolio_value"]),
                    f"cash {money(a.get('cash'))} · holdings {money(a.get('holdings_value'))}", None))
    if cash:
        out.append(("Cash you can use now", money(cash.get("available_cash")),
                    f"safety cash kept {money(cash.get('cash_floor'))} · on order {money(cash.get('unfilled_commitments'))}",
                    None))
    used = a.get("executable_stop_downside")
    unknown = len(a.get("unquantified") or []) + len(a.get("breached") or [])
    if used is not None and lim.get("open_risk_room") is not None:
        sub = f"room left {money(lim['open_risk_room'])} (before new buys)"
        if unknown:
            sub = f"+ {unknown} holding(s) with NO STOP: real risk unknown · " + sub
        out.append(("Money at risk now", money(used) + (" + unknown" if unknown else ""), sub,
                    (used, used + lim["open_risk_room"])))
    if lim.get("risk_budget_per_idea") is not None:
        out.append(("Loss limit per idea", money(lim["risk_budget_per_idea"]),
                    f"max per stock {money(lim.get('position_cap_total'))} · stop ≤ {e(lim.get('max_stop_distance_pct'))}%",
                    None))
    if lim.get("max_positions") is not None:
        n = lim.get("open_positions") or 0
        out.append(("Things you hold", f"{n} of {lim['max_positions']} allowed", "", (n, lim["max_positions"])))
    h = ""
    for k, v, s, m in out:
        h += (f'<div class="tile"><div class="k">{e(k)}</div><div class="v">{e(v)}</div>'
              f'<div class="s">{e(s)}</div>{meter(*m, tone=True) if m else ""}</div>')
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
        pnl = r.get("unrealized_pnl")
        pc = ("ok" if pnl > 0 else "bad" if pnl < 0 else "") if _num(pnl) else ""
        dc = "bad" if not _num(r.get("downside")) else ""
        body += (f"<tr><td><b>{e(t)}</b>{flag}</td><td>{money(r.get('market_value'))}</td>"
                 f"<td class=\"{pc}\">{'+' if _num(pnl) and pnl > 0 else ''}{money(pnl)}</td>"
                 f"<td class=\"{dc}\">{money(r.get('downside'))}</td>"
                 f"<td>{e(r.get('downside_type'))}</td></tr>")
    return ('<div class="tbl"><table><thead><tr><th>You hold</th><th>Worth now</th><th>Up / down</th>'
            f'<th>Can lose (at your stop)</th><th>Stop type</th></tr></thead><tbody>{body}</tbody></table></div>')


def sectors(state, projected):
    src = get(projected, "projected", "sector_exposure") or get(state, "actual", "sector_exposure") or {}
    label = "projected (plans added as orders, not executed)" if get(projected, "projected") else "actual"
    if not src:
        return ""
    top = max(src.values()) or 1
    rows = "".join(f'<div class="secrow"><span>{e(k)}</span>{meter(v, top)}<span>{money(v)}</span></div>'
                   for k, v in sorted(src.items(), key=lambda kv: -kv[1]))
    return f'<h2>Where your money sits — {e(label)}</h2>{rows}'


def universe():
    """Sector pools for the "check more" buttons (universe.json). A broken file means no sector buttons."""
    try:
        with open(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "universe.json")) as f:
            return [str(k) for k in (json.load(f).get("sectors") or {})]
    except (OSError, ValueError, AttributeError):
        return []


MORE_JS = """
(function(){var box=document.getElementById('more-text'),said=document.getElementById('more-said');
function put(t){box.value=t;box.focus();box.select();
var done=function(){said.textContent='COPIED. PASTE IT IN THE CHAT WITH CLAUDE.'};
var fail=function(){said.textContent='SELECTED BELOW. COPY IT AND PASTE IT IN THE CHAT WITH CLAUDE.'};
try{navigator.clipboard.writeText(t).then(done,fail)}catch(e){fail()}}
var mk=document.getElementById('more-market');
if(mk){var hol=JSON.parse(mk.getAttribute('data-hol')),early=JSON.parse(mk.getAttribute('data-early'));
var F=new Intl.DateTimeFormat('en-CA',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',
hour:'2-digit',minute:'2-digit',weekday:'short',hourCycle:'h23'});
var ny=function(d){var o={};F.formatToParts(d).forEach(function(x){o[x.type]=x.value});
return {day:o.year+'-'+o.month+'-'+o.day,min:(+o.hour)*60+(+o.minute),wd:o.weekday}};
var sess=function(n){return n.wd!=='Sat'&&n.wd!=='Sun'&&hol.indexOf(n.day)<0};
var span=function(m){return (m>=60?Math.floor(m/60)+' H ':'')+(m%60)+' MIN'};
var tick=function(){var now=new Date(),n=ny(now),end=early.indexOf(n.day)<0?960:780,b=mk.querySelector('button');
if(sess(n)&&n.min>=570&&n.min<end){mk.className='row mkt open';
mk.querySelector('.st').textContent='+ US MARKET IS OPEN NOW. CLOSES IN '+span(end-n.min)+'.';b.textContent='Follow the market now';return}
var t=new Date(now.getTime()),left=-1;
for(var i=0;i<14*24*4&&left<0;i++){t=new Date(t.getTime()+15*60000);var x=ny(t);
if(sess(x)&&x.min>=570&&x.min<585)left=Math.round((t-now)/60000)-(x.min-570)}
mk.className='row mkt';mk.querySelector('.st').textContent='! US MARKET IS CLOSED.'+(left>=0?' OPENS IN '
+(left>=1440?Math.floor(left/1440)+' D ':'')+span(left%1440)+' ('+new Date(now.getTime()+left*60000).toLocaleString([],
{weekday:'short',hour:'2-digit',minute:'2-digit'})+' YOUR TIME).':'');
b.textContent='Get a watch list for the open'};
try{tick();setInterval(tick,60000)}catch(e){mk.querySelector('.st').textContent=''}}
document.querySelectorAll('.more button[data-ask]').forEach(function(b){b.addEventListener('click',function(){
var ask=b.getAttribute('data-ask');
if(b.hasAttribute('data-typed')){var v=document.getElementById('more-tickers').value.replace(/[^A-Za-z0-9., -]/g,'').trim();
if(!v){said.textContent='TYPE ONE OR MORE TICKERS FIRST.';return}ask=ask.replace('{T}',v.toUpperCase())}
put(ask+' '+box.getAttribute('data-same'))})})})();
"""


def more_section(plans, state):
    """v5.3: buttons that write a ready follow-up request (sector, new ideas, tickers, live prices).
    The page cannot run a check by itself: a button copies the request, the user pastes it in the chat."""
    first = next((p for p in plans if p.get("profile")), {})
    bits = [f"risk {first.get('profile')}" if first.get("profile") else "",
            f"hold {first.get('horizon')}" if first.get("horizon") else "",
            f"app {first.get('broker')}" if first.get("broker") else "",
            f"boycott {get(first, 'boycott', 'mode')}" if get(first, "boycott", "mode") else "",
            f"halal {get(first, 'shariah', 'mode')}" if get(first, "shariah", "mode") else ""]
    same = ("Same answers as my last run" + (" (" + ", ".join(b for b in bits if b) + ")" if any(bits) else "")
            + ". My account is the same as last time unless I say so here: ")
    looked = ", ".join(sorted({str(p.get("ticker")).upper() for p in plans if p.get("ticker")}))
    held = ", ".join(sorted({str(h.get("ticker")).upper() for h in ((state or {}).get("actual") or state or {}).get("holdings") or [] if h.get("ticker")}))
    skip = f" Already checked: {looked}." if looked else ""

    def btn(label, ask, typed=False):
        return f'<button type="button" data-ask="{e("quick: " + ask)}"{" data-typed" if typed else ""}>{e(label)}</button>'
    made = next((get(p, "quote", "time") for p in plans if get(p, "quote", "time")), "")
    follow = ("follow the market now: live prices for " + " and ".join(x for x in (
        f"what I hold ({held})" if held else "", f"the ideas on this page ({looked})" if looked else "") if x)
        if (held or looked) else "follow the market now")
    follow += (f", what changed since {_rs.when(made)}" if made else "") + ", and whether any plan is ready to place."
    market = (f'<div class="row mkt" id="more-market" data-hol="{e(json.dumps(sorted(_mc.NYSE_HOLIDAYS)))}" '
              f'data-early="{e(json.dumps(sorted(_mc.NYSE_EARLY_CLOSE)))}"><span class="st"></span>'
              + btn("Follow the market now", follow) + "</div>")
    rows = [market, '<div class="row">' + btn("Find new ideas", "find new ideas, different from the ones on this page." + skip)
            + btn("Same ideas, live prices", f"check {looked} again with live prices." if looked else "check again with live prices.")
            + (btn("Review what I hold", f"review what I hold ({held}).") if held else "") + "</div>"]
    secs = universe()
    if secs:
        rows.append('<div class="sub">One sector:</div><div class="row">'
                    + "".join(btn(s, f"check the sector {s}: a wide first look, then the best 3." + skip) for s in secs) + "</div>")
    rows.append('<div class="sub">Your own tickers:</div><div class="row">'
                '<input id="more-tickers" type="text" placeholder="MSFT, COST" maxlength="80" autocomplete="off">'
                + btn("Check these", "check these tickers: {T}.", typed=True) + "</div>")
    return ('<h2 class="more-h">Check more</h2><div class="more"><div class="sub">Tap one. It writes the request for you. '
            'Paste it in the chat with Claude. A follow-up reuses your answers and saved checks, so it is quicker.</div>'
            + "".join(rows) + '<div class="said ok" id="more-said" aria-live="polite"></div>'
            f'<textarea id="more-text" readonly aria-label="Request to paste in the chat" data-same="{e(same)}"></textarea></div>')


def prescreen_section(ps):
    """v5.3: names checked ahead of time by prescreen.py (boycott and halal only: no price, no plan)."""
    rows = (ps or {}).get("rows") if isinstance(ps, dict) else None
    if not rows:
        return ""
    cls = {"REVIEWED_NO_MATCH": "ok", "EXCLUDED": "bad", "FLAGGED": "warn", "PERMITTED": "ok",
           "REQUIRES_ACCEPTANCE": "warn"}
    word = {"REVIEWED_NO_MATCH": "NOT ON LISTS", "EXCLUDED": "ON BOYCOTT LIST", "FLAGGED": "FLAGGED",
            "UNVERIFIED": "CAN'T CONFIRM", "PERMITTED": "HALAL", "REQUIRES_ACCEPTANCE": "ONLY IF YOU ACCEPT"}
    clean = [r for r in rows if r.get("boycott") == "REVIEWED_NO_MATCH" and r.get("halal") == "PERMITTED"]
    body = "".join(
        f'<tr><td><b>{e(r.get("ticker"))}</b> <span class="sub">{e(r.get("sector"))}</span></td>'
        f'<td>{chip(word.get(r.get("boycott"), str(r.get("boycott"))), cls.get(r.get("boycott"), "warn"))}</td>'
        f'<td>{chip(word.get(r.get("halal"), "NOT HALAL" if r.get("halal") == "EXCLUDED" else str(r.get("halal"))), "bad" if r.get("halal") == "EXCLUDED" else cls.get(r.get("halal"), "warn"))}</td>'
        f'<td class="ref">{e(r.get("note"))}</td></tr>' for r in rows)
    return (f'<h2>Checked ahead of time</h2><details><summary>{len(rows)} names checked on {e(ps.get("as_of"))}: '
            f'{len(clean)} pass both checks</summary><div class="sub">Boycott and halal checks only. No price was '
            'looked at and nothing here is a plan. A check is good for 30 days.</div>'
            f'<div class="tbl"><table class="chk"><thead><tr><th>Name</th><th>Boycott</th><th>Halal</th><th>Note</th></tr>'
            f'</thead><tbody>{body}</tbody></table></div></details>')


def render(plans, state=None, projected=None, market="", metals="", events="", notes=(), sources=(),
           title="Trade plan", skipped=(), tz="", journal=None, money_plan=None, analysis=None, prescreen=None):
    _rs.set_local(tz)
    # never-researched plans (screens not run) are listed once under Skipped, not as red cards
    skipped = list(skipped) + [f"{(x.get('ticker') or '?').upper()}|not researched (checks not run), not a candidate"
                               for x in plans if _rs.never_researched(x)]
    plans = [x for x in plans if not _rs.never_researched(x)]
    kinds = {"buy": 0, "park": 1, "wait": 2, "no": 3}
    plans = sorted(plans, key=lambda x: (kinds[_rs.plan_kind(x)], not _rs.is_clean(x)))
    first = next((p for p in plans if p.get("profile")), {})
    asof = next((get(p, "quote", "time") for p in plans if get(p, "quote", "time")), "")
    p = [f'<h1>{e(title)}</h1>']
    if plans:                               # with nothing priced there is no risk level, hold time or app to show
        p.append('<div class="sub">' + (f"Prices from {e(_rs.when(asof))} · " if asof else "")
                 + f'Risk {e(str(first.get("profile") or "n/a").upper())} · '
                 f'hold {e(str(first.get("horizon") or "n/a").upper())} · app {e(first.get("broker") or "n/a")}</div>')
    if (state or {}).get("reconciliation_required"):
        p.append('<div class="banner bad">x A thing you hold is past its stop. No new trades until '
                 'you fix it in the app.</div>')
    mc = next((x.get("market_clock") for x in plans if x.get("market_clock")), None)
    if mc and not mc.get("open"):
        p.append(f'<div class="banner warn">! NYSE closed ({e(mc.get("reason"))}). US market opens '
                 f'{e(_rs.market_open_words(mc))}. Ask again then.</div>')
    pick = best_pick(plans)
    plan_only = not plans and isinstance(money_plan, dict) and money_plan.get("steps")
    if plan_only:                       # a money plan with no ideas priced yet: not a "no buy" verdict
        r0 = money_plan["steps"][0]
        iso = _rs.ny_wall(r0.get("opens_new_york"))
        w0 = _rs.when(iso) if (_rs.LOCAL and iso) else f'{r0.get("day")} 09:30 NEW YORK TIME'
        p.append('<div class="hero warn"><div class="k warn">TODAY</div><div class="big warn">PLAN ONLY. NOTHING PRICED YET.</div>'
                 '<div class="say">This page is your money plan. No stock was checked or priced for it.</div></div>')
        steps = [f"1. ASK ME FOR A TRADE ON OR AFTER {w0}. USE UP TO {money(r0.get('up_to'))} THAT DAY.",
                 "2. I CHECK THE IDEAS THAT DAY AND SHOW YOUR CHOICES. NO GOOD IDEA MEANS NO BUY.",
                 "3. COME BACK FOR THE NEXT STEP ON ITS DAY. UNUSED MONEY STAYS CASH."]
    else:
        p.append(hero(plans))
        steps = [ln.strip() for ln in _rs.action_lines(plans, events)[1:] if ln.strip()]
    p.append('<h2>Do this now</h2><ol class="steps">'
             + "".join(f"<li>{e(ln.split('. ', 1)[1] if '. ' in ln else ln)}</li>" for ln in steps) + "</ol>")
    todos = account_todos(state)
    if todos:
        p.append('<h2>Also fix in your app</h2><ol class="steps fix">' + "".join(f"<li>{e(t)}</li>" for t in todos) + "</ol>")
    p.append(analysis_section(analysis))
    p.append(money_plan_section(money_plan))
    can_place = any(_rs.plan_kind(x) in ("buy", "park") for x in plans)
    if not plan_only:
        p.append(f"<h2>{'Your choices' if can_place else 'What I looked at'}</h2>" + option_cards(plans))
    p.append(checks_table(plans))
    p.append(more_section(plans, state))
    p.append(prescreen_section(prescreen))
    p.append('<div class="legend">' + chip("GREEN = GOOD / CAN WIN", "ok") + chip("YELLOW = WAIT / YOUR CALL", "warn")
             + chip("RED = STOP / CAN LOSE", "bad") + chip("BLUE = INFO", "info") + "</div>")
    p.append(results_section(journal))
    ctx = [(k, v) for k, v in (("Market", market), ("Gold / silver", metals), ("Watch these days", events)) if v]
    if ctx:
        p.append('<h2>What is going on</h2><div class="ctx">'
                 + "".join(f"<div><b>i {e(k)}</b>{e(v)}</div>" for k, v in ctx) + "</div>")
    t = tiles(plans, state)
    if t or state:
        p.append("<h2>More, if you want it</h2><details><summary>Your money and what you hold</summary>" + t
                 + ('<div style="margin-top:10px">' + holdings_table(state) + "</div>" + sectors(state, projected) if state else "")
                 + "</details>")
    if plans:
        p.append("".join(
            f'<details{" open" if x is pick else ""}>'
            f'<summary>{e((x.get("ticker") or x.get("asset") or "?").upper())}: full plan and safety notes</summary>'
            f'{card(x)}</details>' for x in plans))
    if skipped:
        p.append("<h2>Skipped</h2><ul>" + "".join(
            f"<li><b>{e(x.partition('|')[0].strip().upper())}</b>: {e(x.partition('|')[2].strip() or 'not a candidate')}</li>"
            for x in skipped) + "</ul>")
    if notes:
        p.append("<h2>Notes</h2><ul>" + "".join(f"<li>{e(n)}</li>" for n in notes) + "</ul>")
    links, seen = [], set()
    for x in plans:                                       # every market-wide source the plans were built on
        for it in (x.get("sources") or {}).get("market_items") or []:
            u = it.get("url") or ""
            if u in seen or not u.startswith("https://"):
                continue
            seen.add(u)
            when = _rs.when(it.get("published_at") or it.get("observed_at") or "")
            links.append(f'<li><a href="{e(u)}" rel="noopener noreferrer">{e(it.get("source_name"))}: '
                         f'{e(it.get("what") or it.get("category"))}</a> <span class="sub">{e(when)}</span></li>')
    for s in sources:
        t, _, u = s.partition("|")
        if u in seen:
            continue
        seen.add(u)
        if u.startswith("https://") or u.startswith("http://"):
            links.append(f'<li><a href="{e(u)}" rel="noopener noreferrer">{e(t or u)}</a></li>')
    if links:
        p.append(f'<details><summary>Where the numbers came from ({len(links)})</summary><ul class="src">'
                 + "".join(links) + "</ul></details>")
    p.append(f'<div class="foot">{SAFETY_FOOTER}</div>')
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title><style>{CSS}</style></head><body><main>'
            + "".join(p) + f"</main><script>{MORE_JS}</script></body></html>\n")


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
    ap.add_argument("--skipped", action="append", default=[], help='v4.9: "TICKER|why it was dropped"')
    ap.add_argument("--tz", default="", help="v5.1: the user's time zone, e.g. Asia/Amman or +03:00")
    ap.add_argument("--journal", help="v5.1: journal.py report JSON; shows whether the plans have made money")
    ap.add_argument("--money-plan", help="v5.2: money_plan.py JSON; shows when to invest and in what kind of thing")
    ap.add_argument("--analysis", help="v5.2: ANALYSIS.json, the analyst's market read (mood, sourced facts, both sides, scenarios)")
    ap.add_argument("--prescreen", help="v5.3: PRESCREEN.json from prescreen.py; lists names checked ahead of time")
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    def load(f):
        with open(f) as fh:
            return json.load(fh)
    page = render([load(f) for f in a.plans], load(a.state) if a.state else None,
                  load(a.projected) if a.projected else None, a.market, a.metals, a.events,
                  a.note, a.source, a.title, a.skipped, a.tz, load(a.journal) if a.journal else None,
                  load(a.money_plan) if a.money_plan else None, load(a.analysis) if a.analysis else None,
                  load(a.prescreen) if a.prescreen else None)
    if a.out:
        with open(a.out, "w") as fh:
            fh.write(page)
    else:
        sys.stdout.write(page)


if __name__ == "__main__":
    main()
