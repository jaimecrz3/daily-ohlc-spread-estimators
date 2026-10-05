"""Build the MMF checkpoint deck from the supplied template and accepted outputs.

Run: python -B src/build_presentation.py
No raw intraday reads, new empirical analysis, or estimator calculations.
Requires python-pptx, pandas, openpyxl, and Pillow.
"""
from pathlib import Path
from datetime import date
import hashlib
import json
from zipfile import ZipFile
from io import BytesIO

import pandas as pd
import openpyxl
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR

ROOT = Path(__file__).resolve().parents[1]
NAVY, TEAL, BLUE, INK, GRAY = "102A43", "087E8B", "246BCE", "172B3A", "5F6F7A"
PALE, WHITE = "F2F5F7", "FFFFFF"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_text(shape, text, size=20, color=INK, bold=False):
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(.02)
    tf.margin_top = tf.margin_bottom = Inches(.025)
    for i, line in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.space_after = Pt(0 if size <= 13 else 6)
        p.line_spacing = 1.0
        p.font.name = "Arial"
        p.font.size = Pt(size)
        p.font.color.rgb = RGBColor.from_string(color)
        p.font.bold = bold
    return shape


def text(slide, x, y, w, h, value, size=20, color=INK, bold=False):
    return write_text(slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)),
                      value, size, color, bold)


def prepare(slide, number, section, title, subtitle):
    """Keep template header/footer rules, side accent, background and masters."""
    for shape in list(slide.shapes):
        if Inches(1.6) <= shape.top < Inches(7.0):
            shape._element.getparent().remove(shape._element)
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue
        y = shape.top / 914400
        if .25 < y < .5:
            write_text(shape, section.upper(), 11.25, TEAL, True)
        elif .5 <= y < 1.0:
            write_text(shape, title, 28, NAVY, True)
        elif 1.0 <= y < 1.6:
            write_text(shape, subtitle, 15, GRAY)
        elif y > 7 and shape.left / 914400 > 11:
            write_text(shape, f"{number:02}", 11.25, NAVY)
    # Old template instructional speaker notes are replaced with project lineage.
    slide.notes_slide.notes_text_frame.text = ""


def box(slide, x, y, w, h, heading, lines, accent=TEAL, size=20):
    shape = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(PALE)
    shape.line.fill.background()
    text(slide, x+.18, y+.13, w-.36, .4, heading, 15, accent, True)
    text(slide, x+.18, y+.7, w-.36, h-.85, "\n".join(lines), size)


def table(slide, headers, rows, widths, x=.7, y=1.9, h=3.9, size=17):
    shape = slide.shapes.add_table(len(rows)+1, len(headers), Inches(x), Inches(y),
                                   Inches(sum(widths)), Inches(h))
    t = shape.table
    for col, width in zip(t.columns, widths):
        col.width = Inches(width)
    for r, values in enumerate([headers]+rows):
        for c, value in enumerate(values):
            cell = t.cell(r,c)
            cell.margin_left = cell.margin_right = Inches(.10)
            cell.margin_top = cell.margin_bottom = Inches(.07)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor.from_string(NAVY if r == 0 else (PALE if r % 2 else WHITE))
            write_text(cell, value, size, WHITE if r == 0 else INK, r == 0)
    return shape


def takeaway(slide, value, status="DIAGNOSTIC", size=19):
    text(slide, .7, 6.3, 1.5, .5, status, 12, TEAL, True)
    text(slide, 2.2, 6.22, 10.35, .68, value, size, NAVY)


def picture(slide, path, x=.65, y=1.72, w=12.05, h=4.45):
    with Image.open(path) as im:
        iw, ih = im.size
    scale = min(w/iw, h/ih)
    pw, ph = iw*scale, ih*scale
    slide.shapes.add_picture(str(path), Inches(x+(w-pw)/2), Inches(y+(h-ph)/2),
                             width=Inches(pw), height=Inches(ph))


