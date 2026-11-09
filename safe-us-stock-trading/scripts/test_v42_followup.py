"""Independent v4.2 follow-up tests. Expected to FAIL before the findings are fixed.
Place in us-portfolio-cfo/scripts/ and run `python3 run_checks.py`.
Tests are intentionally policy-focused: they reject stale/live quotes being described
as order-ready and expired or undated Shariah evidence being marked PERMITTED.
"""
import datetime as dt
import sys
import os
import unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import size_trade as _st_v48  # noqa: E402
# v4.8: these v4.x suites isolate one gate at a time, so the mandatory screen and source gates are
# switched off here (module switch, like CLOCK). test_v48_mandatory.py tests them switched on.
_st_v48.SCREENS_REQUIRED = _st_v48.SOURCES_REQUIRED = _st_v48.MARKET_CLOCK_REQUIRED = False
import shariah_screen as sh
import size_trade as st
def trade(**kwargs):
    base = dict(asset='stock', ticker='ABC', profile='balanced', horizon='short',
                portfolio=10000, cash=10000, entry=100, stop=94, t1=112, t2=119,
                sector_weights='{"Tech":1}', quote_status='live',
                as_of='2026-11-05', quote_time='2026-11-05T15:30:00-05:00',
                quote_source='Test source', broker='bank-al-etihad-jo',
                boycott_mode='off', shariah_mode='off')
    base.update(kwargs)
    argv=[]
    for key, value in base.items():
        if value is None: continue
        argv += ['--' + key.replace('_','-'), str(value)]
    return st.compute(st.build_parser().parse_args(argv))
def screen(args):
    return sh.screen(sh.build_parser().parse_args(args))
class NewFollowupRegressions(unittest.TestCase):
    def test_future_quote_within_asof_day_is_not_tradeable(self):
        now = dt.datetime.now(dt.timezone.utc)
        future = now + dt.timedelta(hours=2)
        r = trade(as_of=now.date().isoformat(), quote_time=future.isoformat())
        self.assertEqual(r['verdict'], 'WATCHLIST', r)
    def test_historical_asof_cannot_authorize_live_trade_today(self):
        r = trade(as_of='2020-01-01', quote_time='2020-01-01T15:30:00-05:00')
        self.assertEqual(r['verdict'], 'WATCHLIST', r)
    def test_three_day_old_live_quote_is_not_tradeable(self):
        # This quote is within the engine's default 96-hour age, but not live.
        now = dt.datetime.now(dt.timezone.utc)
        past = now - dt.timedelta(hours=72)
        r = trade(as_of=now.date().isoformat(), quote_time=past.isoformat())
        self.assertEqual(r['verdict'], 'WATCHLIST', r)
    def test_century_old_etf_certificate_not_permitted(self):
        r = screen(['--asset','etf-certified','--ticker','ABC','--isin','US0000000001',
                    '--entity','ABC Fund','--as-of','2026-11-05','--certifier','Example',
                    '--certificate-date','1900-01-01'])
        self.assertNotEqual(r['policy_decision'], 'PERMITTED', r)
    def test_future_etf_certificate_not_permitted(self):
        r = screen(['--asset','etf-certified','--ticker','ABC','--isin','US0000000001',
                    '--entity','ABC Fund','--as-of','2026-11-05','--certifier','Example',
                    '--certificate-date','2099-01-01'])
        self.assertNotEqual(r['policy_decision'], 'PERMITTED', r)
    def test_undated_market_cap_cannot_pass_aaoifi(self):
        args=['--asset','stock','--ticker','ABC','--isin','US0000000001','--entity','ABC Corp',
              '--business','permissible','--as-of','2026-11-05', '--period','FY2025',
              '--data-published','2026-02-20','--market-cap','1000','--total-assets','1000',
              '--interest-debt','100','--interest-deposits','10',
              '--nonpermissible-income','1','--total-income','500']
        r = screen(args)
        self.assertNotEqual(r['policy_decision'], 'PERMITTED', r)
if __name__ == '__main__':
    unittest.main()
