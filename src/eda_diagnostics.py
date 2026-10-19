"""Descriptive intraday diagnostics only; no spread estimators or session filters.

Run from any directory: python -B src/eda_diagnostics.py
Inputs are resolved exclusively through data_io.intraday_root().
Full files are scanned in bounded chunks; one asset's project-window numeric
rows are retained at a time for exact duplicate, quantile, and gap diagnostics.
Raw files are opened read-only. All generated artifacts live under outputs/.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from itertools import islice
import json
import os
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from data_io import PILOT_FILES, SCHEMA, TIMESTAMP_FORMAT, intraday_root

PROJECT = Path(__file__).resolve().parents[1]
START, END = pd.Timestamp("2015-01-01"), pd.Timestamp("2026-01-01")
COMMON_START, COMMON_END = pd.Timestamp("2024-11-04"), pd.Timestamp("2024-11-16")
WINDOWS = {"project": (START, END), "common": (COMMON_START, COMMON_END)}
NUMERIC = SCHEMA[1:]
FLAGS = ["missing_value", "non_numeric", "non_finite", "invalid_ohlc",
         "zero_volume", "negative_volume", "duplicate_timestamp"]
MISSING = {"", "na", "nan", "null", "none", "n/a"}


def parse_chunk(lines: list[str], first_line: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preserve physical line numbers; never silently skip malformed records."""
    fields = [line.rstrip("\r\n").split(",") for line in lines]
    widths = np.array([len(row) for row in fields])
    raw = pd.DataFrame([(row + [""] * 6)[:6] for row in fields], columns=SCHEMA)
    raw.index = pd.RangeIndex(first_line, first_line + len(raw), name="raw_line_number")
    raw = raw.apply(lambda col: col.str.strip())
    dt = pd.to_datetime(raw.timestamp, format=TIMESTAMP_FORMAT, errors="coerce")
    exact = raw.timestamp.str.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
    dt = dt.where(exact)
    values = raw[NUMERIC].apply(pd.to_numeric, errors="coerce").astype("float64")
    missing = raw.apply(lambda col: col.str.lower().isin(MISSING))
    nonnumeric = values.isna() & ~missing[NUMERIC]
    finite = pd.DataFrame(np.isfinite(values), index=raw.index, columns=NUMERIC)
    prices = values[["open", "high", "low", "close"]]
    price_finite = finite[["open", "high", "low", "close"]].all(axis=1)
    inconsistent = ((prices.high < prices.low) | (prices.open > prices.high) |
                    (prices.open < prices.low) | (prices.close > prices.high) |
                    (prices.close < prices.low))
    parsed = values.copy()
    parsed.insert(0, "timestamp", dt)
    parsed["missing_value"] = missing.any(axis=1)
    parsed["non_numeric"] = nonnumeric.any(axis=1)
    parsed["non_finite"] = ((~finite) & values.notna()).any(axis=1)
    parsed["invalid_ohlc"] = price_finite & ((prices <= 0).any(axis=1) | inconsistent)
    parsed["zero_volume"] = values.volume.eq(0)
    parsed["negative_volume"] = values.volume.lt(0)
    parsed["malformed_columns"] = widths != 6
    for col in SCHEMA:
        parsed["missing_" + col] = missing[col]
    for col in NUMERIC:
        parsed["non_numeric_" + col] = nonnumeric[col]
    return raw, parsed


