#!/usr/bin/env python3
"""Long-only signals for the safe-us-stock-trading skill (v4.8), computed from real daily prices.

Formulas follow Kakushadze & Serur, "151 Trading Strategies" (2018, SSRN 3247865). Only the
long-only parts are used; shorting, options, leverage and pairs/stat-arb are out of scope here.

  section 3.1   price momentum: 12-month return skipping the latest month (12-1), plus the
                risk-adjusted version (mean monthly return / monthly volatility)
  section 3.2   earnings momentum: SUE = (EPS now - EPS 4 quarters ago) / stdev of that change
                over the last 8 quarters (needs 12 quarters of diluted EPS, newest first, from SEC)
  section 3.4   low volatility: historical volatility over 126 trading days
  section 3.6   multifactor: demeaned rank average across factors (rank subcommand)
  section 3.13  three moving averages 3/10/21: MA3 > MA10 > MA21 confirms an up-trend
  section 3.14  pivot point support/resistance from the previous day's high, low, close
  section 3.15  Donchian channel (20-day high/low)
  section 4.1.1 trend filter: buy only if price > 200-day moving average
  section 4.1.2 dual momentum: broad market above its 200-day MA and 12-month return > 0, else
                defensive (gold or cash; not Treasuries when the Shariah screen excludes interest)
  plus ATR(14) and 20-day swing low/high for the skill's own level rules (section 5 of SKILL.md).

The paper itself warns that single-stock technical rules have weak theoretical grounding and that
momentum effects fade with longer holding periods. These are evidence inputs, never a buy order:
every plan still goes through the screens, the source check and size_trade.py.

Prices (--prices FILE): CSV with a header date,close[,high,low] (oldest first), or JSON
[{"date": "YYYY-MM-DD", "close": 1.0, "high": 1.0, "low": 1.0}, ...]. Use split- and
dividend-adjusted closes, and record the file's source in the source ledger (price_history).

  python3 signals.py one --ticker ABC --prices ABC.csv [--market SPUS.csv] [--eps "1.2,1.1,..."]
  python3 signals.py rank --signals SIG_ABC.json SIG_XYZ.json
"""
import argparse, csv, datetime as dt, json, math, statistics, sys

DAYS_MONTH, DAYS_YEAR = 21, 252


def validate_rows(rows):
    """Rows -> clean list of {date, close, high, low}. Raises ValueError on anything malformed."""
    if not isinstance(rows, list) or not rows:
        raise ValueError("no price rows")
    out = []
    for r in rows:
        if not isinstance(r, dict):
            raise ValueError("each price row must be an object / CSV line")
        r = {str(k).strip().lower(): v for k, v in r.items() if k is not None}
        if "date" not in r or "close" not in r:
            raise ValueError("price rows need 'date' and 'close' columns")
        try:
            dt.date.fromisoformat(str(r["date"]))
            c = float(r["close"])
            h = float(r["high"]) if r.get("high") not in (None, "") else None
            lo = float(r["low"]) if r.get("low") not in (None, "") else None
        except (TypeError, ValueError):
            raise ValueError(f"bad price row on {r.get('date')}")
        if not math.isfinite(c) or c <= 0 or any(x is not None and (not math.isfinite(x) or x <= 0) for x in (h, lo)):
            raise ValueError(f"bad price on {r.get('date')}")
        out.append(dict(date=str(r["date"]), close=c, high=h, low=lo))
    dates = [x["date"] for x in out]
    if dates != sorted(dates) or len(set(dates)) != len(dates):
        raise ValueError("prices must be oldest first with one row per date")
    return out


def load_prices(path):
    with open(path) as f:
        text = f.read()
    rows = json.loads(text) if text.lstrip().startswith("[") else list(csv.DictReader(text.splitlines()))
    return validate_rows(rows)


def sma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def momentum_12_1(closes):
    """Section 3.1: cumulative return over months t-12..t-1 (skip the latest month)."""
    need = DAYS_YEAR + 1
    if len(closes) < need:
        return None, None
    end, start = closes[-1 - DAYS_MONTH], closes[-1 - DAYS_YEAR]
    cum = end / start - 1
    monthly = [closes[-1 - DAYS_MONTH * k] / closes[-1 - DAYS_MONTH * (k + 1)] - 1 for k in range(1, 12)]
    sd = statistics.stdev(monthly)
    risk_adj = (statistics.mean(monthly) / sd) if sd > 0 else None
    return cum, risk_adj


