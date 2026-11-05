#!/usr/bin/env python3
"""Independent audit regression tests (supplied by the external auditor, 2026-11-05).

The first lines of the supplied file were cut off in transfer; the imports and the
trade() defaults below were reconstructed from what the tests use. Everything from
`base.update(kw)` onward is the auditor's text, unchanged.

v4.3 additions to the reconstructed part only: the engine clock is pinned to 2026-11-05T20:35Z for
this module (the fixtures are fixed-date), trade() passes --market-price 100 from the same quote,
and shariah() passes --market-cap-date, both now required.
"""
import json, os, sys, tempfile, unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fees  # noqa: E402
import portfolio_state as ps  # noqa: E402
import shariah_screen as sh  # noqa: E402
import size_trade as st  # noqa: E402


# v4.3: freshness is checked against the system clock. These fixtures are dated 2026-11-05 15:30 ET,
# so the engine's clock is pinned 5 minutes after that quote for this module only.
_TEST_CLOCK = __import__("datetime").datetime(2026, 11, 5, 20, 35, tzinfo=__import__("datetime").timezone.utc)
_REAL_CLOCK = None


def setUpModule():
    global _REAL_CLOCK
    import size_trade
    _REAL_CLOCK = size_trade.CLOCK
    size_trade.CLOCK = lambda: _TEST_CLOCK


def tearDownModule():
    import size_trade
    size_trade.CLOCK = _REAL_CLOCK


def trade(**kw):
    base = dict(asset='stock', ticker='ABC', profile='balanced', horizon='short',
                portfolio=10000, cash=10000, entry=100, stop=94, t1=112, t2=119,
                sector_weights=json.dumps({'Tech': 1.0}),
                quote_status='live', quote_time='2026-11-05T15:30:00-05:00', quote_source='Yahoo Finance',
                as_of='2026-11-05', broker='bank-al-etihad-jo',
                boycott_mode='off', shariah_mode='off', market_price=100)
    base.update(kw)
    argv = []
    for name, value in base.items():
        if value is None:
            continue
        argv.append('--' + name.replace('_', '-'))
        if value is not True:
            argv.append(str(value))
    return st.compute(st.build_parser().parse_args(argv))


def shariah(**kw):
    base = dict(asset='stock', ticker='ABC', isin='US0000000001', entity='ABC Corp',
                business='permissible', as_of='2026-11-05', period='FY2025',
                data_published='2026-02-20', market_cap=1000, total_assets=1000,
                avg_market_cap_24m=1000, avg_market_cap_36m=1000,
                interest_debt=100, total_debt=100, cash=40, interest_deposits=10,
                interest_securities=10, receivables=60,
                nonpermissible_income=1, total_income=500, market_cap_date='2026-11-04')
    base.update(kw)
    argv = []
    for name, value in base.items():
        if value is None:
            continue
        argv.extend(['--' + name.replace('_', '-'), str(value)])
    return sh.screen(sh.build_parser().parse_args(argv))