def read_asset(path: Path, asset: str, out: Path, chunk_size=100_000):
    """Scan full file including excluded dates; retain project-window rows only."""
    pieces, manual = [], []
    audit = Counter()
    wanted = 2 if asset in {"AAPL", "BTC"} else 1
    before = path.stat()
    audit_path = out / "diagnostics" / f"{asset}_unassignable_rows.csv"
    with audit_path.open("w", encoding="utf-8", newline="") as failures:
        failures.write("raw_line_number,raw_text,reason\n")
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            offset = 1
            while lines := list(islice(stream, chunk_size)):
                raw, parsed = parse_chunk(lines, offset)
                audit["raw_rows_scanned"] += len(lines)
                malformed = parsed.malformed_columns
                unparseable = ~malformed & parsed.timestamp.isna()
                assignable = ~malformed & parsed.timestamp.notna()
                before_horizon = assignable & parsed.timestamp.lt(START)
                after_horizon = assignable & parsed.timestamp.ge(END)
                selected = assignable & parsed.timestamp.ge(START) & parsed.timestamp.lt(END)
                for name, mask in [("malformed_column_rows", malformed),
                                   ("unparseable_timestamp_rows", unparseable),
                                   ("rows_before_2015", before_horizon),
                                   ("rows_after_2025", after_horizon),
                                   ("project_rows", selected)]:
                    audit[name] += int(mask.sum())
                bad = malformed | unparseable
                if bad.any():
                    pd.DataFrame({
                        "raw_line_number": parsed.index[bad],
                        "raw_text": [lines[i-offset].rstrip("\r\n") for i in parsed.index[bad]],
                        "reason": np.where(malformed[bad], "malformed_columns", "unparseable_timestamp"),
                    }).to_csv(failures, index=False, header=False)
                if selected.any():
                    pieces.append(parsed.loc[selected].drop(columns="malformed_columns"))
                common = selected & parsed.timestamp.ge(COMMON_START) & parsed.timestamp.lt(COMMON_END)
                if len(manual) < wanted:
                    for line_number in parsed.index[common][:wanted-len(manual)]:
                        manual.append({"asset": asset, "raw_path": str(path),
                                       "raw_line_number": int(line_number),
                                       "raw_text": lines[line_number-offset].rstrip("\r\n")})
                offset += len(lines)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError(f"Source changed during read: {path}")
    audit["raw_size_bytes"] = before.st_size
    audit["raw_mtime_ns"] = before.st_mtime_ns
    if not pieces:
        raise ValueError(f"No assignable project-window rows: {path}; audit={dict(audit)}")
    data = pd.concat(pieces)
    audit["backward_steps_in_raw_order"] = int(data.timestamp.diff().lt(pd.Timedelta(0)).sum())
    audit["duplicate_excess_rows"] = int(data.timestamp.duplicated().sum())
    data["duplicate_timestamp"] = data.timestamp.duplicated(keep=False)
    # Stable order preserves physical line order for ties; nothing is deduplicated.
    data = data.sort_values("timestamp", kind="stable")
    return data, manual, dict(audit)


def add_derivatives(data: pd.DataFrame) -> pd.DataFrame:
    """Explicit diagnostic validity rules; no permanent exclusion/cleaning policy."""
    data = data.copy()
    p = data[["open", "high", "low", "close"]]
    valid_price = np.isfinite(p).all(axis=1) & ~data.invalid_ohlc
    data["bar_range"] = (data.high - data.low).where(valid_price)
    data["bar_range_pct"] = (100 * data.bar_range / data.close).where(valid_price)
    gap = data.timestamp.diff().dt.total_seconds() / 60
    data["gap_minutes"] = gap
    prev_valid = valid_price.shift(fill_value=False)
    duplicate_pair = data.duplicate_timestamp | data.duplicate_timestamp.shift(fill_value=False)
    valid_pair = valid_price & prev_valid & gap.gt(0) & ~duplicate_pair
    data["simple_return_pct"] = (100 * (data.close / data.close.shift() - 1)).where(valid_pair)
    data["one_minute_return_pct"] = data.simple_return_pct.where(gap.eq(1))
    data["date"] = data.timestamp.dt.floor("D")
    return data


def summarize(values: pd.Series) -> dict:
    x = values[np.isfinite(values)]
    if x.empty:
        return {"n": 0, **{k: np.nan for k in ["mean", "std", "min", "p25", "median", "p75", "p95", "p99", "max"]}}
    q = x.quantile([.25, .5, .75, .95, .99])
    return dict(n=len(x), mean=x.mean(), std=x.std(), min=x.min(),
                p25=q.loc[.25], median=q.loc[.5], p75=q.loc[.75],
                p95=q.loc[.95], p99=q.loc[.99], max=x.max())