def hist_vol(closes, n=126):
    """Section 3.4: annualized volatility of daily returns over n trading days."""
    if len(closes) < n + 1:
        return None
    r = [closes[i] / closes[i - 1] - 1 for i in range(len(closes) - n, len(closes))]
    return statistics.stdev(r) * math.sqrt(DAYS_YEAR)


def atr(rows, n=14):
    if len(rows) < n + 1 or any(r["high"] is None or r["low"] is None for r in rows[-n - 1:]):
        return None
    tr = []
    for i in range(len(rows) - n, len(rows)):
        h, lo, pc = rows[i]["high"], rows[i]["low"], rows[i - 1]["close"]
        tr.append(max(h - lo, abs(h - pc), abs(lo - pc)))
    return sum(tr) / n


def pivot(rows):
    """Section 3.14: C = (H + L + C) / 3, R = 2C - L, S = 2C - H from the previous session."""
    p = rows[-1]
    if p["high"] is None or p["low"] is None:
        return None
    c = (p["high"] + p["low"] + p["close"]) / 3
    return dict(center=round(c, 2), resistance=round(2 * c - p["low"], 2), support=round(2 * c - p["high"], 2),
                from_session=p["date"])


def sue(eps):
    """Section 3.2: SUE = (E0 - E4) / stdev(E_k - E_{k+4}, k = 0..7). eps newest first, >= 12 quarters."""
    if not eps or len(eps) < 12 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in eps):
        return None
    ue = [eps[k] - eps[k + 4] for k in range(8)]
    sd = statistics.stdev(ue)
    return (ue[0] / sd) if sd > 0 else None


def market_regime(rows):
    """Section 4.1.2 absolute momentum of a broad-market fund."""
    closes = [r["close"] for r in rows]
    m200 = sma(closes, 200)
    ret12 = closes[-1] / closes[-1 - DAYS_YEAR] - 1 if len(closes) > DAYS_YEAR else None
    if m200 is None or ret12 is None:
        return dict(state="UNKNOWN", note="needs 253 sessions of the market fund")
    up = closes[-1] > m200 and ret12 > 0
    return dict(state="UP" if up else "DOWN", price=closes[-1], sma200=round(m200, 2), return_12m=round(ret12, 4),
                note=("broad market trending up: equity ideas allowed" if up else
                      "broad market trending down: favour defensive (gold, cash); no new short-term equity entries"))