class MissingSafeguards(unittest.TestCase):
    def test_future_quote_must_not_be_executable(self):
        self.assertEqual(trade(quote_time='2099-01-01T12:00:00-05:00')['verdict'], 'WATCHLIST')

    def test_very_old_quote_must_not_be_executable(self):
        self.assertEqual(trade(quote_time='2020-01-01T12:00:00-05:00')['verdict'], 'WATCHLIST')

    def test_market_confirmation_cannot_validate_a_limit_order(self):
        result = trade(confirm_order='ABC|market|100|10')
        self.assertNotIn('ready to place', result['placement_status'])

    def test_negative_tbill_price_must_not_create_a_trade(self):
        result = trade(asset='tbill', entry=None, stop=None, t1=None, t2=None,
                       sector_weights=None, amount=2000, price=-50,
                       yield_pct=4, expense_ratio_pct=0.1,
                       duration_yrs=0.15, hold_months=6)
        self.assertNotEqual(result['verdict'], 'TRADE')
        self.assertGreaterEqual(result.get('shares', 0), 0)

    def test_tbill_delayed_over_20_minutes_is_watchlist(self):
        result = trade(asset='tbill', entry=None, stop=None, t1=None, t2=None,
                       sector_weights=None, amount=2000, price=50,
                       yield_pct=4, expense_ratio_pct=0.1,
                       duration_yrs=0.15, hold_months=6,
                       quote_status='delayed', quote_delay_min=60)
        self.assertEqual(result['verdict'], 'WATCHLIST')

    def test_optional_raise_stop_is_true_net_break_even(self):
        result = trade()
        remaining = result['partial_exit_plan']['hold_for_t2']
        rounded_stop = result['partial_exit_plan']['stop_after_t1']['optional_raise_to']
        self.assertIsNotNone(rounded_stop)
        account_fee = fees.make_fee(0.005, 0.5, 30)
        cost_basis = result['total_order_value'] + result['total_buy_fees'] + result['total_order_value'] * 0.0005
        allocated_basis = cost_basis * remaining / result['shares']
        net_proceeds = remaining * rounded_stop - account_fee(remaining * rounded_stop, remaining, side='sell') - remaining * rounded_stop * 0.0005
        self.assertGreaterEqual(net_proceeds - allocated_basis, -0.001)

    def test_negative_sector_weight_is_rejected(self):
        self.assertNotEqual(trade(sector_weights=json.dumps({'Tech': -2.0}))['verdict'], 'TRADE')

    def test_sector_weights_must_represent_the_whole_instrument(self):
        self.assertNotEqual(trade(sector_weights=json.dumps({'Tech': 0.01}))['verdict'], 'TRADE')

    def test_zero_unquantified_loss_pct_is_not_conservative(self):
        result = trade(unquantified_holdings=1, unquantified_value=10000, unquantified_loss_pct=0)
        self.assertNotEqual(result['verdict'], 'TRADE')

    def test_negative_unquantified_loss_pct_is_rejected(self):
        result = trade(unquantified_holdings=1, unquantified_value=10000, unquantified_loss_pct=-100)
        self.assertNotEqual(result['verdict'], 'TRADE')

    def test_portfolio_projection_supports_a_tbill_plan(self):
        _, fee = fees.broker_profile('bank-al-etihad-jo')
        t_bill_plan = trade(asset='tbill', entry=None, stop=None, t1=None, t2=None,
                            sector_weights=None, amount=2000, price=50,
                            yield_pct=4, expense_ratio_pct=0.1,
                            duration_yrs=0.15, hold_months=6)
        self.assertEqual(t_bill_plan['verdict'], 'TRADE')
        state = dict(cash=10000, cash_includes_open_orders=False, holdings=[], orders=[])
        projected = ps.build(state, [t_bill_plan], fee)
        self.assertGreater(projected['size_trade_args']['committed'], 0)

    def test_nonstock_shariah_result_cannot_authorize_stock(self):
        args = sh.build_parser().parse_args([
            '--asset', 'etf-certified', '--ticker', 'ABC',
            '--certifier', 'Test certifier (hypothetical)',
            '--certificate-date', '2026-11-05', '--as-of', '2026-11-05'])
        result = sh.screen(args)
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'screen.json'
            p.write_text(json.dumps(result))
            t = trade(shariah_mode='exclude', shariah_result=str(p))
            self.assertNotEqual(t['verdict'], 'TRADE')

    def test_short_balanced_stop_distance_must_not_exceed_six_percent(self):
        result = trade(stop=88, t1=140, t2=155)
        self.assertNotEqual(result['verdict'], 'TRADE',
                            'balanced short trade has a 12% stop distance but the limit is 6%')

    def test_existing_single_stock_exposure_is_included_in_position_cap(self):
        _, broker_fee = fees.broker_profile('bank-al-etihad-jo')
        state = dict(cash=9100, cash_includes_open_orders=False, orders=[],
                     holdings=[dict(ticker='ABC', asset='stock', shares=9,
                                    avg_cost=100, price=100, level=94,
                                    level_type='hard', sector_weights={'Tech': 1.0})])
        actual = ps.build(state, [], broker_fee)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'actual.json'
            path.write_text(json.dumps(actual))
            result = trade(state=str(path))
            if result['verdict'] == 'TRADE':
                self.assertLessEqual(900 + result['total_order_value'], 1000,
                                     'proposed purchase exceeds 10% combined single-stock cap')

    def test_negative_debt_is_not_permissible_financial_data(self):
        self.assertNotEqual(shariah(interest_debt=-100)['policy_decision'], 'PERMITTED')

    def test_future_filing_date_is_not_acceptable(self):
        self.assertNotEqual(shariah(data_published='2099-12-01')['policy_decision'], 'PERMITTED')


if __name__ == "__main__":
    unittest.main(verbosity=2)
