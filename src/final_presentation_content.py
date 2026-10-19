"""Step23 presentation authoring from frozen tables; no analysis or deck generation."""
from pathlib import Path
import json
import re

import pandas as pd
import final_paper as frozen

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'presentation'
OUT=ROOT/'outputs/diagnostics/presentation_content'
AUDIT=[]
P='outputs/results/primary/'
R='outputs/results/robustness/'
M='outputs/results/error_model/'
T='outputs/tables/'
TIMES=[20,65,85,70,85,90,70,70,70,35]
TITLES=['Title','Research question','Data and design','How the horse race works','EDGE performs best overall','There is no universal estimator ranking','Hypotheses: what survived?','Roll availability is the main sample bottleneck','The overall conclusion survives the major sensitivity checks','Conclusion']
APPENDIX=['Estimator error is partly predictable','Exact selected universe','Estimator definitions and daily mappings','Class × liquidity accuracy','Failure and raw-negative rates','Roll quality sensitivities','Cross-fitted model details and placebo','Source and calendar limitations']


def row(slide,name,ref,display=None):
    kind=json.loads(ref['source_metric_or_row'])['kind']
    role='INHERITED_FIGURE' if name.startswith('figure') else 'SUPPORTING_EVIDENCE' if name.startswith('positive_low_CS_bias') else 'QUALITATIVE_OR_METHOD' if kind=='text' else 'DISPLAYED_VALUE'
    AUDIT.append(dict(slide=slide,claim_short_name=name,claim_text=name.replace('_',' '),
        audit_role=role,
        displayed_value=ref['display'] if display is None else display,
        **{k:ref[k] for k in ['numeric_value','unit','source_file','source_metric_or_row']},reconciliation_status='PASS'))
    return ref['display'] if display is None else display


def v(slide,name,file,filters,column,format='.2f',scale=1):
    return row(slide,name,frozen.value(file,filters,column,format,scale))


def q(slide,name,text,file,anchor):
    return row(slide,name,frozen.evidence(file,anchor),text)


def cell(slide,name,file,filters,column):
    ref=frozen.value(file,filters,column)
    ref['numeric_value']='';ref['unit']='categorical / methodology'
    locator=json.loads(ref['source_metric_or_row']);locator['kind']='categorical_csv';locator['expected']=ref['display']
    ref['source_metric_or_row']=json.dumps(locator,sort_keys=True)
    return row(slide,name,ref)


def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(map(str,r))+' |' for r in rows])


def figure(slide,name,meaning):
    path='outputs/figures/'+name+'.png'
    manifest=pd.read_csv(ROOT/'outputs/reproducibility/final_artifact_manifest.csv')
    saved=manifest.loc[manifest.relative_path.eq(path)].iloc[0]
    assert frozen.digest(ROOT/path)==saved.sha256
    ref=dict(display='Frozen '+name,numeric_value='',unit='unchanged figure',source_file=path,
        source_metric_or_row=json.dumps(dict(kind='artifact_sha256',sha256=saved.sha256,registry='outputs/reproducibility/final_artifact_manifest.csv')))
    row(slide,name,ref)
    # Preserve and audit inherited calendar/sample labels, including the figures'
    # design-window footers. Axis ticks and feature names are not new results.
    for cls in ['stocks','etfs','futures','crypto']:
        for metric in ['primary_start','primary_end']:
            v(slide,name+'_'+cls+'_'+metric,T+'table1_estimator_definitions_and_coverage.csv',dict(asset_class=cls,estimator='ROLL'),metric)
    if name.startswith(('figure1','figure2')):
        v(slide,name+'_common_N',P+'primary_accuracy_results.csv',dict(reporting_scope='overall',estimator='EDGE'),'N_asset_days',',.0f')
    return f'![{meaning}](../{path})\n\nVisual: reuse the existing full figure, unchanged; retain its notes, units and transformed-axis labels. '+meaning


