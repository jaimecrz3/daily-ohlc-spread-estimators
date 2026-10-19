"""Reconcile final presentation against immutable numeric result sources."""
import json
import subprocess
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
import final_artifacts as f


class FinalArtifactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables=f.build_tables()

    def test_table1_counts_and_fx_not_zero(self):
        t=self.tables['table1_estimator_definitions_and_coverage']
        numeric=t.loc[t.asset_class.ne('fx')]
        np.testing.assert_array_equal(numeric.defined_N+numeric.undefined_N,numeric.design_eligible_N)
        np.testing.assert_allclose(numeric.failure_rate,numeric.undefined_N/numeric.design_eligible_N)
        self.assertTrue(t.loc[t.asset_class.eq('fx'),'design_eligible_N'].isna().all())
        self.assertIn('BLOCKED',t.loc[t.asset_class.eq('fx'),'status'].iloc[0])

    def test_table2_exact_primary_and_hac_reconciliation(self):
        t=self.tables['table2_primary_horse_race']
        self.assertEqual(len(t),51)
        a=f.read(f.primary.RESULTS/'primary_accuracy_results.csv')
        a=a.loc[a.reporting_scope.isin(['overall','asset_class','asset_class_x_tier'])]
        pd.testing.assert_frame_equal(t[a.columns].reset_index(drop=True),a.reset_index(drop=True))
        h=f.read(f.primary.RESULTS/'primary_bias_hac_results.csv')
        check=t.merge(h,on=f.primary.CELL_KEYS+['estimator'],suffixes=('_final','_source'))
        for col in ['hac_se_bps','ci95_low_bps','ci95_high_bps','p_value_two_sided']:
            np.testing.assert_array_equal(check[col+'_final'],check[col+'_source'])

    def test_table3_failure_and_negative_denominators(self):
        t=self.tables['table3_failure_negative_decomposition']
        for panel,name in [('A','failure_rates.csv'),('B','raw_negative_rates.csv')]:
            s=f.read(f.primary.RESULTS/name)
            s=s.loc[s.reporting_scope.isin(['overall','asset_class'])].reset_index(drop=True)
            pd.testing.assert_frame_equal(t.loc[t.panel.eq(panel),s.columns].reset_index(drop=True),s,check_dtype=False)

    def test_table4_retains_sensitivity_sources_and_empty_cells(self):
        t=self.tables['table4_robustness_falsification']
        s=f.read(f.robustness.RESULTS/'robustness_conclusion_stability.csv')
        s=s.loc[s.variant.ne('Primary')&s.estimator.eq('EDGE')]
        pd.testing.assert_frame_equal(t.iloc[:len(s)][s.columns].reset_index(drop=True),s.reset_index(drop=True),check_dtype=False)
        self.assertTrue(((t.asset_class=='etfs')&(t.liquidity_tier=='LOW')&(t.N_asset_days==0)).any())
        ml=t.loc[t.variant.eq('Cross-fitted error model')]
        self.assertTrue(ml.mae_leader.eq('NOT_APPLICABLE').all())
        saved=f.read(f.diagnostic.RESULTS/'cross_fitted_performance.csv')
        np.testing.assert_array_equal(ml.mae_bps,saved.MAE)

    def test_attrition_parallel_sets_and_exact_common(self):
        t=self.tables['appendix_data_lineage_attrition']
        expected={'stocks':(14499,9707),'etfs':(8649,3175),'futures':(2331,1667),'crypto':(12753,9828),'ALL':(38232,24377)}
        for cls,(design,common) in expected.items():
            p=t.loc[t.asset_class.eq(cls)].set_index('stage')
            self.assertEqual(p.loc['design_eligible','N'],design)
            self.assertEqual(p.loc['common_defined','N'],common)
            self.assertEqual(p.loc['ROLL_defined','N']-common,p.loc['additional_loss_after_Roll_defined','N'])
        self.assertEqual(t.loc[t.asset_class.eq('ALL')&t.stage.eq('additional_loss_after_Roll_defined'),'N'].iloc[0],117)
        pd.testing.assert_frame_equal(f.read(f.PROJECT/'manifests/sample_attrition.csv'),f.read(f.TABLES/'appendix_data_lineage_attrition.csv'))

    def test_master_all_values_trace_to_source_row_metric(self):
        m=f.read(f.MASTER)
        self.assertFalse(m.duplicated(['source_result_file','source_row','metric']).any())
        for path,part in m.groupby('source_result_file'):
            self.assertTrue(path.startswith(('outputs/results/','outputs/tables/')))
            original=f.read(f.PROJECT/path)
            for metric,rows in part.groupby('metric'):
                np.testing.assert_allclose(rows.value,original.loc[rows.source_row.astype(int),metric].astype(float),rtol=1e-14,atol=1e-14)
        no_ci=m.loc[m.metric.str.contains('mae|rmse',case=False)]
        self.assertTrue(no_ci.standard_error.isna().all())
        self.assertTrue(no_ci.p_value.isna().all())

    def test_readme_headlines_generated_from_results(self):
        text=(f.PROJECT/'README.md').read_text(encoding='utf-8')
        overall=self.tables['table2_primary_horse_race'].query("panel == 'A'")
        self.assertIn(f'{int(overall.N_asset_days.iloc[0]):,}',text)
        for metric in ['bias_bps','mae_bps','rmse_bps']:
            for value in overall[metric]:self.assertIn(f'{value:.6g}',text)
        for phrase in ['stocks are mixed','ETFs favor CS','UNKNOWN','IMDX','FX remains','HAC inference is for signed bias only']:
            self.assertIn(phrase,text)

    def test_documentation_authorization_preserves_historical_test(self):
        receipt=json.loads((f.REPRO/'documentation_transition.json').read_text())
        self.assertEqual(set(receipt['authorized_document_paths']),set(f.DOCS))
        for path,digest in receipt['authorized_document_sha256'].items():self.assertEqual(f.sha256(f.PROJECT/path),digest)
        old=json.loads((f.source.DESIGN/'run_manifest.json').read_text())
        self.assertEqual(f.sha256(f.REPRO/'historical_test_global_design_freeze.py.txt'),old['code_sha256']['tests/test_global_design_freeze.py'])

    def test_manifest_raw11_and_derived_constructs(self):
        a=f.read(f.PROJECT/'data_manifest.csv');b=f.read(f.PROJECT/'manifests/data_manifest.csv')
        pd.testing.assert_frame_equal(a,b)
        raw=f.read(f.PROJECT/'data/raw_bloomberg/sha256_manifest.csv')
        self.assertEqual(len(raw),11)
        for name in raw.file_name:self.assertIn('data/raw_bloomberg/'+name,a.source_path.tolist())
        for name in ['roll_benchmark_panel','estimator_panel','common_accuracy_panel','primary_results','robustness_results','error_model_results']:
            self.assertIn(name,a.dataset_id.tolist())

    def test_figures_full_range_300dpi_and_lineage(self):
        from PIL import Image
        lineage=f.read(f.REPRO/'figure_lineage.csv')
        self.assertEqual(len(lineage),5)
        self.assertFalse(lineage.display_clipping.any())
        for name in lineage.figure:
            with Image.open(f.FIGURES/(name+'.png')) as im:
                for dpi in im.info['dpi']:self.assertAlmostEqual(dpi,300,delta=.1)
            self.assertGreater((f.FIGURES/(name+'.pdf')).stat().st_size,1000)

    def test_no_licensed_observations_tracked(self):
        tracked=subprocess.run(['git','ls-files'],cwd=f.PROJECT,capture_output=True,text=True,check=True).stdout.splitlines()
        for name in tracked:
            self.assertFalse(name.startswith(('data/raw_bloomberg/','data/analytic/','data/interim/')) or name.endswith(('.xlsx','.parquet','.pkl','.joblib')),name)
        for name in ['data/raw_bloomberg/test.xlsx','data/analytic/test.parquet','data/interim/test.parquet','outputs/diagnostics/test.csv']:
            r=subprocess.run(['git','check-ignore',name],cwd=f.PROJECT,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,name)

    def test_raw_hashes_and_saved_analytic_locks(self):
        raw,_=f.verify_hashes(f.PROJECT/'data/raw_bloomberg');f.require_verified(raw)
        self.assertEqual(len(raw),11)
        f.inputs()

    def test_legacy_raw_excerpts_private_and_public_notebook_code_unchanged(self):
        receipt=json.loads((f.REPRO/'licensed_data_remediation.json').read_text())
        self.assertTrue(receipt['current_index_raw_excerpts_removed'])
        self.assertTrue(receipt['historical_git_blobs_still_present'])
        for row in receipt['local_originals_unchanged']:
            self.assertEqual(f.sha256(f.PROJECT/row['relative_path']),row['local_sha256'])
        a=json.loads((f.PROJECT/'notebooks/01_initial_exploratory_analysis.ipynb').read_text(encoding='utf-8'))
        b=json.loads((f.PROJECT/receipt['code_only_notebook']).read_text(encoding='utf-8'))
        self.assertEqual([c['source'] for c in a['cells']],[c['source'] for c in b['cells']])
        self.assertTrue(all(not c.get('outputs') for c in b['cells']))


if __name__=='__main__':unittest.main()
