"""Inspect the eight intraday pilots without altering or fully loading raw files.

Run: python -B src/data_io.py
Schema/dtypes are sample inferences, not a full-file validation. Field semantics
are inferred from headerless OHLCV layout; class metadata come from provider documentation.
No filtering, filling, session selection, or estimator calculations are performed.
"""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
import io
from itertools import islice
import json
import os
from pathlib import Path
import re

PILOT_FILES = (
    'stocks/AAPL_full_1min_adjsplitdiv.txt',
    'stocks/GME_full_1min_adjsplitdiv.txt',
    'etfs/SPY_full_1min_adjsplitdiv.txt',
    'etfs/IWM_full_1min_adjsplitdiv.txt',
    'futures/ES_Z24_1min.txt',
    'futures/CL_Z24_1min.txt',
    'cryptos/BTC_full_1min.txt',
    'cryptos/ETH_full_1min.txt',
)
TIMESTAMP_FORMAT = '%Y-%m-%d %H:%M:%S'
SCHEMA = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
ASSET_METADATA = {
    'stocks': dict(timezone='America/New_York', volume_units='shares', adjustment='split+dividend adjusted (*_adjsplitdiv)'),
    'etfs': dict(timezone='America/New_York', volume_units='shares', adjustment='split+dividend adjusted (*_adjsplitdiv)'),
    'futures': dict(timezone='America/New_York', volume_units='futures contracts', adjustment='unadjusted individual contracts'),
    'cryptos': dict(timezone='UTC', volume_units='crypto units', adjustment='not specified by provider documentation'),
}


def asset_metadata(asset_class: str) -> dict:
    """Return a copy of documented metadata; FX is deliberately unsupported."""
    if asset_class not in ASSET_METADATA:
        raise ValueError(f'Unsupported asset class: {asset_class}; FX remains inaccessible')
    return dict(ASSET_METADATA[asset_class])


def intraday_root() -> Path:
    """Resolve only the intraday archive through RISKLAB_DATA_ROOT."""
    value = os.environ.get('RISKLAB_DATA_ROOT')
    if not value:
        raise RuntimeError('RISKLAB_DATA_ROOT is not set')
    root = Path(value)
    return root if root.name.lower() == 'intraday_data' else root / 'intraday_data'


def is_timestamp(value: str) -> bool:
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', value):
        return False
    try:
        datetime.strptime(value, TIMESTAMP_FORMAT)
        return True
    except ValueError:
        return False


def infer_dtype(values: list[str]) -> str:
    """Describe textual sample values without coercing or discarding them."""
    if not values:
        return 'unknown'
    if any(value == '' for value in values):
        return 'string (contains empty values)'
    if all(is_timestamp(value) for value in values):
        return 'datetime (naive provider wall clock; timezone defined by asset class)'
    if all(re.fullmatch(r'[+-]?\d+', value) for value in values):
        return 'integer'
    try:
        if all(Decimal(value).is_finite() for value in values):
            return 'decimal/float'
    except InvalidOperation:
        pass
    return 'string/mixed'


def last_nonempty_line(path: Path, block_size: int = 4096) -> tuple[str, int]:
    """Seek backward in binary mode; memory scales with the final record.

    Trailing empty lines are skipped solely to locate the last available record.
    """
    with path.open('rb') as stream:
        position = stream.seek(0, 2)
        buffer = b''
        bytes_read = 0
        while position:
            size = min(block_size, position)
            position -= size
            stream.seek(position)
            buffer = stream.read(size) + buffer
            bytes_read += size
            lines = buffer.split(b'\n')
            complete = lines if position == 0 else lines[1:]
            for line in reversed(complete):
                if line.strip():
                    return line.rstrip(b'\r').decode('utf-8-sig'), bytes_read
        return '', bytes_read


def inspect_file(root: Path, relative_path: str) -> dict:
    """Read at most ten initial physical rows, then the last record."""
    path = root / relative_path
    result = dict(asset_class=relative_path.split('/')[0], file=relative_path,
                  raw_path=str(path), exists=False, status='pending', error='')
    result.update(asset_metadata(result['asset_class']))
    result['metadata_basis'] = 'provider documentation supplied at design freeze'
    result['provider_zero_volume_policy'] = 'zero-volume bars omitted; observed zero-volume rows retained and flagged'
    try:
        result['exists'] = path.is_file()
        if not result['exists']:
            result.update(status='missing', error='Requested file does not exist')
            return result
        result['file_size_bytes'] = path.stat().st_size
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            initial_lines = list(islice(stream, 10))
        rows = list(csv.reader(initial_lines, delimiter=','))
        result['initial_rows_read'] = len(rows)
        result['sample_raw_rows_json'] = json.dumps(rows)
        if not rows:
            result.update(status='empty', error='No initial rows')
            return result
        widths = sorted({len(row) for row in rows})
        result['sample_column_counts_json'] = json.dumps(widths)
        result['number_of_columns'] = widths[0] if len(widths) == 1 else 'inconsistent'
        result['delimiter'] = ','
        result['line_ending'] = 'CRLF' if all(x.endswith('\r\n') for x in initial_lines) else 'mixed/other'
        first = rows[0]
        header = [value.lower().strip() for value in first] == SCHEMA
        headerless = len(first) == 6 and is_timestamp(first[0])
        result['has_header'] = 'yes' if header else 'no' if headerless else 'undetermined'
        data = rows[1:] if header else rows
        names = SCHEMA if widths == [6] else [f'column_{i+1}' for i in range(max(widths))]
        result['inferred_schema_json'] = json.dumps(names)
        result['schema_basis'] = 'explicit header' if header else 'positional OHLCV inference; provider semantics unverified'
        result['inferred_dtypes_json'] = json.dumps({name: infer_dtype([row[i] for row in data if len(row) > i]) for i, name in enumerate(names)})
        result['timestamp_format'] = TIMESTAMP_FORMAT if data and all(row and is_timestamp(row[0]) for row in data) else 'undetermined/mixed'
        last_line, tail_bytes = last_nonempty_line(path)
        last = next(csv.reader([last_line])) if last_line else []
        result['tail_bytes_read'] = tail_bytes
        result['last_raw_row_json'] = json.dumps(last)
        result['last_row_columns'] = len(last)
        result['first_timestamp'] = data[0][0] if data and data[0] else ''
        result['last_timestamp'] = last[0] if last else ''
        result['endpoint_basis'] = 'first/last data records; chronological ordering and global extrema not verified'
        result['dtype_scope'] = 'first 10 physical rows only; not full-file validation'
        result['status'] = 'ok' if widths == [6] and result['has_header'] != 'undetermined' and result['timestamp_format'] == TIMESTAMP_FORMAT and len(last) == 6 and is_timestamp(last[0]) else 'needs_review'
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        result.update(status='error', error=f'{type(exc).__name__}: {exc}')
    return result


def main() -> None:
    project = Path(__file__).resolve().parents[1]
    output = project / 'outputs' / 'diagnostics' / 'pilot_schema.csv'
    root = intraday_root()
    records = [inspect_file(root, relative) for relative in PILOT_FILES]
    fields = list(dict.fromkeys(key for record in records for key in record))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    for record in records:
        print(json.dumps({key: record.get(key) for key in ('file', 'exists', 'status', 'number_of_columns', 'has_header', 'inferred_dtypes_json', 'first_timestamp', 'last_timestamp', 'tail_bytes_read', 'error')}))
    print(f'Saved {output}')


if __name__ == '__main__':
    main()