def build():
    AUDIT.clear();slides={};appendix={}
    slides['1']='''# Which Daily OHLC Spread Estimator Tracks Realized Intraday Cost?
## A CS / AR / EDGE Horse-Race

Comparative evidence across stocks, ETFs, futures and crypto

Visual: minimal title treatment; no result table or implementation timeline.'''
    slides['2']='''**Which daily-OHLC spread estimator best matches a one-minute Roll benchmark, and where do the methods break down?**

Compare Corwin–Schultz, Abdi–Ranaldo and EDGE.

- EDGE expected to dominate accuracy.
- CS expected to be downward biased in thin markets.
- Rankings expected to be stable across asset classes.

**These are falsifiable hypotheses, not assumptions.**

Visual: question at top; three neutral hypothesis cards.'''
    q('2','original_hypotheses','Original hypotheses, retained before results','README.md','Original hypothesis (retained, including falsified components)')
    design=v('3','design_eligible',T+'appendix_data_lineage_attrition.csv',dict(asset_class='ALL',stage='design_eligible'),'N',',.0f')
    common=v('3','common_defined',P+'primary_accuracy_results.csv',dict(reporting_scope='overall',estimator='EDGE'),'N_asset_days',',.0f')
    counts=[]
    for cls in ['stocks','etfs','futures','crypto']:
        counts.append(v('3',cls+'_selected_assets',T+'appendix_data_lineage_attrition.csv',dict(asset_class=cls,stage='raw_selected_universe'),'N',',.0f'))
    assert len(set(counts))==1
    slides['3']=f'''```mermaid
flowchart LR
    A["Stocks · ETFs · Futures · Crypto"] --> B["{counts[0]} assets per class · LOW / MEDIUM / HIGH"]
    B --> C["{design} design-eligible asset-days"]
    C --> D["{common} common-defined asset-days"]
```

Three liquidity tiers; selection frozen independently of estimator outcomes.

FX retained in scope but unavailable because official access remained blocked; no substitute data.

Footer: class calendars differ; futures cover their verified common year only. Common-defined conditioning can change the effective date/tier composition.

Visual: use this compact flow, not a dense coverage table.'''
    q('3','tiers','Three tiers, three assets per tier, independently within each class','README.md','| futures | HIGH | NQ, ZF, ES |')
    q('3','fx','FX in scope but blocked; no substitutes','README.md','FX remains **IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS**')
    slides['4']='''```mermaid
flowchart LR
    A[Daily OHLC] --> B[CS / AR / EDGE]
    C[One-minute closes] --> D[Roll benchmark]
    B --> E["Error = estimator − Roll"]
    D --> E
    E --> F[Bias · MAE · RMSE]
```

**All estimators use exactly the same asset-days.**

Footer: primary equal asset-day weighting; bps. HAC inference applies only to signed bias. MAE/RMSE rankings are descriptive.

Visual: parallel inputs converging into one comparison; no full derivations.'''
    q('4','comparison_rules','Identical common days; signed-bias HAC only','paper/final_paper_draft.md','No significance test was specified for MAE or RMSE differences.')
    rows=[]
    for method in ['CS','AR','EDGE']:
        filt=dict(reporting_scope='overall',estimator=method)
        rows.append([method,*[v('5',method+'_'+metric,P+'primary_accuracy_results.csv',filt,metric) for metric in ['mae_bps','rmse_bps']]])
    slides['5']=table(['Estimator','MAE (bps)','RMSE (bps)'],rows)+'''

**EDGE roughly halves typical absolute benchmark error relative to CS / AR; the advantage is not universal.**

Visual: make this compact table dominant, with the existing estimator-versus-Roll scatter alongside or below it for benchmark context. Do not interpret the scatter as a significance test.

'''+figure('5','figure1_estimator_vs_roll','Full common-defined scatter; the table, not a fitted line, supplies the MAE/RMSE comparison.')+'''

Footer: descriptive accuracy; no formal statistical-superiority test for MAE/RMSE.'''
    q('5','overall_edge_leader','EDGE overall MAE/RMSE leader','README.md','EDGE has the lowest overall MAE and RMSE in this frozen sample.')
    matrix=[]
    for cls,label in [('stocks','Stocks'),('etfs','ETFs'),('futures','Futures'),('crypto','Crypto')]:
        filt=dict(variant='Primary',reporting_scope='asset_class',asset_class=cls,estimator='EDGE')
        leaders=[cell('6',cls+'_'+metric,R+'robustness_conclusion_stability.csv',filt,metric) for metric in ['mae_leader','rmse_leader']]
        matrix.append([label,*leaders,'MIXED' if leaders[0]!=leaders[1] else 'Same leader on both metrics'])
    slides['6']=table(['Class','Lowest MAE','Lowest RMSE','Interpretation'],matrix)+'\n\n'+figure('6','figure3_relative_performance','Read class-aggregate leaders from the matrix; the existing figure shows class × tier cells, whose boundaries can differ from the class aggregate.')
    for row0 in pd.read_csv(ROOT/P/'primary_accuracy_results.csv').query("reporting_scope == 'asset_class_x_tier'").to_dict('records'):
        filt={k:row0[k] for k in ['reporting_scope','asset_class','liquidity_tier','estimator']}
        for metric in ['mae_bps','rmse_bps']:v('6','figure3_'+row0['asset_class']+'_'+row0['liquidity_tier']+'_'+row0['estimator']+'_'+metric,P+'primary_accuracy_results.csv',filt,metric,'.6g')
    slides['7']=table(['Hypothesis','Evidence','Assessment'],[
        ['H1: EDGE dominates accuracy','Overall yes; universal no','Partially supported'],
        ['H2: EDGE has lowest raw-negative rate','Lowest overall; class exceptions','Partially supported'],
        ['H3: CS downward bias in LOW liquidity','Observed bias positive in every completed class','Not supported'],
        ['H4: Rankings stable across classes','ETF and stock boundaries differ','Not supported']])+'''

Visual: neutral evidence matrix; equal visual weight for adverse and favorable findings. Use text labels, not red/green success/failure coding.

Footer: raw negatives are not estimation failures; conclusions concern this benchmark and sample.'''
    q('7','h1_h2_h3_h4','Partial accuracy/negative support; adverse CS bias and ranking results','paper/final_paper_draft.md','The negative-rate hypothesis therefore receives partial rather than universal support.')
    q('7','negative_rate_exceptions','EDGE lowest overall; CS lower in futures and crypto','README.md','EDGE has the lowest overall raw-negative rate, but CS is lower in futures and crypto.')
    for cls in ['stocks','etfs','futures','crypto']:
        v('7','positive_low_CS_bias_'+cls,P+'primary_accuracy_results.csv',dict(reporting_scope='asset_class_x_tier',asset_class=cls,liquidity_tier='LOW',estimator='CS'),'bias_bps')
    overall=v('8','overall_roll_undefined',P+'failure_rates.csv',dict(reporting_scope='overall',estimator='ROLL'),'failure_rate',scale=100)
    etf=v('8','ETF_roll_undefined',P+'failure_rates.csv',dict(reporting_scope='asset_class',asset_class='etfs',estimator='ROLL'),'failure_rate',scale=100)
    slides['8']=f'''**Roll undefined: {overall}% overall; {etf}% for ETFs.**

Accuracy is conditional on days where Roll and all methods are defined.

**Interpretation: best match to the Roll proxy—not the true best transaction-cost estimator.**

'''+figure('8','figure4_benchmark_coverage','Emphasize the left-hand undefinedness panel. The right-hand R25/R50 panel is sensitivity evidence only, never the primary sample.')
    for cls in ['stocks','etfs','futures','crypto']:
        for method in ['ROLL','CS','AR','EDGE']:
            v('8','figure4_failure_'+cls+'_'+method,P+'failure_rates.csv',dict(reporting_scope='asset_class',asset_class=cls,estimator=method),'failure_rate','.6g',100)
        for variant in ['Roll R25','Roll R50']:
            v('8','figure4_retention_'+cls+'_'+variant,R+'roll_quality_sensitivity.csv',dict(reporting_scope='asset_class',asset_class=cls,variant=variant,estimator='CS'),'retention_pct','.6g')
    slides['9']=table(['Prespecified sensitivity','What survives?','Boundary'],[
        ['Roll R25 / R50','EDGE overall leader; class leader patterns unchanged','Thin ETF tier cells tiny or unavailable'],
        ['Equal-asset weighting','Overall and class leaders unchanged','Different estimand; does not cure selection'],
        ['Bloomberg adjusted / unadjusted','Stock/ETF class leaders unchanged','Matched dates; local corporate-event caveats'],
        ['EDGE abs-root','Overall EDGE leadership survives','Stocks switch to CS on both metrics'],
        ['Leave-one-asset-out','Within-class MAE leaders stable','Stock RMSE changes when SNDL is omitted']])+'''

**Overall EDGE result survives the major applicable checks; local stock / thin-tier results are less stable.**

Visual: concise evidence rows; no new preferred specification or composite score.'''
    for variant in ['Roll R25','Roll R50','Equal asset weighting','Bloomberg unadjusted','EDGE abs-root']:
        for cls in (['stocks','etfs'] if variant=='Bloomberg unadjusted' else ['ALL','stocks','etfs','futures','crypto']):
            filt=dict(variant=variant,asset_class=cls,liquidity_tier='ALL',estimator='EDGE')
            for metric in ['mae_leader','rmse_leader']:cell('9',variant+'_'+cls+'_'+metric,R+'robustness_conclusion_stability.csv',filt,metric)
    q('9','influence_boundary','SNDL omission changes stock RMSE leadership; primary untouched','paper/final_paper_draft.md','stock RMSE leadership changes from CS to EDGE when SNDL is omitted.')
    slides['10']='''- EDGE is the strongest overall estimator against the frozen Roll benchmark.
- Method choice depends on asset class and error criterion: ETFs favor CS; stocks are mixed; futures and crypto favor EDGE.
- Benchmark availability limits the conclusion to agreement with Roll, rather than true effective execution cost.

**Daily OHLC spread estimators are useful, but they are not interchangeable across market structures.**

Visual: no table; three bullets only, followed by the closing sentence.'''
    q('10','conclusion','Overall EDGE leadership with class/criterion boundaries','paper/final_paper_draft.md','EDGE is the strongest overall estimator against the frozen one-minute Roll benchmark within the sampled universe, but no estimator dominates universally.')
    r2=[]
    for method in ['CS','AR','EDGE']:
        r2.append([method,v('A1',method+'_absolute_error_R2',M+'cross_fitted_performance.csv',dict(estimator=method,target_type='absolute_error_bps'),'R2','.3f')])
    appendix['A1']='''**Secondary / diagnostic only: estimator error is partly predictable.**

'''+table(['Estimator','Absolute-error cross-fitted R²'],r2)+'\n\n'+figure('A1','figure5_error_predictors','High-low range, open-close movement and asset class matter; liquidity tier is weak/unstable conditional on these features.')+'''

Association only: no causal claim, trading forecast or new spread estimator. Price-condition features overlap estimator inputs; pooled fit can hide adverse class-specific fit. The lagged placebo retains predictability.

Optional talk insert: replace the main robustness slide with this slide if a diagnostic discussion is specifically requested; otherwise use only in Q&A. Do not silently add it to the default main-slide count.'''
    for rec in pd.read_csv(ROOT/M/'feature_importance_stability.csv').query("target_type == 'absolute_error_bps'").to_dict('records'):
        for metric in ['mean_importance_bps','std_importance_bps']:
            v('A1','figure5_'+rec['estimator']+'_'+rec['feature']+'_'+metric,M+'feature_importance_stability.csv',dict(estimator=rec['estimator'],target_type='absolute_error_bps',feature=rec['feature']),metric,'.6g')
    q('A1','tier_importance_limit','Tier importance small/unstable conditionally; no economic irrelevance claim','paper/final_paper_draft.md','Liquidity-tier importance is small and unstable conditional on other included features.')
    universe=[]
    readme=(ROOT/'README.md').read_text(encoding='utf-8')
    for line in readme.splitlines():
        if re.match(r'\| (stocks|etfs|futures|crypto) \| (LOW|MEDIUM|HIGH) \|',line):
            entries=[x.strip() for x in line.strip('|').split('|')]
            universe.append(entries)
            q('A2','universe_'+entries[0]+'_'+entries[1],line,'README.md',line)
    appendix['A2']=table(['Class','Tier','Frozen assets / roots'],universe)+'\n\nNo performance-based replacement; REIT/ADS included under the stock rule. IMDX continuity remains uncertified.'
    definitions=[]
    for method in ['ROLL','CS','AR','EDGE']:
        definitions.append([method,*[cell('A3',method+'_'+col,T+'table1_estimator_definitions_and_coverage.csv',dict(asset_class='ALL',estimator=method),col) for col in ['conceptual_formula','daily_mapping','negative_treatment']]])
    appendix['A3']=table(['Method','Conceptual formula','Frozen mapping','Negative / undefined rule'],definitions)+'\n\nProject mappings are ex-post measurements, not trading signals. No missing-minute filling, gap bridging, carry-forward or compressed missing sessions. Roll computability is not a precision guarantee.'
    tier=[]
    for rec in pd.read_csv(ROOT/P/'primary_accuracy_results.csv').query("reporting_scope == 'asset_class_x_tier'").to_dict('records'):
        filt={key:rec[key] for key in ['reporting_scope','asset_class','liquidity_tier','estimator']}
        tier.append([rec['asset_class'],rec['liquidity_tier'],rec['estimator'],*[v('A4','_'.join([rec['asset_class'],rec['liquidity_tier'],rec['estimator'],col]),P+'primary_accuracy_results.csv',filt,col,',.0f' if col=='N_asset_days' else '.2f') for col in ['mae_bps','rmse_bps','N_asset_days']]])
    appendix['A4']=table(['Class','Tier','Method','MAE (bps)','RMSE (bps)','Common N'],tier)+'\n\nQ&A reference table, not a dense main slide. Descriptive rankings; identical rows per method within a cell; effective common-date composition can differ across tiers.'
    failures=[];negatives=[]
    for method in ['ROLL','CS','AR','EDGE']:
        filt=dict(reporting_scope='overall',estimator=method)
        failures.append([method,v('A5',method+'_failed_N',P+'failure_rates.csv',filt,'failure_N',',.0f'),v('A5',method+'_failure_denominator',P+'failure_rates.csv',filt,'denominator_N',',.0f'),v('A5',method+'_failure_percent',P+'failure_rates.csv',filt,'failure_rate',scale=100)+'%'])
    for method in ['CS','AR','EDGE']:
        filt=dict(reporting_scope='overall',estimator=method)
        negatives.append([method,v('A5',method+'_negative_N',P+'raw_negative_rates.csv',filt,'negative_N',',.0f'),v('A5',method+'_raw_computable_N',P+'raw_negative_rates.csv',filt,'raw_computable_N',',.0f'),v('A5',method+'_negative_percent',P+'raw_negative_rates.csv',filt,'negative_rate',scale=100)+'%'])
    appendix['A5']='**Failures: all design-eligible days.**\n\n'+table(['Method','Undefined N','Design N','Failure rate'],failures)+'\n\n**Raw-negative rates: method-specific finite raw-computable days.**\n\n'+table(['Method','Negative N','Raw-computable N','Raw-negative rate'],negatives)+'\n\nA negative finite raw estimate is not a failure. EDGE has the lowest raw-negative rate overall; CS is lower in futures and crypto. Do not change these denominators to common-defined N.'
    coverage=[]
    for variant in ['Roll R25','Roll R50']:
        filt=dict(reporting_scope='overall',variant=variant,estimator='EDGE')
        coverage.append([variant,v('A6',variant+'_coverage_threshold',R+'roll_quality_sensitivity.csv',filt,'coverage_threshold','.0f',100)+'%',*[v('A6',variant+'_'+col,R+'roll_quality_sensitivity.csv',filt,col,',.0f' if col=='N_asset_days' else '.2f') for col in ['N_asset_days','mae_bps','rmse_bps']],v('A6',variant+'_low_ETF_N',R+'roll_quality_sensitivity.csv',dict(reporting_scope='asset_class_x_tier',asset_class='etfs',liquidity_tier='LOW',variant=variant,estimator='EDGE'),'N_asset_days',',.0f')])
    appendix['A6']=table(['Sensitivity','Pair-coverage floor','Common N','EDGE MAE (bps)','EDGE RMSE (bps)','LOW ETF N'],coverage)+'\n\nCoverage uses valid Roll pairs divided by regular-envelope pair opportunities. Short/early-close sessions can score lower; these opportunities are not synthetic bars. Overall EDGE and class-level leader patterns persist, but sparse tier comparisons do not. Sensitivities only; never preferred primary exclusions.'
    embargo=json.loads((ROOT/'outputs/diagnostics/error_model/output_validation.json').read_text())['embargo_dates']
    row('A7','embargo_dates',dict(source_file='outputs/diagnostics/error_model/output_validation.json',source_metric_or_row=json.dumps(dict(kind='json',key='embargo_dates')),numeric_value=embargo,unit='dates',display=str(embargo)))
    appendix['A7']=f'''Five chronological test folds; one-percent embargo = {embargo} subsequent target dates where available. Exact information-interval purging; train-only preprocessing; fixed HistGradientBoostingRegressor with no tuning; test-only permutation importance.

Block cross-fitting may train on later non-overlapping periods: ex-post diagnostic, not a forward trading forecast. Signed and absolute errors are separate targets.

The scheduled one-period lag placebo retains substantial predictability; AR/EDGE weaken by pooled R² and RMSE, while CS does not. Tier importance is conditional, not evidence that liquidity is irrelevant.

Source: [saved diagnostic review](../outputs/diagnostics/error_model/step20_cross_fitted_error_model_review.md).'''
    q('A7','folds_and_embargo','Five folds; one-percent embargo; no overlap','paper/final_paper_draft.md','with five chronological test folds and an embargo of one percent')
    calendar=[]
    for cls in ['stocks','etfs','futures','crypto']:
        calendar.append([cls,*[v('A8',cls+'_'+col,T+'table1_estimator_definitions_and_coverage.csv',dict(asset_class=cls,estimator='ROLL'),col) for col in ['primary_start','primary_end']]])
    appendix['A8']=table(['Class','Design start','Design end'],calendar)+'''

- Bloomberg adjusted OHLC for stock/ETF estimates; First Rate minute benchmark. CshAdjAbnormal = UNKNOWN; daily/RTH equivalence uncertified.
- Futures: provider-selected individual unadjusted contracts; no continuous adjusted prices or silent substitution. Historical extras remain supplementary.
- Crypto/futures share minute inputs across daily estimates and Roll. Crypto formal quote currency = UNKNOWN; do not label it USD.
- Liquidity tiers use 2024 turnover: look-ahead before calibration, and futures comparison is in-calibration-year. Selection predates performance.
- IMDX historical continuity uncertified; no OCX stitching. FX official access blocked; no substitute.
- Roll is a proxy and common-defined conditioning selects observations. Class calendars differ; this is not a balanced all-class historical panel.
- MAE/RMSE rankings descriptive; HAC only for bias. Cross-fitted models associative; no causal/trading claim.

Source/lineage: [manifest](../manifests/data_manifest.csv), [attrition](../manifests/sample_attrition.csv), [frozen decisions](../design_decisions.md).'''
    q('A8','calibration_and_limitations','2024 calibration and source/identity limitations','README.md','Liquidity tiers use 2024 information')
    return slides,appendix


