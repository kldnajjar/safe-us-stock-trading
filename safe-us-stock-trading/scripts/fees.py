#!/usr/bin/env python3
"""Broker cost models for the safe-us-stock-trading skill (v4.3).

fee(value, shares=None, side="buy") -> estimated cost of ONE order in the account currency.

UNITS: every rate is a FRACTION. 0.005 means 0.5%. A rate of 0.1 (10%) or more is
rejected as a likely percent-vs-fraction mistake.

A spec may contain:
  model         percent | per_share | flat | zero   (commission on buys, and sells unless "sell" is given)
  sell          optional separate commission spec for sell orders (same fields)
  fx_pct        optional currency-conversion cost, as a fraction of order value. Charged ONLY when
                the order actually converts currency (make_fee_model(spec, convert=True)); a USD
                account buying a USD stock pays no FX.
Bid/ask spread and slippage are NOT here: the engine applies them separately
(--friction-bps), so a zero-commission broker still has trading friction.
"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))
BROKERS = os.path.join(HERE, "brokers.json")
REQUIRED = {"percent": ("rate", "min", "max"), "per_share": ("per_share", "min", "max_pct"),
            "flat": ("flat",), "zero": ()}
FRACTION_FIELDS = ("rate", "max_pct", "fx_pct")


def _check_fraction(name, x):
    if x is None:
        return
    if x < 0:
        raise ValueError(f"fee field '{name}' cannot be negative")
    if x >= 0.1:
        raise ValueError(f"fee field '{name}'={x} looks like a percent; use a fraction (0.005 = 0.5%)")


def _commission(spec):
    model = spec.get("model")
    if model not in REQUIRED:
        raise ValueError(f"unknown fee model '{model}'")
    missing = [k for k in REQUIRED[model] if spec.get(k) is None]
    if missing:
        raise ValueError(f"fee model '{model}' is missing {', '.join(missing)}")
    for k in REQUIRED[model]:
        if spec[k] < 0:
            raise ValueError(f"fee field '{k}' cannot be negative")
        if k in FRACTION_FIELDS:
            _check_fraction(k, spec[k])

    def c(value, shares):
        if model == "percent":
            return min(max(spec["rate"] * value, spec["min"]), spec["max"])
        if model == "per_share":
            if shares is None:
                raise ValueError("per-share fee needs the share count")
            return min(max(spec["per_share"] * shares, spec["min"]), spec["max_pct"] * value)
        if model == "flat":
            return float(spec["flat"])
        return 0.0
    return c


def make_fee_model(spec, convert=False):
    """Validate a cost spec and return fee(value, shares=None, side='buy').
    convert: True only when the order converts between the account and instrument currencies."""
    buy = _commission(spec)
    sell = _commission(spec["sell"]) if spec.get("sell") else buy
    fx_rate = spec.get("fx_pct") or 0.0
    _check_fraction("fx_pct", fx_rate)
    fx = fx_rate if convert else 0.0

    def fee(value, shares=None, side="buy"):
        if value <= 0:
            return 0.0
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return (sell if side == "sell" else buy)(value, shares) + fx * value
    fee.describe = dict(buy=spec.get("model"), sell=(spec.get("sell") or {}).get("model", spec.get("model")),
                        fx_pct=fx_rate, fx_charged=bool(convert and fx_rate), note="spread/slippage applied separately")
    return fee


def make_fee(rate, fmin, fmax):
    """Percent model shortcut (kept for callers and tests)."""
    return make_fee_model(dict(model="percent", rate=rate, min=fmin, max=fmax))


def load_brokers(path=BROKERS):
    with open(path) as f:
        reg = json.load(f)
    validate_brokers(reg)
    return reg


def validate_brokers(reg):
    if "brokers" not in reg or not isinstance(reg["brokers"], dict):
        raise ValueError("brokers.json: 'brokers' object missing")
    for bid, b in reg["brokers"].items():
        for k in ("name", "fee", "currency", "source"):
            if k not in b:
                raise ValueError(f"broker '{bid}' missing '{k}'")
        if b.get("template"):
            continue
        make_fee_model(b["fee"])
        if b.get("min_order") is None:
            raise ValueError(f"broker '{bid}' needs min_order (use 0 if none)")


def broker_profile(broker_id, path=BROKERS, convert=False):
    reg = load_brokers(path)
    b = reg["brokers"].get(broker_id)
    if b is None:
        raise ValueError(f"unknown broker '{broker_id}'")
    if b.get("template"):
        raise ValueError(f"'{broker_id}' is a template; copy it and fill in the user's fee schedule")
    return b, make_fee_model(b["fee"], convert=convert)