def build_presentation(project=ROOT, presenter=None, presentation_date=None):
    project = Path(project)
    template = project / "presentation/MMF_2026_Project_Progress_Update_Template.pptx"
    if not template.is_file():
        raise FileNotFoundError("Supplied template is required; no from-scratch fallback.")
    prs = Presentation(template)
    if len(prs.slides) != 13:
        raise ValueError("Expected the inspected 13-slide MMF template")
    original_hash = sha(template)
    used = [template]
    def read(folder, name):
        path = project / "outputs" / folder / (name+".csv")
        used.append(path)
        return pd.read_csv(path)
    coverage = read("tables","pilot_coverage")
    common = read("tables","common_window_presentation_summary")
    quality = read("tables","data_quality_summary").query("window == 'project'").set_index("asset")
    audit = read("diagnostics","file_scan_audit")
    manual = read("diagnostics","manual_checks")
    schema = read("diagnostics","pilot_schema")
    assert len(common) == 8 and manual.check_pass.all()
    assert (schema.number_of_columns.eq(6) & schema.has_header.eq("no")).all()
    zero_cols = ["duplicate_timestamp_rows","invalid_ohlc_rows","missing_value_rows","non_numeric_rows"]
    assert quality[zero_cols].sum().eq(0).all(), "Quality changed: revise validation text"
    raw = project / "data/raw_bloomberg/bloomberg_pilot_AAPL_SPY_20241104_20241115.xlsx"
    static = raw.with_name(raw.stem+"_STATIC.xlsx")
    hash_file = static.with_suffix(".sha256.txt")
    used += [raw, static, hash_file]
    workbook = openpyxl.load_workbook(static, read_only=True, data_only=True)
    entries = list(workbook["source log"].iter_rows(values_only=True))
    log = pd.DataFrame(entries[1:], columns=entries[0]).dropna(how="all")
    workbook.close()
    assert hash_file.read_text().split()[0] == sha(static)
    assert set(log.file_hash) == {sha(raw)}
    bloom_dates = sorted(set(log.retrieval_date.astype(str)))
    slides = list(prs.slides)
    s = slides[0]
    byid = {shape.shape_id:shape for shape in s.shapes}
    write_text(byid[19], "Comparative Analysis of Bid-Ask\nSpread Estimators Across Asset Classes", 34, WHITE, True)
    byid[19].height = Inches(1.35)
    write_text(byid[20], "How do daily-OHLC spread estimates compare with an intraday\nrealized-cost benchmark across asset classes and liquidity tiers?", 21, "D9E4EC")
    byid[20].top = Inches(3.25)
    byid[20].height = Inches(.95)
    write_text(byid[22], presenter or "MMF 1941 | First progress checkpoint", 20, WHITE)
    byid[22].width = Inches(10)
    write_text(byid[23], "Project 1 | Proposal A04-03 | 2015-2025 asset-day framework", 17, "D9E4EC")
    byid[23].width = Inches(11)
    write_text(byid[24], presentation_date or "Data validation and design readiness", 16, "A9DADD")
    byid[24].width = Inches(10)
    write_text(byid[25], "Progress update | Descriptive diagnostics; estimator comparison remains planned", 12, "A9BBC9")
    byid[25].width = Inches(11.5)
    s.notes_slide.notes_text_frame.text = "Source: Proposal A04-03 and accepted exploratory notebook. Benchmark remains undefined; this is not an estimator-results deck."

    s=slides[1]
    prepare(s,2,"Research design","Compare spread estimates after the design is frozen","PLANNED METHODOLOGY | Asset-day observations, 2015-2025")
    box(s,.7,1.9,5.8,3.95,"EVENTUAL COMPARISON",[
        "Corwin-Schultz (CS)",
        "Abdi-Ranaldo (AR)",
        "EDGE",
        "Against an intraday realized-cost benchmark"],size=21)
    box(s,6.75,1.9,5.85,3.95,"DESIGN DIMENSIONS",[
        "Stocks, ETFs, futures, crypto; FX unresolved",
        "Liquidity-stratified final universe",
        "Cross-class and within-class diagnostics",
        "Exact benchmark and session rules: OPEN"],accent=BLUE,size=20)
    takeaway(s,"Choose the benchmark for its economic meaning, not estimator performance.","OPEN DECISION")

    s=slides[2]
    prepare(s,3,"Data requirements","Separate local intraday inputs from Bloomberg daily data","REQUIREMENTS | Identifiers, timing and units must connect the sources")
    table(s,["Input","Source / frequency","Role / current boundary"],[
        ["Daily OHLC + volume","Daily/EOD source; aggregation TBD","Inputs for eventual daily estimators"],
        ["Intraday OHLCV","Local RiskLab / First Rate Data","Benchmark feasibility + diagnostics"],
        ["Daily bid / ask","Bloomberg equity / ETF pilot","PX_BID / PX_ASK; not intraday quotes"],
        ["Identifiers + metadata","Provider records + Bloomberg BDP","IDs, currency, adjustments, timezone"]
    ],[2.6,4.2,5.1],h=3.65,size=18)
    takeaway(s,"Bloomberg is daily/EOD/reference only; all intraday data stay local.","SOURCE RULE")

    s=slides[3]
    prepare(s,4,"Local data inventory","Four asset classes available; FX remains unresolved","FACTS | Local RiskLab / First Rate intraday archive")
    table(s,["Asset class","Availability","Pilot / limitation"],[
        ["Stocks","AVAILABLE","AAPL, GME"],
        ["ETFs","AVAILABLE","SPY, IWM"],
        ["Futures","AVAILABLE; methodology review","ES_Z24, CL_Z24: individual contracts"],
        ["Crypto","AVAILABLE","BTC, ETH"],
        ["FX","METADATA REVIEW","Expected by metadata; physically unavailable"]
    ],[2.0,4.0,5.9],h=3.95,size=18)
    takeaway(s,"No FX substitute. Futures files do not form a continuous history.","LIMITATION")
    s.notes_slide.notes_text_frame.text = "Inputs resolve via RISKLAB_DATA_ROOT/intraday_data. Availability refers to the accepted pilot inventory, not universal 2015-2025 coverage."

    s=slides[4]
    prepare(s,5,"Bloomberg acquisition","AAPL + SPY daily/reference pilot is preserved","PILOT | 2024-11-04 to 2024-11-15; BDP / BDH")
    box(s,.7,1.9,5.8,3.95,"ACQUISITION SCOPE",[
        "BDP: names, FIGI, ISIN, CUSIP,",
        "ticker/exchange and currency",
        "BDH daily: PX_OPEN, PX_HIGH, PX_LOW,",
        "PX_LAST, PX_VOLUME, PX_BID, PX_ASK"],size=19)
    box(s,6.75,1.9,5.85,3.95,"EVIDENCE / NEXT PULL",[
        "Raw workbook + values-only snapshot",
        f"{len(log)} source-log entries; SHA-256 verified",
        "Retrieval dates: "+ " / ".join(bloom_dates),
        "Full 2015-2025 pull deferred until",
        "final equity/ETF universe is frozen"],accent=BLUE,size=19)
    takeaway(s,"Daily bid/ask fields do not establish the intraday benchmark.","BOUNDARY")
    s.notes_slide.notes_text_frame.text = "Source: static workbook, source log and Acquisition evidence sheets. Read only metadata, not new empirical observations. Logged timezone is Bloomberg daily metadata, not evidence for local intraday timezone. Default BDH adjustments remain unverified."

    s=slides[5]
    prepare(s,6,"Intraday pilot validation","The local pilot is parsed, checked and traceable","FACTS | AAPL, GME, SPY, IWM, ES_Z24, CL_Z24, BTC, ETH")
    table(s,["Validation item","Accepted diagnostic"],[
        ["Raw schema","Six columns; headerless timestamp + OHLCV"],
        ["Project-window rows",f"{int(coverage.observed_rows.sum()):,} | 2015-2025"],
        ["Post-2025 rows excluded",f"{int(audit.rows_after_2025.sum()):,} | audit only"],
        ["Duplicates / invalid OHLC / missing / non-numeric","0 in project-window diagnostics"],
        ["Zero-volume rows retained",f"AAPL: {int(quality.loc['AAPL','zero_volume_rows']):,} | GME: {int(quality.loc['GME','zero_volume_rows']):,}"],
        ["Manual raw-row checks",f"{int(manual.check_pass.sum())}/{len(manual)} passed"]
    ],[6.0,5.9],h=4.0,size=18)
    takeaway(s,"Parsing checks passed; session, timezone and volume-unit metadata remain open.","SCOPE")
    s.notes_slide.notes_text_frame.text = "Sources: pilot_schema.csv; pilot_coverage.csv; file_scan_audit.csv; data_quality_summary.csv; manual_checks.csv. Flags and validity definitions are those of the accepted notebook."

    s=slides[6]
    prepare(s,7,"Common-window diagnostic","Observed raw bars differ across asset classes","DIAGNOSTIC | 2024-11-04 to 2024-11-15; no expected-session denominator")
    common_fig=project/"outputs/figures/common_window_bars_per_day.png"
    used.append(common_fig)
    picture(s,common_fig)
    takeaway(s,"Observed bar structure differs materially across asset classes before any session convention is imposed.",size=18)
    s.notes_slide.notes_text_frame.text = "Source: common_window_bars_per_day.png, generated by notebook from bars_per_calendar_day.csv. Counts retain all recorded hours; no minute filling. Calendar-date zeros are not missing-minute estimates."

    s=slides[7]
    prepare(s,8,"Intraday clock diagnostic","Resolve clock interpretation before aggregation","DIAGNOSTIC | Recorded-clock activity; percentages describe activity, not coverage")
    hour_fig=project/"outputs/figures/hourly_activity_by_asset_class.png"
    used.append(hour_fig)
    picture(s,hour_fig,h=4.5)
    takeaway(s,"Recorded-clock patterns differ across assets/classes; resolve timezone and session interpretation before benchmark aggregation.",size=17)
    s.notes_slide.notes_text_frame.text = "Source: hourly_activity_by_asset_class.png, generated from hourly_activity.csv. Each asset normalized by its own observed rows. Different date spans and unlocalized clocks limit interpretation."

    s=slides[8]
    prepare(s,9,"Preparation and reproducibility","One reproducible path from raw data to this deck","IMPLEMENTED | Raw data remain read-only")
    box(s,.7,1.85,5.8,3.8,"DATA HANDLING",[
        "RISKLAB_DATA_ROOT / intraday_data",
        "Chunked full-file scanner",
        "No forward filling or inserted minute bars",
        "Duplicates retained and flagged",
        "Explicit date exclusions and quality flags"],size=20)
    box(s,6.75,1.85,5.85,3.8,"REPRODUCIBILITY",[
        "CSV tables + 300-DPI figures from code",
        "Source log, hashes and raw-row checks",
        "Notebook -> CSV/PNG -> template -> deck",
        "Package versions + run manifest retained",
        "Numeric outputs reconcile unchanged"],accent=BLUE,size=20)
    takeaway(s,"The analytic asset-day panel is a later step; this checkpoint produces diagnostics.","STATUS")

    s=slides[9]
    prepare(s,10,"Preliminary implication","Session/calendar rules must precede the benchmark","DESCRIPTIVE IMPLICATION | Not an estimator result")
    rows=[]
    for r in common.itertuples():
        rows.append([r.asset,str(r.observed_dates),f"{r.median_rows_per_observed_day:,.1f}",
                     f"{r.min_rows_per_observed_day:,} - {r.max_rows_per_observed_day:,}"])
    table(s,["Asset","Observed dates","Median rows / observed day","Min - max"],rows,
          [1.8,2.0,3.45,2.45],x=.7,y=1.8,h=4.3,size=16)
    text(s,10.7,1.95,1.95,4.1,
         "BTC / ETH\n1,440 per raw date\n\nStocks / ETFs\nFewer bars; zero-row dates\n\nFutures\nDistinct calendars",16)
    takeaway(s,"Freeze class-specific session/calendar rules before constructing a comparable intraday benchmark.",size=18)
    s.notes_slide.notes_text_frame.text = "Source: common_window_presentation_summary.csv. Dates are raw calendar dates. Equity/ETF zero-row dates coincide with non-trading weekend dates, but session conventions are not frozen. Futures are individual contracts. No expected-session coverage percentage."

    s=slides[10]
    prepare(s,11,"Open decisions and next steps","Freeze the design before estimating spreads","NEXT STEPS | Sequence, not completed methodology")
    box(s,.7,1.9,3.85,3.95,"1. METADATA",[
        "Confirm timezone / bar labels",
        "Freeze class-specific sessions",
        "Resolve FX availability",
        "Review adjustments and units"],size=20)
    box(s,4.75,1.9,3.85,3.95,"2. DESIGN",[
        "Define exact intraday benchmark",
        "Freeze negative / undefined treatment",
        "Choose liquidity-stratified universe",
        "Set futures contract policy"],accent=BLUE,size=20)
    box(s,8.8,1.9,3.8,3.95,"3. EXECUTION",[
        "Full Bloomberg daily pull",
        "Build asset-day framework",
        "Only after design freeze:",
        "estimate CS / AR / EDGE"],size=20)
    takeaway(s,"Feedback sought: benchmark feasibility and class-specific session conventions.","DISCUSSION")

    s=slides[11]
    prepare(s,12,"Appendix - sources and lineage","Every displayed result maps to a saved artifact","LINEAGE | Sources, parser, diagnostics and presentation")
    table(s,["Source / stage","Retained evidence","Role / restriction"],[
        ["First Rate via RiskLab","intraday_data; source paths + scan audit","Local intraday OHLCV only"],
        ["Bloomberg","Raw + static workbook; source log + hashes","Daily/EOD/reference only"],
        ["Parser + diagnostics","data_io.py; eda_diagnostics.py; CSV/PNG","Accepted EDA; no estimators"],
        ["Presentation","Supplied MMF template + build_presentation.py","Reads accepted outputs; no new analysis"]
    ],[2.8,5.3,3.8],h=3.3,size=17)
    text(s,.75,5.5,11.85,.6,"Raw -> parser -> diagnostics -> analytic output (planned) -> presentation",20,NAVY,True)
    takeaway(s,"Current deck uses diagnostics directly; the analytic asset-day output is still planned.","STATUS")
    s.notes_slide.notes_text_frame.text = "Source paths and SHA-256 values for deck dependencies are saved in outputs/diagnostics/presentation_build.json. Template master/layout/theme retained."

    s=slides[12]
    prepare(s,13,"Appendix - acquisition and validation","Bloomberg lineage and raw-row evidence","AUDIT EVIDENCE | Source-log metadata; accepted manual checks")
    box(s,.7,1.8,6.1,4.25,"BLOOMBERG SOURCE LOG",[
        "AAPL US Equity + SPY US Equity",
        "BDP reference / BDH daily OHLCV + bid/ask",
        f"{len(log)} entries | retrieval: "+ " / ".join(bloom_dates),
        "Raw + static SHA-256: verified",
        "Logged filename has '(1)'; local name differs.",
        "Raw hash matches; adjustment defaults unverified."],size=17)
    selected=manual.groupby("asset",sort=False).head(1)
    selected=selected[selected.asset.isin(["AAPL","SPY","ES_Z24","BTC"])]
    table(s,["Asset","Raw line","Check"],[
        [r.asset,f"{r.raw_line_number:,}","PASS" if r.check_pass else "FAIL"] for r in selected.itertuples()
    ],[1.65,2.25,1.35],x=7.0,y=2.35,h=2.8,size=17)
    text(s,7.0,1.87,5.2,.4,f"MANUAL VALIDATION: {int(manual.check_pass.sum())}/{len(manual)}",16,TEAL,True)
    text(s,7.0,5.35,5.25,.65,"Raw path / line / text + parsed values, range, gap and return checks retained.",17)
    takeaway(s,"Bloomberg daily metadata do not resolve the local intraday timezone.","LIMITATION")
    s.notes_slide.notes_text_frame.text = (
        "Bloomberg raw SHA-256: "+sha(raw)+"\nStatic SHA-256: "+sha(static)+
        "\nSource log filename: "+str(log.file_name.iloc[0])+
        "\nActual local raw path: "+str(raw.relative_to(project))+
        "\nRaw content hash agrees despite filename suffix difference. "
        "See manual_checks.csv for all 10 examples and full raw-row text.")
    output=project/"presentation/MMF1941_Project1_Progress_Update.pptx"
    prs.save(output)
    # python-pptx rewrites XML declarations; retain immutable template parts verbatim.
    buffer = BytesIO()
    with ZipFile(template) as original, ZipFile(output) as generated, ZipFile(buffer, "w") as archive:
        for entry in generated.infolist():
            preserve = entry.filename.startswith(("ppt/theme/", "ppt/slideMasters/", "ppt/slideLayouts/"))
            archive.writestr(entry, original.read(entry.filename) if preserve else generated.read(entry.filename))
    output.write_bytes(buffer.getvalue())
    assert sha(template)==original_hash
    # Verify retained theme/master/layout payloads and eliminate template prompts.
    with ZipFile(template) as a, ZipFile(output) as b:
        preserved=[name for name in a.namelist() if name.startswith(("ppt/theme/","ppt/slideMasters/","ppt/slideLayouts/")) and not name.endswith("/")]
        assert all(a.read(name)==b.read(name) for name in preserved)
    check=Presentation(output)
    for slide in check.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                assert "[Project" not in shape.text and "ILLUSTRATIVE" not in shape.text
            assert shape.left >= 0 and shape.top >= 0
            assert shape.left+shape.width <= prs.slide_width+Inches(.03)
            assert shape.top+shape.height <= prs.slide_height+Inches(.03)
    report=dict(output=str(output.relative_to(project)),slides=len(check.slides),
        template_sha256=original_hash,template_unchanged=True,
        preserved="Slide size, backgrounds, masters, layouts, theme, header/footer rules and accent bars",
        adapted="Template prompts, illustrative charts and body tables replaced; 13 slides repurposed to requested sequence",
        numerical_source="Accepted notebook CSV/PNG outputs; no new empirical analysis",
        dependencies={str(p.relative_to(project)):sha(p) for p in used},
        bloomberg_source_log_rows=len(log),bloomberg_hashes_verified=True,
        bloomberg_filename_note="Logged '(1)' suffix absent locally; raw SHA-256 matches",
        manual_edits_recommended=["Add presenter name/date if desired","Review projector readability"],
        presenter=presenter,presentation_date=presentation_date)
    report_path=project/"outputs/diagnostics/presentation_build.json"
    report_path.write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(f"Generated {output} | {len(check.slides)} slides")
    return output


if __name__ == "__main__":
    build_presentation()