def window_tables(data: pd.DataFrame, asset: str, asset_class: str, window: str):
    lo, hi = WINDOWS[window]
    d = data.loc[data.timestamp.ge(lo) & data.timestamp.lt(hi)].copy()
    # Recompute at each window boundary: no prior-window price enters returns.
    d = add_derivatives(d)
    base = dict(asset=asset, asset_class=asset_class, window=window)
    counts = d.groupby("date").size()
    dates = pd.date_range(lo, hi - pd.Timedelta(days=1), freq="D")
    daily = pd.DataFrame({"date": dates, "observed_rows": counts.reindex(dates, fill_value=0).to_numpy()})
    unique = d.groupby("date").timestamp.nunique()
    daily["unique_timestamps"] = unique.reindex(dates, fill_value=0).to_numpy()
    daily["no_observed_rows"] = daily.observed_rows.eq(0)
    daily["low_count_observed_day_le10"] = daily.observed_rows.between(1, 10)
    daily["futures_sparse_review_flag"] = (asset_class == "futures") & daily.low_count_observed_day_le10
    for key, value in base.items():
        daily[key] = value
    coverage = dict(**base, first_timestamp=d.timestamp.min(), last_timestamp=d.timestamp.max(),
                    observed_rows=len(d), unique_timestamps=d.timestamp.nunique(),
                    observed_calendar_days=int((daily.observed_rows > 0).sum()),
                    calendar_days_in_window=len(daily),
                    calendar_dates_without_observations=int(daily.no_observed_rows.sum()),
                    inserted_minute_bars=0, timezone="unresolved", session="unfiltered raw clock")
    quality = dict(**base, observed_rows=len(d),
                   duplicate_excess_rows=int(d.timestamp.duplicated().sum()),
                   **{flag + "_rows": int(d[flag].sum()) for flag in FLAGS})
    for col in SCHEMA:
        quality["missing_" + col + "_rows"] = int(d["missing_" + col].sum())
    for col in NUMERIC:
        quality["non_numeric_" + col + "_rows"] = int(d["non_numeric_" + col].sum())
    bars = []
    for population, vals in [("all_calendar_dates_zero_row_dates_included", daily.observed_rows),
                             ("observed_dates_only", counts)]:
        bars.append(dict(**base, population=population, **summarize(vals)))
    gaps = []
    same_date = d.date.eq(d.date.shift())
    for population, vals in [("all_adjacent_observed_records", d.gap_minutes),
                             ("same_raw_calendar_date", d.gap_minutes.where(same_date))]:
        gaps.append(dict(**base, population=population, **summarize(vals),
                         gaps_over_one_minute=int(vals.gt(1).sum()),
                         zero_gaps=int(vals.eq(0).sum())))
    metrics = {
        "close_raw_price": d.close,
        "volume_raw_units": d.volume,
        "bar_high_minus_low": d.bar_range,
        "bar_range_pct_of_close": d.bar_range_pct,
        "adjacent_observed_return_pct": d.simple_return_pct,
        "one_minute_pair_return_pct": d.one_minute_return_pct,
    }
    # Daily extrema use only valid OHLC rows; count invalid rows separately above.
    valid = np.isfinite(d[["open", "high", "low", "close"]]).all(axis=1) & ~d.invalid_ohlc
    valid_days = d.loc[valid].groupby("date").agg(high=("high", "max"), low=("low", "min"))
    metrics["observed_calendar_day_high_minus_low"] = valid_days.high - valid_days.low
    descriptives = [dict(**base, metric=name, input_rows=len(vals),
                         undefined_or_nonfinite=int((~np.isfinite(vals)).sum()), **summarize(vals))
                    for name, vals in metrics.items()]
    hourly = d.groupby(d.timestamp.dt.hour).size().reindex(range(24), fill_value=0)
    hours = pd.DataFrame({"hour_raw_clock": range(24), "observed_rows": hourly.to_numpy()})
    for key, value in base.items():
        hours[key] = value
    minutes = d.timestamp.dt.hour * 60 + d.timestamp.dt.minute
    outside = ~minutes.between(570, 959)  # descriptive clock marker only
    clock = dict(**base, rows_outside_raw_clock_0930_to_1600=int(outside.sum()),
                 assessment=("apparent_extended_clock_coverage_if_US_exchange_local_time"
                             if asset_class in {"stocks", "etfs"} and outside.any()
                             else "session_interpretation_unresolved"),
                 note="09:30 <= raw clock < 16:00 is a reference marker only; no timezone/session assumed")
    return coverage, quality, bars, gaps, descriptives, daily, hours, clock


