from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import fx_access_review as fx


class FxAccessTests(unittest.TestCase):
    def test_only_configured_official_fx_path_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'RISKLAB_DATA_ROOT': directory}):
                with patch.object(Path, 'iterdir', side_effect=FileNotFoundError('missing')) as probe:
                    record = fx.probe_official_fx()
            self.assertEqual(record['official_path'], str(Path(directory) / 'intraday_data/fx'))
            self.assertEqual(probe.call_count, 1)
            self.assertEqual(record['status'], 'BLOCKED')
            self.assertIsNone(record['inventory_count'])

    def test_missing_environment_never_uses_substitute(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(Path, 'iterdir') as probe:
                record = fx.probe_official_fx()
        probe.assert_not_called()
        self.assertEqual(record['error_type'], 'RuntimeError')
        self.assertEqual(record['official_path'], '')

    def test_access_denied_retains_failure_without_fallback(self):
        with patch.object(fx, 'intraday_root', return_value=Path('official/intraday_data')):
            with patch.object(Path, 'iterdir', side_effect=PermissionError('denied')) as probe:
                record = fx.probe_official_fx()
        self.assertEqual(record['error_type'], 'PermissionError')
        self.assertEqual(probe.call_count, 1)
        self.assertIn('denied', record['error_message'])

    def test_blocked_outputs_do_not_invent_inventory_sessions_or_rankings(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(fx, 'intraday_root', side_effect=RuntimeError('unset')):
                record = fx.probe_official_fx()
            out = Path(directory)
            fx.write_blocked_review(record, 'sandbox', out)
            spec = yaml.safe_load((out / 'fx_final_spec.yaml').read_text())
            self.assertEqual(spec['status'], 'BLOCKED')
            self.assertIsNone(spec['inventory_count'])
            self.assertIsNone(spec['eligible_count'])
            self.assertIsNone(spec['primary_common_calendar'])
            self.assertEqual(spec['selected_pairs'], [])
            self.assertFalse(spec['substitute_sources_permitted'])
            self.assertEqual({p.name for p in out.iterdir()}, {
                'fx_access_audit.csv', 'fx_final_spec.yaml',
                'fx_session_review.md', 'fx_design_freeze_review.md'})

    def test_successful_access_cannot_approve_unvalidated_methodology(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                fx.write_blocked_review({'accessible': True, 'status': 'ACCESSIBLE_PENDING_VALIDATION'},
                                        'sandbox', Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_no_benchmark_or_estimator_dependency(self):
        result = subprocess.run([sys.executable, '-B', '-c',
            "import sys;sys.path.insert(0,'src');import fx_access_review;"
            "assert not any(n in sys.modules for n in ['benchmark','corwin_schultz','abdi_ranaldo','edge'])"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
