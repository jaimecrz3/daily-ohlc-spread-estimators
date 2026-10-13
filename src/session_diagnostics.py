"""Small common-window session audit; run python -B src/session_diagnostics.py.

Scans raw files in bounded chunks after ten-row pilot reads. Counts raw bars in
2024-11-04 <= provider calendar timestamp < 2024-11-16, not full-file bars.
No estimator calculations. Historical exploratory artifacts are not overwritten.
"""
import json
from itertools import islice
from pathlib import Path

import pandas as pd

from data_io import PILOT_FILES, asset_metadata, inspect_file, intraday_root
from eda_diagnostics import parse_chunk
from session_rules import assign_primary_session

START, END = pd.Timestamp('2024-11-04'), pd.Timestamp('2024-11-16')
ASSETS = {'AAPL', 'SPY', 'BTC', 'ETH'}


def main():
    out = Path(__file__).resolve().parents[1] / 'outputs' / 'diagnostics'
    out.mkdir(parents=True, exist_ok=True)
    root = intraday_root()
    summaries, failures, pilots = [], [], []
    for relative in PILOT_FILES:
        asset = Path(relative).name.split('_')[0]
        if asset not in ASSETS:
            continue
        cls = relative.split('/')[0]
        pilot = inspect_file(root, relative)
        pilots.append(pilot)
        try:
            if pilot['status'] != 'ok':
                raise ValueError(f'Pilot failed: {pilot}')
            path = root / relative
            before = path.stat()
            pieces = []
            scanned = outside = unassignable = 0
            audit_path = out / f'{asset}_session_exclusions.csv'
            with audit_path.open('w', encoding='utf-8', newline='') as audit:
                audit.write('raw_line_number,raw_timestamp,reason\n')
                with path.open(encoding='utf-8-sig', newline='') as stream:
                    offset = 1
                    while lines := list(islice(stream, 100_000)):
                        raw, parsed = parse_chunk(lines, offset)
                        scanned += len(parsed)
                        bad = parsed.timestamp.isna() | parsed.malformed_columns
                        in_window = parsed.timestamp.ge(START) & parsed.timestamp.lt(END)
                        outside += int((~bad & ~in_window).sum())
                        unassignable += int(bad.sum())
                        if bad.any():
                            pd.DataFrame({'raw_line_number': parsed.index[bad],
                                          'raw_timestamp': raw.timestamp[bad],
                                          'reason': 'unassignable_timestamp_or_malformed_columns'}).to_csv(audit, index=False, header=False)
                        # Keep malformed but date-assignable rows in the diagnostic.
                        if in_window.any():
                            pieces.append(parsed.loc[in_window])
                        offset += len(parsed)
                if not pieces:
                    raise ValueError('No timestamp-assignable rows in diagnostic window')
                data = pd.concat(pieces)
                data['duplicate_timestamp'] = data.timestamp.duplicated(keep=False)
                annotated = assign_primary_session(data, cls)
                excluded = annotated.loc[~annotated.primary_session_retained]
                pd.DataFrame({'raw_line_number': excluded.index,
                              'raw_timestamp': excluded.timestamp,
                              'reason': 'outside_primary_session'}).to_csv(audit, index=False, header=False)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError('Source changed during scan')
            retained = annotated.loc[annotated.primary_session_retained]
            annotated.loc[annotated.zero_volume].to_csv(out / f'{asset}_session_zero_volume_rows.csv', index=True)
            summary = dict(asset=asset, file=relative, window_start=str(START.date()),
                           window_end_exclusive=str(END.date()), raw_bars=len(data),
                           primary_session_bars=len(retained),
                           first_retained_timestamp=retained.timestamp_local.min(),
                           last_retained_timestamp=retained.timestamp_local.max(),
                           **asset_metadata(cls), zero_volume_rows=int(annotated.zero_volume.sum()),
                           retained_zero_volume_rows=int(retained.zero_volume.sum()),
                           raw_rows_scanned=scanned, outside_window_assignable_rows=outside,
                           unassignable_or_malformed_rows=unassignable,
                           timezone_assignment_failed_rows=int(annotated.timezone_assignment_failed.sum()),
                           inserted_minute_bars=0, raw_size_bytes=before.st_size,
                           raw_mtime_ns=before.st_mtime_ns)
            summaries.append(summary)
            print(json.dumps(summary, default=str), flush=True)
        except Exception as exc:
            failures.append(dict(file=relative, error_type=type(exc).__name__, error=str(exc)))
    table = pd.DataFrame(summaries)
    table.to_csv(out / 'primary_session_summary.csv', index=False)
    pd.DataFrame(failures, columns=['file', 'error_type', 'error']).to_csv(out / 'session_failures.csv', index=False)
    (out / 'session_manifest.json').write_text(json.dumps(dict(
        source_root=str(root), pilots=pilots, window_start=str(START), window_end_exclusive=str(END),
        scope='common-window raw bars; full files scanned read-only; date exclusions counted',
        session_rules={'stocks': '09:30 <= NY local time < 16:00', 'etfs': '09:30 <= NY local time < 16:00', 'cryptos': 'UTC calendar day'},
        pending=['root-specific futures sessions/universe', 'FX folder inaccessible', 'benchmark definition', 'negative/undefined estimator treatment'],
        zero_volume_note='Provider says omitted; historical exploratory project window: AAPL 94, GME 1277. Retain and flag; historical outputs unchanged.',
        inserted_minute_bars=0, failures=failures), indent=2, default=str), encoding='utf-8')
    columns = ['asset', 'raw_bars', 'primary_session_bars', 'first_retained_timestamp', 'last_retained_timestamp', 'timezone', 'volume_units']
    text = '# Primary session diagnostic: 2024-11-04 through 2024-11-15\n\n'
    text += '| ' + ' | '.join(columns) + ' |\n|' + '|'.join(['---'] * len(columns)) + '|\n'
    for record in summaries:
        text += '| ' + ' | '.join(str(record[c]) for c in columns) + ' |\n'
    text += '\nRaw bars refer to this window only. No filling, deduplication, quality exclusions, holiday or early-close adjustment. Zero-volume rows retained and flagged. Futures and FX pending. No estimators computed.\n'
    (out / 'primary_session_summary.md').write_text(text, encoding='utf-8')
    if failures:
        raise RuntimeError('Diagnostic failures: see session_failures.csv')


if __name__ == '__main__':
    main()