def manual_check(data: pd.DataFrame, record: dict) -> dict:
    """Independent datetime/Decimal recomputation for exact raw-row traceability."""
    index = record["raw_line_number"]
    row = data.loc[index]
    fields = record["raw_text"].split(",")
    expected_dt = datetime.strptime(fields[0], TIMESTAMP_FORMAT)
    numbers = [Decimal(v) for v in fields[1:]]
    expected_range = numbers[1] - numbers[2]
    position = data.index.get_loc(index)
    prev = data.iloc[position - 1] if position else None
    expected_gap = ((expected_dt - prev.timestamp.to_pydatetime()).total_seconds() / 60
                    if prev is not None else np.nan)
    parse_pass = expected_dt == row.timestamp.to_pydatetime() and all(
        np.isclose(float(value), row[name], rtol=1e-12, atol=1e-12)
        for value, name in zip(numbers, NUMERIC))
    range_pass = bool(np.isclose(float(expected_range), row.bar_range, rtol=1e-12, atol=1e-12))
    gap_pass = bool(np.isclose(expected_gap, row.gap_minutes, equal_nan=True))
    return dict(**record, parsed_timestamp=row.timestamp,
                **{f"parsed_{name}": row[name] for name in NUMERIC},
                previous_raw_line_number=int(prev.name) if prev is not None else "",
                previous_timestamp=prev.timestamp if prev is not None else "",
                previous_close=prev.close if prev is not None else np.nan,
                expected_range_decimal=str(expected_range), derived_bar_range=row.bar_range,
                expected_gap_minutes=expected_gap, derived_gap_minutes=row.gap_minutes,
                derived_simple_return_pct=row.simple_return_pct,
                **{flag: bool(row[flag]) for flag in FLAGS},
                parsed_values_pass=parse_pass, range_pass=range_pass, gap_pass=gap_pass,
                check_pass=parse_pass and range_pass and gap_pass)


def verify_manual_sources(checks: pd.DataFrame) -> pd.DataFrame:
    """Re-read selected raw physical lines and verify derived values independently."""
    checks = checks.copy()
    for path, group in checks.groupby("raw_path", sort=False):
        targets = set(group.raw_line_number.astype(int))
        targets.update(int(v) for v in group.previous_raw_line_number if pd.notna(v) and str(v) != "")
        found = {}
        with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
            for number, line in enumerate(stream, 1):
                if number in targets:
                    found[number] = line.rstrip("\r\n")
                if number >= max(targets):
                    break
        for index, check in group.iterrows():
            actual = found[int(check.raw_line_number)]
            current = actual.split(",")
            previous = found.get(int(check.previous_raw_line_number)) if pd.notna(check.previous_raw_line_number) and str(check.previous_raw_line_number) != "" else None
            checks.loc[index, "raw_source_match"] = actual == check.raw_text
            if previous is not None:
                prev = previous.split(",")
                checks.loc[index, "previous_raw_text"] = previous
                expected_gap = (datetime.strptime(current[0], TIMESTAMP_FORMAT) - datetime.strptime(prev[0], TIMESTAMP_FORMAT)).total_seconds() / 60
                checks.loc[index, "expected_gap_minutes"] = expected_gap
                checks.loc[index, "gap_pass"] = np.isclose(expected_gap, check.derived_gap_minutes)
                if pd.notna(check.derived_simple_return_pct):
                    expected_return = 100 * (Decimal(current[4]) / Decimal(prev[4]) - 1)
                    checks.loc[index, "expected_return_pct_decimal"] = str(expected_return)
                    checks.loc[index, "return_pass"] = bool(np.isclose(float(expected_return), check.derived_simple_return_pct, rtol=1e-10, atol=1e-10))
                else:
                    checks.loc[index, "return_pass"] = True
                    checks.loc[index, "expected_return_pct_decimal"] = "undefined under documented pair mask"
            else:
                checks.loc[index, "return_pass"] = pd.isna(check.derived_simple_return_pct)
            checks.loc[index, "check_pass"] = all(bool(checks.loc[index, col]) for col in
                ["parsed_values_pass", "range_pass", "gap_pass", "raw_source_match", "return_pass"])
    return checks


