"""Step 13 official FX access gate. No alternative source or analytical fallback.

Run with --context sandbox or approved_outside_sandbox to record each attempt.
Only blocked-access artifacts are produced; successful access requires a separate
documentation/inventory review before any daily convention can be approved.
"""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import json

import yaml

from data_io import intraday_root

PROJECT = Path(__file__).resolve().parents[1]
OUT = PROJECT / 'outputs/diagnostics/final_universe/fx_final'


def probe_official_fx():
    record = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),
                  logical_path='intraday_data/fx', official_path='',
                  accessible=False, status='BLOCKED', error_type='', error_message='',
                  errno='', winerror='', inventory_count=None)
    try:
        # No path argument, default location, web source or fallback is accepted.
        path = intraday_root() / 'fx'
        record['official_path'] = str(path)
        entries = list(path.iterdir())
        record.update(accessible=True, status='ACCESSIBLE_PENDING_VALIDATION')
        # Directory entries do not establish an inventory of provider FX files.
        del entries
    except (OSError, RuntimeError) as exc:
        record.update(error_type=type(exc).__name__, error_message=str(exc),
                      errno=getattr(exc, 'errno', '') or '',
                      winerror=getattr(exc, 'winerror', '') or '')
    return record


def write_blocked_review(record, context, out=OUT):
    if record['accessible'] or record['status'] != 'BLOCKED':
        raise ValueError('Access succeeded: documentation and inventory review required; no automatic freeze')
    out.mkdir(parents=True, exist_ok=True)
    audit = out / 'fx_access_audit.csv'
    row = dict(record, execution_context=context)
    with audit.open('a', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(row))
        if stream.tell() == 0:
            writer.writeheader()
        writer.writerow(row)
    spec = dict(status='BLOCKED', step=13, official_source_only=True,
                official_logical_path='intraday_data/fx', official_path=record['official_path'],
                last_access_context=context, access_error_type=record['error_type'],
                access_error=record['error_message'], access_winerror=record['winerror'],
                inventory_count=None, eligible_count=None, selected_pairs=[],
                timezone_status='NOT_ASSESSED_ACCESS_BLOCKED',
                daily_session_status='NOT_FROZEN_ACCESS_BLOCKED',
                liquidity_comparability_status='NOT_ASSESSED_ACCESS_BLOCKED',
                primary_common_calendar=None, substitute_sources_permitted=False,
                external_downloads_performed=False, raw_data_modified=False,
                benchmark_or_estimator_values_calculated=False,
                blocked_reason='Official FX directory cannot be enumerated; stop before inventory or methodology',
                resume_requirement='Restore official folder access, then verify provider timezone, pair direction, daily boundaries and comparable liquidity before selection')
    (out / 'fx_final_spec.yaml').write_text(yaml.safe_dump(spec, sort_keys=False), encoding='utf-8')
    with audit.open(encoding='utf-8', newline='') as stream:
        attempts = list(csv.DictReader(stream))
    report = '# Step 13 FX access review\n\n**Status: BLOCKED.**\n\n'
    report += f'Only configured official path checked: `{record["official_path"]}`.\n\n'
    for attempt in attempts:
        report += (f'- {attempt["checked_at_utc"]} ({attempt["execution_context"]}): '
                   f'{attempt["error_type"]}, WinError {attempt["winerror"]}; '
                   f'{attempt["error_message"]}\n')
    report += ('\nInventory and eligible counts are **unknown**, not zero. No inventory, '
               'daily coverage, liquidity ranking or selection tables were fabricated. '
               'No files were downloaded and no substitute source was consulted.\n\n'
               'Provider timezone, pair direction, daily boundary and cross-pair liquidity '
               'comparability remain unassessed. No UTC assumption, session freeze, tier '
               'assignment, final nine or common calendar is authorized by this access check.\n\n'
               'The official folder must become accessible before continuing Step 13. '
               'Raw data, existing specifications, README.md, design_decisions.md and '
               'data_manifest.csv were not modified. No Roll, CS, AR or EDGE values were calculated.\n')
    (out / 'fx_design_freeze_review.md').write_text(report, encoding='utf-8')
    (out / 'fx_session_review.md').write_text(
        '# FX session review\n\nStatus: BLOCKED at official-source access gate.\n\n'
        'Provider timezone, pair denomination/direction and daily-boundary evidence '
        'have not been inspected because the official FX folder is inaccessible. '
        'No session convention is frozen; UTC is not assumed. Liquidity comparability '
        'is unassessed. No aggregation or selection was run.\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context', choices=['sandbox', 'approved_outside_sandbox'], required=True)
    args = parser.parse_args()
    record = probe_official_fx()
    write_blocked_review(record, args.context)
    print(json.dumps(record, indent=2))


if __name__ == '__main__':
    main()