def one(ticker, rows, market_rows=None, eps=None):
    closes = [r["close"] for r in rows]
    px = closes[-1]
    m3, m10, m21, m50, m200 = (sma(closes, n) for n in (3, 10, 21, 50, 200))
    mom, mom_ra = momentum_12_1(closes)
    vol = hist_vol(closes)
    a14 = atr(rows)
    last20 = rows[-20:]
    lows = [r["low"] if r["low"] is not None else r["close"] for r in last20]
    highs = [r["high"] if r["high"] is not None else r["close"] for r in last20]
    don_hi, don_lo = (max(highs), min(lows)) if len(rows) >= 20 else (None, None)
    trend_ok = (px > m200) if m200 else None
    three_ma = (m3 > m10 > m21) if m21 else None
    s = sue(eps)
    flags, missing = [], []
    for name, v in (("200-day MA", m200), ("12-1 momentum", mom), ("126-day volatility", vol), ("ATR(14)", a14)):
        if v is None:
            missing.append(name)
    if trend_ok is False and mom is not None and mom < 0:
        hint = "AVOID"
        flags.append("downtrend: price is below its 200-day average and the 12-1 month return is negative")
    elif trend_ok is False:
        hint = "CAUTION"
        flags.append("price is below its 200-day average (trend filter, 151 TS 4.1.1)")
    elif trend_ok is None:
        hint = "UNKNOWN"
        flags.append("not enough history for the trend filter")
    else:
        hint = "OK"
    if three_ma is False:
        flags.append("short averages not aligned (MA3 > MA10 > MA21 fails): no short-term breakout entry")
    if s is not None and s < 0:
        flags.append("earnings momentum negative (SUE < 0)")
    regime = market_regime(market_rows) if market_rows else None
    if regime and regime["state"] == "DOWN" and hint in ("OK", "UNKNOWN"):
        hint = "CAUTION"
        flags.append("broad market filter is DOWN (dual momentum, 151 TS 4.1.2)")
    r2 = lambda x: None if x is None else round(x, 2)
    r4 = lambda x: None if x is None else round(x, 4)
    return dict(schema="signals/1", ticker=ticker.upper(), history_through=rows[-1]["date"], sessions=len(rows),
                price=px, sma=dict(ma3=r2(m3), ma10=r2(m10), ma21=r2(m21), ma50=r2(m50), ma200=r2(m200)),
                trend_filter_pass=trend_ok, three_ma_aligned=three_ma,
                momentum_12_1=r4(mom), momentum_12_1_risk_adj=r4(mom_ra), volatility_126d=r4(vol),
                atr14=r2(a14), atr_pct=None if a14 is None else round(100 * a14 / px, 2),
                swing_low_20d=r2(don_lo), swing_high_20d=r2(don_hi),
                donchian_20=dict(ceiling=r2(don_hi), floor=r2(don_lo)), pivot=pivot(rows), sue=r4(s),
                market_regime=regime, hint=hint, flags=flags, missing=missing,
                label="Calculated", reference="Kakushadze & Serur, 151 Trading Strategies (2018), SSRN 3247865",
                inputs=dict(rows=rows, market_rows=market_rows, eps=eps),
                integrity="size_trade.py recomputes every signal from these recorded prices; an edited result is refused")


def rank(sigs):
    """Section 3.6: demeaned rank average. Higher momentum, lower volatility, higher SUE rank better."""
    factors = [("momentum_12_1", 1), ("volatility_126d", -1), ("sue", 1)]
    n = len(sigs)
    scores = {s["ticker"]: [] for s in sigs}
    used = []
    for key, sign in factors:
        vals = [(s["ticker"], s.get(key)) for s in sigs]
        if any(v is None for _, v in vals) or n < 2:
            continue
        used.append(key)
        order = sorted(vals, key=lambda x: sign * x[1])
        ranks = {t: i + 1 for i, (t, _) in enumerate(order)}
        mean = (n + 1) / 2
        for t in ranks:
            scores[t].append(ranks[t] - mean)
    rows = [dict(ticker=s["ticker"], hint=s.get("hint"),
                 score=round(sum(scores[s["ticker"]]) / len(used), 3) if used else None) for s in sigs]
    rows.sort(key=lambda r: (r["hint"] == "AVOID", -(r["score"] if r["score"] is not None else -1e9)))
    return dict(schema="signal-rank/1", factors_used=used,
                note="factors with any missing value are left out for every ticker; AVOID names sort last",
                ranking=rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("one")
    o.add_argument("--ticker", required=True)
    o.add_argument("--prices", required=True)
    o.add_argument("--market", default="", help="broad-market fund prices for the dual-momentum filter")
    o.add_argument("--eps", default="", help="12+ quarters of diluted EPS from SEC filings, newest first")
    o.add_argument("--out", default="")
    r = sub.add_parser("rank")
    r.add_argument("--signals", nargs="+", required=True)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "one":
            eps = [float(x) for x in a.eps.split(",") if x.strip()] if a.eps else None
            out = one(a.ticker, load_prices(a.prices), load_prices(a.market) if a.market else None, eps)
            if a.out:
                with open(a.out, "w") as f:
                    json.dump(out, f, indent=2)
        else:
            sigs = []
            for p in a.signals:
                with open(p) as f:
                    sg = json.load(f)
                if not isinstance(sg, dict) or sg.get("schema") != "signals/1" or not sg.get("ticker"):
                    raise ValueError(f"{p} is not a signals.py result")
                sigs.append(sg)
            out = rank(sigs)
    except (OSError, ValueError, KeyError, TypeError) as e:
        print(json.dumps(dict(error=f"signals: {e}"), indent=2))
        return 1
    # recorded inputs stay in the file; keep the screen output short
    print(json.dumps({k: v for k, v in out.items() if k != "inputs"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