def validate_parser() -> None:
    """Small regression checks of failure paths absent from clean pilot files."""
    lines = [
        "2024-11-04 09:30:00,10,11,9,10,0\n",
        "2024-11-04 09:30:00,10,11,9,10,1\n",
        "2024-11-04 09:32:00,10,9,11,10,2\n",
        "2024-11-04 09:33:00,10,11,9,,x\n",
        "bad,10,11,9,10,1\n",
        "2026-01-01 00:00:00,10,11,9,10,1\n",
        "2024-11-04 09:35:00,10,11,9,10\n",
        "2024-11-04 09:36:00,10,11,9,10,inf\n"]
    _, p = parse_chunk(lines, 99)
    assert list(p.index) == list(range(99, 107))
    assert p.loc[99, "zero_volume"] and p.loc[101, "invalid_ohlc"]
    assert p.loc[102, "missing_value"] and p.loc[102, "non_numeric"]
    assert pd.isna(p.loc[103, "timestamp"])
    assert p.loc[104, "timestamp"] >= END
    assert p.loc[105, "malformed_columns"] and p.loc[106, "non_finite"]
    d = p.loc[[99, 100, 101]].copy()
    d["duplicate_timestamp"] = d.timestamp.duplicated(keep=False)
    d = add_derivatives(d)
    assert d.gap_minutes.iloc[1:].tolist() == [0, 2]
    assert d.simple_return_pct.isna().all() and len(d) == 3


