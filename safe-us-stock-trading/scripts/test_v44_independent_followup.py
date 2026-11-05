"""Independent v4.4 follow-up regression tests (supplied by the external auditor, 2026-11-05).

The first part of the supplied file did not arrive. Everything up to and including the first line of
test_tbill_limit_far_above_market_must_not_trade (the imports, the trade() helper, the sector-cap test
and the start of the T-bill test) was RECONSTRUCTED from the audit report's reproduction steps (H1, H2).
Everything from that test's assertNotEqual line onward is the auditor's text, unchanged.

trade() uses the real clock (as_of = today UTC, quote 2 minutes old), so these tests need no clock pin.
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import fees  # noqa: E402
import portfolio_state as ps  # noqa: E402
import size_trade as st  # noqa: E402

FEE = fees.broker_profile('bank-al-etihad-jo')[1]


def trade(**kwargs):
    now = dt.datetime.now(dt.timezone.utc)
    base = dict(asset='stock', ticker='ABC', profile='balanced', horizon='short',
                portfolio=10000, cash=10000, entry=100, stop=94, t1=112, t2=119, market_price=100,
                sector_weights='{"Tech":1}', quote_status='live',
                as_of=now.date().isoformat(), quote_time=(now - dt.timedelta(minutes=2)).isoformat(),
                quote_source='Test source', broker='bank-al-etihad-jo',
                boycott_mode='off', shariah_mode='off')
    base.update(kwargs)
    argv = []
    for key, value in base.items():
        if value is None:
            continue
        argv += ['--' + key.replace('_', '-'), str(value)]
    return st.compute(st.build_parser().parse_args(argv))


class V44IndependentFollowup(unittest.TestCase):
    def test_unclassified_existing_holding_cannot_bypass_sector_cap(self):
        # H1: $10,000 portfolio, 27 x $100 OLD with a valid stop but no sector_weights; new $1,000 Tech buy.
        state = dict(cash=7300, holdings=[dict(ticker='OLD', asset='stock', shares=27, price=100, avg_cost=100,
                                               level=94, level_type='hard')], orders=[])
        got = ps.build(state, fee=FEE)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'actual.json')
            with open(p, 'w') as f:
                json.dump(got, f)
            result = trade(state=p, portfolio=None, cash=None)
        if result['verdict'] == 'TRADE':
            self.assertLessEqual(2700 + result['total_order_value'], 3000,
                                 'unclassified $2,700 holding could be Tech: combined Tech would exceed the 30% cap')

    def test_tbill_limit_far_above_market_must_not_trade(self):
        result = trade(asset='tbill', entry=None, stop=None, t1=None, t2=None, sector_weights=None,
                       amount=2000, price=150, market_price=50, yield_pct=5, expense_ratio_pct=0.1,
                       duration_yrs=0.15, hold_months=6)
        self.assertNotEqual(result['verdict'], 'TRADE', 'A $150 buy limit on a $50 T-bill fund is not an approved near-market entry')
    def test_unplaceable_fractional_cent_limit_must_not_be_order_ready(self):
        result = trade(entry=100.004, stop=94.01, t1=112.001, t2=119.002)
        self.assertNotEqual(result['verdict'], 'TRADE', 'Engine promises a cent-price grid but produces fractional-cent limit prices')
    def test_overfilled_working_buy_order_requires_reconciliation(self):
        order = dict(id='bad', ticker='AAA', asset='stock', side='buy', limit=100, shares=10,
                     filled_shares=15, status='partial', level=90, level_type='hard',
                     sector_weights={'Tech': 1})
        state = dict(cash=10000, holdings=[], orders=[order])
        try:
            result = ps.build(state, fee=FEE)
        except ValueError:
            return
        self.assertTrue(result.get('reconciliation_required'), 'Overfilled order was silently dropped rather than reconciled')
    def test_unknown_working_order_status_requires_reconciliation(self):
        order = dict(id='bad-status', ticker='AAA', asset='stock', side='buy', limit=100, shares=10,
                     filled_shares=0, status='unspecified', level=90, level_type='hard',
                     sector_weights={'Tech': 1})
        state = dict(cash=10000, holdings=[], orders=[order])
        try:
            result = ps.build(state, fee=FEE)
        except ValueError:
            return
        self.assertTrue(result.get('reconciliation_required'), 'Unknown order status accepted as an ordinary open order')
    def test_tbill_confirmation_must_not_instruct_a_nonexistent_stop(self):
        result = trade(asset='tbill', entry=None, stop=None, t1=None, t2=None, sector_weights=None,
                       amount=2000, price=150, market_price=150, yield_pct=5, expense_ratio_pct=0.1,
                       duration_yrs=0.15, hold_months=6, confirm_order='ABC|limit|150|13')
        self.assertEqual(result['verdict'], 'TRADE')
        self.assertNotIn('set a price alert at the stop', result['placement_status'],
                         'Treasury ETF path has no stop; confirmation text must not invent one')
if __name__ == '__main__':
    unittest.main()
