from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from futures_historical_sessions import (historical_configs, historical_plan,
    ready_for_analysis, process_root, scan_selected_contract, ROOTS)
from futures_roll import parse_provider_calendar, contract_file
from session_rules import assign_primary_session


class HistoricalSessionTests(unittest.TestCase):
    def setUp(self):
        # Self-contained fixtures: no licensed archive or generated outputs needed.
        mapping=pd.DataFrame([dict(provider_root=root, mapping_resolved=True,
            exchange_symbol={'AD':'6C','B6':'6B','J1':'6J','E6':'6E'}.get(root,root),
            product_family=('METALS' if root in ('HG','GC') else 'EQUITY_INDEX'
                if root in ('ES','NQ') else 'US_TREASURIES' if root=='ZF' else 'CME_CURRENCY'))
            for root in ROOTS])
        self.configs, self.rules, self.unresolved = historical_configs(mapping)

    def test_exact_frozen_roots_no_universe_expansion(self):
        self.assertEqual(set(self.configs), set(ROOTS))

    def test_2015_date_effective_close(self):
        data = pd.DataFrame(dict(timestamp=pd.to_datetime([
            '2015-09-18 17:05', '2015-09-21 17:05']), volume=[1,1]))
        for root in ('HG','GC','ES','NQ'):
            assigned=assign_primary_session(data,'futures',futures_root=root,futures_sessions=self.configs)
            self.assertEqual(assigned.primary_session_retained.tolist(),[True,False])

    def test_2021_pause_removed_on_effective_trade_date(self):
        data=pd.DataFrame(dict(timestamp=pd.to_datetime([
            '2021-06-25 16:15','2021-06-28 16:15','2021-06-28 16:30']),volume=[1,1,1]))
        for root in ('ES','NQ'):
            assigned=assign_primary_session(data,'futures',futures_root=root,futures_sessions=self.configs)
            self.assertEqual(assigned.primary_session_retained.tolist(),[False,True,True])

    def test_no_backcast_and_unresolved_periods_explicit(self):
        data=pd.DataFrame(dict(timestamp=pd.to_datetime([
            '2023-01-03 09:00','2024-01-03 09:00','2025-01-03 09:00']),volume=[1,1,1]))
        for root in ('AD','B6','J1','E6','ZF'):
            assigned=assign_primary_session(data,'futures',futures_root=root,futures_sessions=self.configs)
            self.assertEqual(assigned.primary_session_retained.tolist(),[False,True,False])
        self.assertEqual(len(self.unresolved),10)
        self.assertFalse(self.unresolved.primary_inclusion.any())

    def fixture(self, folder, root='AD'):
        mapping=folder/'calendar.txt'
        mapping.write_text('2023-01-03,H23\n2024-01-02,H24\n2024-01-03,M24\n')
        # H23 is physically available but its session is unresolved.
        (folder/f'{root}_H23_1min.txt').write_text('2023-01-02 18:00:00,1,2,1,2,3\n')
        (folder/f'{root}_H24_1min.txt').write_text(
            '2024-01-01 18:00:00,1,2,1,2,0\n2024-01-02 16:59:00,2,3,2,3,4\n'
            '2024-01-02 17:30:00,2,3,2,3,2\n2024-01-02 18:00:00,3,4,3,4,5\n')
        (folder/f'{root}_continuous_adjusted_1min.txt').write_text('MUST NEVER BE READ')
        out=folder/'derived';out.mkdir();(out/'read_audits').mkdir()
        return parse_provider_calendar(mapping),out

    def test_pipeline_unresolved_missing_no_substitution_or_filling(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);calendar,out=self.fixture(folder)
            before={p.name:p.read_bytes() for p in folder.glob('*.txt')}
            record,contracts,missing,transitions,scans=process_root('AD',folder,calendar,self.configs,out)
            daily=pd.read_csv(out/'AD_historical_daily_ohlcv.csv')
            self.assertEqual(daily.date.tolist(),['2024-01-02'])
            self.assertEqual(daily.bars_observed.tolist(),[2])
            self.assertEqual(daily.zero_volume_rows.tolist(),[1])
            self.assertEqual(daily.volume.tolist(),[4.])
            self.assertEqual(daily.selected_contract.tolist(),['H24'])
            self.assertEqual(missing[0]['selected_contract'],'M24')
            self.assertEqual(missing[0]['other_required_contract_potential_rows'],1)
            self.assertFalse(missing[0]['substituted'])
            self.assertTrue(record['final_analysis_ready'])
            self.assertEqual(before,{p.name:p.read_bytes() for p in folder.glob('*.txt')})
            self.assertEqual(set(s['file_name'] for s in scans),{'AD_H23_1min.txt','AD_H24_1min.txt'})

    def test_unknown_date_is_audit_only_not_synthetic_observation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);calendar,out=self.fixture(folder)
            plan=historical_plan(calendar,'AD',folder,self.configs)
            row=plan.loc[plan.trade_date.eq(pd.Timestamp('2023-01-03').date())].iloc[0]
            self.assertEqual(row.session_status,'UNRESOLVED')
            self.assertTrue(pd.isna(row.session_start))
            self.assertEqual(row.selected_contract,'H23')

    def test_unbalanced_readiness_ignores_missing_audit_dates(self):
        day=pd.Timestamp('2024-01-02').date()
        daily=pd.DataFrame([dict(date=day,selected_contract='H24',bars_observed=1)])
        sessions=pd.DataFrame([
            dict(trade_date=day,session_status='VERIFIED',selected_contract='H24',bars_observed=1,
                contract_file_exists=True,validation_status='ok'),
            dict(trade_date=pd.Timestamp('2025-12-31').date(),session_status='UNRESOLVED',
                selected_contract='H26',bars_observed=0,contract_file_exists=False,validation_status='excluded_audit_only')])
        self.assertTrue(ready_for_analysis(daily,sessions)[0])
        self.assertFalse(ready_for_analysis(daily,sessions,transition_failures=1)[0])
        sessions.loc[0,'session_status']='UNRESOLVED'
        self.assertFalse(ready_for_analysis(daily,sessions)[0])

    def test_contract_provenance_and_overlap_block_readiness(self):
        day=pd.Timestamp('2024-01-02').date()
        daily=pd.DataFrame([dict(date=day,selected_contract='H24',bars_observed=1)])
        sessions=pd.DataFrame([dict(trade_date=day,session_status='VERIFIED',selected_contract='M24',
            bars_observed=1,contract_file_exists=True,validation_status='ok')])
        self.assertFalse(ready_for_analysis(daily,sessions)[0])
        self.assertFalse(ready_for_analysis(pd.concat([daily,daily]),sessions)[0])
        with self.assertRaises(ValueError):
            contract_file(Path('.'),'AD','continuous_adjusted',allowed_roots=self.configs)
        with self.assertRaises(ValueError):
            scan_selected_contract(Path('AD_continuous_adjusted_1min.txt'),'AD','H24',
                pd.DataFrame(),set(),self.configs,Path('.'))

    def test_import_does_not_load_benchmark_or_execute_ranking(self):
        result=subprocess.run([sys.executable,'-B','-c',
            "import sys;sys.path.insert(0,'src');import futures_historical_sessions;assert 'benchmark' not in sys.modules"],
            capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