NOTES=[
('Frame the economic question.','Daily price summaries are widely available, but execution-cost information is harder to obtain. This presentation asks which existing daily estimator best tracks a common intraday proxy.','Start with the question and the original expectations.'),
('Establish falsifiable prior expectations.','We compare CS, AR and EDGE rather than build a new estimator. The original expectations favored EDGE, downward CS bias in thin markets, and stable class rankings. Those expectations were recorded before provider performance and remain open to contradiction.','Explain the sample on which the question can actually be answered.'),
('Show scope and conditioning without an inventory tour.','The completed comparison spans stocks, ETFs, futures and crypto, stratified independently by liquidity. The common-defined sample is smaller than the eligible design, and class calendars differ. FX remained in scope but blocked, with no substitute source.','Show how daily estimates and the intraday proxy enter the same comparison.'),
('Define the target and error criteria.','Each daily spread estimate is compared with the one-minute Roll measure on exactly the same asset-days. Bias describes the average signed gap, MAE typical absolute discrepancy, and RMSE gives large errors more weight. HAC inference concerns signed bias only; the accuracy ranking is descriptive.','Give the overall accuracy answer before discussing its boundaries.'),
('Deliver the central overall finding.','EDGE roughly halves typical absolute error relative to CS and AR in the frozen sample. Its advantage is against Roll, not an observed true execution cost, and it remains positively biased overall. No statistical-superiority test was specified for MAE or RMSE differences.','Ask whether that ordering survives when markets are separated.'),
('Make the class boundary unmistakable.','ETFs favor CS on both criteria, while stocks favor EDGE on MAE and CS on RMSE. Futures and crypto favor EDGE on both. The figure adds tier detail; its individual cells should not be confused with the class-aggregate matrix.','Translate those boundaries into evidence about the original hypotheses.'),
('Retain adverse and partial findings.','Overall EDGE leadership is partial support for dominance, not universal confirmation. Its raw-negative-rate lead also has class exceptions, while positive LOW-tier CS bias contradicts the directional expectation. Stable rankings across classes are not supported.','Explain the benchmark limitation that conditions every accuracy claim.'),
('Make sample selection central to credibility.','Roll availability is the main bottleneck, particularly for ETFs. Our accuracy comparison is conditional on all measures being defined, so it cannot rank methods on the unavailable days. The coverage thresholds shown on the right are sensitivity diagnostics, not the primary sample.','Check whether the overall finding depends on specific conventions.'),
('Separate robust overall results from fragile local results.','Overall EDGE leadership survives the applicable coverage, weighting and convention sensitivities. ETF and stock class leaders are preserved under matched adjusted and unadjusted Bloomberg comparisons. The stock abs-root and asset-omission results show why local conclusions need qualification.','Close with the answer and its economic scope; diagnostic material remains available in the appendix.'),
('Answer the research question directly.','EDGE is the strongest overall match to the frozen Roll benchmark, but method choice depends on asset class and the error criterion. Daily OHLC spread estimators are useful, but they are not interchangeable across market structures.','Invite questions; use the optional appendices only for the topic raised.')]