def make_figures(daily: pd.DataFrame, hourly: pd.DataFrame, out: Path):
    os.environ.setdefault("MPLCONFIGDIR", str(out / "diagnostics" / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = "Times New Roman" if "Times New Roman" in available else "DejaVu Serif"
    plt.rcParams.update({"font.family": font, "font.size": 12, "axes.spines.top": False, "axes.spines.right": False})
    assets = daily.asset.unique()
    fig, axes = plt.subplots(4, 2, figsize=(14, 12), sharex=True)
    for ax, asset in zip(axes.flat, assets):
        part = daily.loc[daily.asset.eq(asset) & daily.window.eq("project")]
        ax.scatter(pd.to_datetime(part.date), part.observed_rows, s=1.2, color="#2166ac", linewidths=0)
        ax.set_xlim(START, END - pd.Timedelta(days=1))
        ax.set_xticks(pd.to_datetime([f"{year}-01-01" for year in range(2015, 2026, 2)]))
        ax.set_ylim(bottom=0)
        ax.set_title(asset, loc="left", weight="bold")
        ax.set_ylabel("Observed rows / calendar day")
        ax.grid(alpha=.2)
    fig.suptitle("Diagnostic: observed intraday rows by raw calendar date | 2015-2025", fontsize=16)
    fig.text(.05, .018, "All raw-clock hours; timezone unresolved. Zero-row dates shown; no minute bars filled.\nDuplicates retained. Separate futures contracts; no expected-session denominator.", fontsize=12)
    fig.tight_layout(rect=(0, .065, 1, .96))
    fig.savefig(out / "figures" / "bars_per_day_by_asset.png", dpi=300)
    plt.close(fig)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True)
    for ax, (asset_class, part) in zip(axes.flat, hourly.loc[hourly.window.eq("project")].groupby("asset_class", sort=False)):
        for asset, h in part.groupby("asset", sort=False):
            total = h.observed_rows.sum()
            ax.plot(h.hour_raw_clock, 100 * h.observed_rows / total if total else h.observed_rows,
                    marker=".", label=asset)
        ax.set_title(asset_class, loc="left", weight="bold")
        ax.set_xlabel("Hour of day in recorded clock (timezone unknown)")
        ax.set_ylabel("% of asset's observed rows")
        ax.set_xticks([0, 4, 8, 12, 16, 20, 23])
        ax.set_ylim(bottom=0)
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle("Hourly distribution of observed rows | 2015-2025", fontsize=16)
    fig.text(.05, .018, "Each asset normalized by its own observed rows, not expected session bars.\nUnfiltered hours; unequal coverage periods. Percentages describe activity, not coverage.", fontsize=12)
    fig.tight_layout(rect=(0, .075, 1, .95))
    fig.savefig(out / "figures" / "hourly_activity_by_asset_class.png", dpi=300)
    plt.close(fig)


def make_common_window_presentation(daily, quality, coverage, out):
    """Presentation-only aggregation of validated common-window diagnostics.

    duplicate_rows means all rows affected by duplicate timestamps, matching
    duplicate_timestamp_rows in data_quality_summary.csv. Daily statistics use
    observed dates only; zero-row calendar dates remain visible in the figure.
    """
    part = daily.loc[daily.window.eq("common")].copy()
    part["date"] = pd.to_datetime(part.date)
    assert part.date.between(COMMON_START, COMMON_END - pd.Timedelta(days=1)).all()
    assert not part.duplicated(["asset", "date"]).any()
    assert part.asset.nunique() == 8
    counts = part.loc[part.observed_rows.gt(0)].groupby(
        ["asset", "asset_class"], sort=False).observed_rows.agg(
            observed_dates="size", total_rows="sum",
            median_rows_per_observed_day="median",
            min_rows_per_observed_day="min",
            max_rows_per_observed_day="max").reset_index()
    q = quality.loc[quality.window.eq("common"),
        ["asset", "duplicate_timestamp_rows", "invalid_ohlc_rows", "zero_volume_rows"]]
    summary = counts.merge(q, on="asset", validate="one_to_one").rename(
        columns={"duplicate_timestamp_rows": "duplicate_rows"})
    summary["timezone_status"] = "unresolved"
    summary["session_status"] = "unresolved; all recorded hours retained"
    expected = coverage.loc[coverage.window.eq("common")].set_index("asset")
    assert set(summary.asset) == set(expected.index)
    for row in summary.itertuples():
        assert row.total_rows == expected.loc[row.asset, "observed_rows"]
        assert row.observed_dates == expected.loc[row.asset, "observed_calendar_days"]
    summary.to_csv(out / "tables" / "common_window_presentation_summary.csv", index=False)

    os.environ.setdefault("MPLCONFIGDIR", str(out / "diagnostics" / ".mplconfig"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    names = {f.name for f in font_manager.fontManager.ttflist}
    font = "Times New Roman" if "Times New Roman" in names else "DejaVu Serif"
    classes = [("stocks", "Stocks", "#0072B2"), ("etfs", "ETFs", "#009E73"),
               ("futures", "Futures - individual contracts", "#D55E00"),
               ("cryptos", "Crypto", "#7B3294")]
    dates = pd.date_range(COMMON_START, COMMON_END - pd.Timedelta(days=1))
    with plt.rc_context({"font.family": font, "font.size": 12,
                         "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(2, 2, figsize=(14, 8), sharex=True, sharey=True)
        for ax, (asset_class, label, color) in zip(axes.flat, classes):
            subset = part.loc[part.asset_class.eq(asset_class)]
            for i, (asset, values) in enumerate(subset.groupby("asset", sort=False)):
                values = values.sort_values("date")
                assert list(values.date) == list(dates)
                ax.plot(values.date, values.observed_rows, color=color,
                        linestyle="-" if i == 0 else "--",
                        marker="o" if i == 0 else "x", markersize=5,
                        markerfacecolor="white", linewidth=1.8, label=asset)
            ax.set_title(label, loc="left", color=color, weight="bold", fontsize=15)
            ax.set_xticks(dates, [date.strftime("%d") for date in dates])
            ax.tick_params(axis="x", labelbottom=True)
            ax.set_ylim(0, max(1500, part.observed_rows.max() * 1.06))
            ax.set_yticks([0, 500, 1000, 1500])
            ax.set_xlabel("November 2024 - raw calendar date")
            ax.set_ylabel("Observed raw bars / date")
            ax.grid(axis="y", alpha=.22)
            ax.legend(loc="lower right" if asset_class in {"futures", "cryptos"} else "upper left", ncol=2, frameon=True, fontsize=11)
        fig.suptitle("Observed raw bars per calendar date | 2024-11-04 to 2024-11-15",
                     fontsize=20, weight="bold", y=.98)
        fig.text(.05, .035,
                 "All 8 pilot assets; timezone/session conventions unresolved. No expected-session denominator.\n"
                 "No missing minutes filled. Zero-row dates show no recorded bars; futures contracts remain separate.",
                 fontsize=12)
        fig.tight_layout(rect=(.015, .10, .995, .945))
        fig.savefig(out / "figures" / "common_window_bars_per_day.png", dpi=300)
        plt.close(fig)
    print(f"Common-window presentation: {len(summary)} assets, {summary.total_rows.sum():,} rows; font: {font}")
    return summary


def run_pipeline(project: Path = PROJECT) -> dict[str, pd.DataFrame]:
    validate_parser()
    out = project / "outputs"
    for folder in ["tables", "diagnostics", "figures"]:
        (out / folder).mkdir(parents=True, exist_ok=True)
    accepted = pd.read_csv(out / "diagnostics" / "pilot_schema.csv")
    if set(accepted.file) != set(PILOT_FILES):
        raise ValueError("Accepted pilot schema does not match the requested universe")
    if not (accepted.number_of_columns.eq(6) & accepted.has_header.eq("no")).all():
        raise ValueError("Accepted schema differs from the six-column headerless parser")
    root = intraday_root()
    collections = {key: [] for key in ["coverage", "quality", "bars", "gaps", "descriptives", "daily", "hourly", "clock", "audit", "manual", "futures"]}
    failures = []
    for relative in PILOT_FILES:
        asset_class = relative.split("/")[0]
        asset = Path(relative).stem.split("_full")[0].removesuffix("_1min")
        print(f"Scanning {asset}: {relative}", flush=True)
        try:
            data, manual, audit = read_asset(root / relative, asset, out)
            data = add_derivatives(data)
            collections["audit"].append(dict(asset=asset, asset_class=asset_class, file=relative, **audit))
            flags = data.loc[data[FLAGS].any(axis=1), ["timestamp"] + NUMERIC + FLAGS]
            flags.to_csv(out / "diagnostics" / f"{asset}_flagged_rows.csv", index=True)
            for record in manual:
                collections["manual"].append(manual_check(data, record))
            for window in WINDOWS:
                result = window_tables(data, asset, asset_class, window)
                for key, value in zip(["coverage", "quality", "bars", "gaps", "descriptives", "daily", "hourly", "clock"], result):
                    if isinstance(value, list):
                        collections[key].extend(value)
                    else:
                        collections[key].append(value)
            if asset_class == "futures":
                observed = data.groupby("date").size()
                first_year = observed.index.year.min()
                early = observed.loc[observed.index.year == first_year]
                late = observed.tail(30)
                collections["futures"].append(dict(asset=asset, first_observed_year=int(first_year),
                    first_year_observed_days=len(early), first_year_median_rows=early.median(),
                    first_year_days_le10=int(early.le(10).sum()),
                    last30_observed_days_median_rows=late.median(),
                    all_observed_days_le10=int(observed.le(10).sum()),
                    interpretation="Sparse early observations warrant review; active-contract onset NOT inferred",
                    threshold_note="<=10 observed rows/day is a descriptive review flag, not an exclusion/session rule"))
            print(f"  {audit['raw_rows_scanned']:,} raw rows; {len(data):,} project rows; {int(data.duplicate_timestamp.sum()):,} duplicate-affected rows", flush=True)
            del data, flags
        except Exception as exc:
            failures.append(dict(file=relative, error_type=type(exc).__name__, error=str(exc)))
            print(f"  FAILED: {exc}", flush=True)
    pd.DataFrame(failures, columns=["file", "error_type", "error"]).to_csv(out / "diagnostics" / "failures.csv", index=False)
    tables = {}
    for key, items in collections.items():
        tables[key] = pd.concat(items, ignore_index=True) if key in {"daily", "hourly"} and items else pd.DataFrame(items)
    if tables["coverage"].empty:
        raise RuntimeError("No files successfully processed; see failures.csv")
    exports = {
        "pilot_coverage": tables["coverage"].query("window == 'project'"),
        "common_window_coverage": tables["coverage"].query("window == 'common'"),
        "bars_per_day_summary": tables["bars"], "data_quality_summary": tables["quality"],
        "gap_summary": tables["gaps"], "descriptive_summary": tables["descriptives"],
        "bars_per_calendar_day": tables["daily"], "hourly_activity": tables["hourly"],
        "raw_clock_coverage": tables["clock"], "futures_sparse_review": tables["futures"],
    }
    for name, table in exports.items():
        table.to_csv(out / "tables" / f"{name}.csv", index=False)
    tables["audit"].to_csv(out / "diagnostics" / "file_scan_audit.csv", index=False)
    tables["manual"] = verify_manual_sources(tables["manual"])
    tables["manual"].to_csv(out / "diagnostics" / "manual_checks.csv", index=False)
    make_figures(tables["daily"], tables["hourly"], out)
    make_common_window_presentation(tables["daily"], tables["quality"], tables["coverage"], out)
    manifest = dict(project_start=str(START.date()), project_end="2025-12-31",
        common_start=str(COMMON_START.date()), common_end="2024-11-15",
        source_root=str(root), files=list(PILOT_FILES), python=platform.python_version(),
        pandas=pd.__version__, numpy=np.__version__, inserted_minute_bars=0,
        timestamp_timezone="unresolved; naive recorded wall-clock timestamps",
        session="none imposed", duplicate_policy="retained and flagged",
        gap_policy="stable chronological adjacent records, including overnight/weekend gaps and duplicate zero gaps",
        return_policy="100*(close/previous close-1), within each window; positive finite consistent OHLC pairs, strictly increasing timestamps, no duplicate-affected pair; no forward filling",
        range_policy="finite, positive, internally consistent OHLC rows; diagnostic validity mask only",
        price_volume_policy="finite raw close/volume values, including flagged values; native units unverified",
        date_exclusions="before 2015 and after 2025 counted only in file_scan_audit; no 2026 in summaries",
        flags="<=10 rows on an observed day is a sparse-review marker, not an active-contract or completeness rule",
        failures=failures)
    (out / "diagnostics" / "run_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    validate_outputs(tables)
    summary = (f"Checkpoint: {len(tables['audit'])}/8 files scanned; "
               f"{int(exports['pilot_coverage'].observed_rows.sum()):,} project rows; "
               f"{int(exports['common_window_coverage'].observed_rows.sum()):,} common-window rows. "
               f"{len(tables['manual'])} traceable checks passed. No minute bars filled; no estimators computed.")
    (out / "diagnostics" / "checkpoint_summary.txt").write_text(summary, encoding="utf-8")
    print(summary, flush=True)
    if failures:
        raise RuntimeError("Some files failed; see outputs/diagnostics/failures.csv")
    return tables


def validate_outputs(tables):
    audit, coverage, daily = tables["audit"], tables["coverage"], tables["daily"]
    assert (audit.raw_rows_scanned == audit[["malformed_column_rows", "unparseable_timestamp_rows", "rows_before_2015", "rows_after_2025", "project_rows"]].sum(axis=1)).all()
    assert coverage.inserted_minute_bars.eq(0).all()
    assert pd.to_datetime(daily.date).lt(END).all()
    for _, row in coverage.iterrows():
        days = daily.loc[daily.asset.eq(row.asset) & daily.window.eq(row.window)]
        assert int(days.observed_rows.sum()) == row.observed_rows
        hours = tables["hourly"].loc[lambda x: x.asset.eq(row.asset) & x.window.eq(row.window)]
        assert int(hours.observed_rows.sum()) == row.observed_rows
        lo, hi = WINDOWS[row.window]
        if row.observed_rows:
            assert lo <= row.first_timestamp <= row.last_timestamp < hi
    if len(audit) == 8:
        assert len(tables["manual"]) == 10
        assert tables["manual"].check_pass.all()


if __name__ == "__main__":
    run_pipeline()