def run():
    DEST.mkdir(exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
    frozen_manifest=pd.read_csv(ROOT/'outputs/reproducibility/final_artifact_manifest.csv')
    lock={r.relative_path:r.sha256 for r in frozen_manifest.itertuples()}
    for name in ['paper/final_paper_draft.md','paper/paper_claims_audit.csv','src/final_paper.py','outputs/diagnostics/paper_draft/output_validation.json','outputs/reproducibility/final_artifact_manifest.csv']:
        lock[name]=frozen.digest(ROOT/name)
    decks={p.name:frozen.digest(p) for p in DEST.glob('*.pptx')}
    for name,expected in lock.items():assert frozen.digest(ROOT/name)==expected,name
    slides,appendix=build()
    outline='# Final presentation outline\n\nDefault: ten main slides, planned '+str(sum(TIMES)//60)+':'+str(sum(TIMES)%60).zfill(2)+' speaking time. Optional Q&A appendices are outside this budget. No implementation chronology.\n\n'
    outline+=table(['Slide','Purpose / headline','Planned seconds'],[[str(i),title,str(seconds)] for i,(title,seconds) in enumerate(zip(TITLES,TIMES),1)])
    outline+='\n\nThe diagnostic is A1, rather than an additional main slide, to retain a separate conclusion within the requested main-slide limit. A1 may replace slide 9 if a diagnostic focus is explicitly requested; it is never silently appended to the timed flow. Timing is an editorial target, not a measured rehearsal.\n\n'
    outline+=table(['Appendix','Topic'],[[f'A{i}',title] for i,title in enumerate(APPENDIX,1)])
    outline+='\n\nStoryline: economic question → comparable design → overall answer → class boundary → falsification → benchmark limitation → sensitivity → economic conclusion. Primary accuracy, prespecified robustness and secondary diagnostic material remain distinct.\n\nVisual policy: reuse final figures unchanged, keep source/axis/denominator notes, and emphasize a small number of spoken conclusions. No new chart estimation and no PPTX creation.\n'
    (DEST/'final_presentation_outline.md').write_text(outline,encoding='utf-8')
    content='# Final presentation content\n\nPrimary evidence: frozen primary horse race. Sensitivities: prespecified robustness. Cross-fitted models: secondary diagnostic only. All displayed empirical values below are copied or unit-formatted from saved outputs, without re-estimation. The content is a slide plan, not a finished deck.\n\n'
    for i,title in enumerate(TITLES,1):content+=f'## Slide {i} — {title}\n\n'+slides[str(i)]+'\n\n'
    content+='---\n\n# Optional appendix: not in the default speaking budget\n\n'
    for i,title in enumerate(APPENDIX,1):content+=f'## Appendix A{i} — {title}\n\n'+appendix['A'+str(i)]+'\n\n'
    content+='Audit scope: empirical values, dates, method settings, qualitative conclusions and inherited figure labels/data summaries are linked to frozen sources. Slide numbers, hypothesis labels, figure axis ticks and proposed speaking times are editorial structure, not new empirical results. Figure hashes retain the existing full-range plots; plotted observations are not copied into the audit.\n'
    (DEST/'final_presentation_content.md').write_text(content,encoding='utf-8')
    notes='# Speaker notes\n\nUse these as prompts, not a memorized script. Default ten-slide flow; appendix slides are Q&A material.\n\n'
    for i,(objective,spoken,transition) in enumerate(NOTES,1):
        notes+=f'## Slide {i} — {TITLES[i-1]}\n\nObjective: {objective}\n\nSay aloud: {spoken}\n\nTransition: {transition}\n\n'
    notes+='Optional A1 prompt: the cross-fitted model predicts errors rather than generating new spreads; emphasize association, mechanical input overlap and the persistence shown by the lag placebo. If used instead of the main sensitivity slide, return directly to the unchanged conclusion.\n'
    (DEST/'speaker_notes.md').write_text(notes,encoding='utf-8')
    pd.DataFrame(AUDIT).to_csv(DEST/'presentation_claims_audit.csv',index=False)
    for name,expected in lock.items():assert frozen.digest(ROOT/name)==expected,name
    assert {p.name:frozen.digest(p) for p in DEST.glob('*.pptx')}==decks
    result=dict(status='GENERATED_PENDING_VALIDATION',main_slides=len(slides),appendix_slides=len(appendix),planned_speaking_seconds=sum(TIMES),
        claims_audit_rows=len(AUDIT),no_new_analysis=True,no_new_pptx=True,frozen_sha256=lock,
        existing_deck_sha256=decks,code_sha256=frozen.digest(Path(__file__)),
        source_sha256={r['source_file']:frozen.digest(ROOT/r['source_file']) for r in AUDIT})
    (OUT/'run_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('sha256')},indent=2))


if __name__=='__main__':run()
