"""Step21 presentation and reproducibility freeze. No estimation or model fitting."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

import cross_fitted_error_model as diagnostic
import primary_horse_race as primary
import primary_robustness as robustness
import provider_run_io as source
from bloomberg_io import sha256,verify_hashes,require_verified

PROJECT=source.PROJECT
TABLES=PROJECT/'outputs/tables'
FIGURES=PROJECT/'outputs/figures'
REPRO=PROJECT/'outputs/reproducibility'
OUT=PROJECT/'outputs/diagnostics/final_artifacts'
MASTER=PROJECT/'outputs/results/final_results_master.csv'
DOCS=['README.md','design_decisions.md','data_manifest.csv','manifests/data_manifest.csv']
COLORS={'CS':'#0072B2','AR':'#D55E00','EDGE':'#009E73','ROLL':'#666666'}
CLASSES=['stocks','etfs','futures','crypto']
PERIODS='Stocks: 2019-08-01–2025-12-31; ETFs: 2020-09-15–2025-12-31; futures: 2024 only; crypto: 2022-02-01–2025-12-31.'
LIMITATIONS=[
    'Roll is a transaction-close proxy, not true effective spread or NBBO cost.',
    'Roll undefinedness is the main sample bottleneck; ETF availability is especially low.',
    'Common-defined conditioning can create economic selection; no reliability cutoff beyond frozen computability is primary.',
    'Classes have different calendar support; this is not a balanced 2015–2025 all-class panel.',
    'Futures primary analysis is 2024 only; supplementary heterogeneous histories are not the primary tier comparison.',
    'Liquidity tiers use 2024 information, including ex-post/look-ahead classification before 2024 and an in-calibration-year futures comparison.',
    'Futures and crypto share minute sources between daily OHLC and Roll, creating mechanical dependence.',
    'Crypto formal quote currency remains UNKNOWN; no USD spread claim is made.',
    'Bloomberg CshAdjAbnormal is UNKNOWN; acquired adjustment/session equivalence with local First Rate is not certified.',
    'IMDX historical economic-identity continuity is not independently certified; no manual OCX stitching.',
    'FX remains in scope but blocked by official sharing/synchronization access; no substitute data were used.',
    'MAE/RMSE rankings are descriptive; no statistical test of metric differences was specified. HAC applies to signed bias only.',
    'Cross-fitted error models describe associations, not causal effects, trading forecasts or a new spread estimator.',
    'Feature and importance stability is conditional on the sampled assets/calendars; correlated predictors can share importance.']


def read(path):return pd.read_csv(path,float_precision='round_trip')


def inputs():
    panel,common=diagnostic.verify_inputs()
    manifest=json.loads((diagnostic.OUT/'run_manifest.json').read_text())
    assert manifest['status']=='CROSSFITTED_ERROR_MODEL_COMPLETE'
    robustness.check_lock(manifest['prior_lock_sha256'])
    for category in ['code_sha256','output_sha256','analytic_sha256']:
        for name,digest in manifest[category].items():assert sha256(PROJECT/name)==digest,name
    return panel,common


def analytic_lock():
    lock=diagnostic.prior_lock()
    for folder in [diagnostic.OUT,diagnostic.RESULTS]:
        lock.update({p.relative_to(PROJECT).as_posix():sha256(p) for p in folder.iterdir() if p.is_file()})
    lock.update({p.relative_to(PROJECT).as_posix():sha256(p) for p in list(diagnostic.ANALYTIC.iterdir())+[diagnostic.PREDICTIONS] if p.is_file()})
    return lock


def format_md(frame):
    clean=frame.copy().astype(object)
    for col in clean:
        clean[col]=clean[col].map(lambda v:'unavailable / blocked' if pd.isna(v) else
            f'{v:.6g}' if isinstance(v,(float,np.floating)) else str(v))
        clean[col]=clean[col].map(lambda v:v.replace('|',' / ').replace('\n',' '))
    return primary.markdown(clean)


def build_tables():
    accuracy=read(primary.RESULTS/'primary_accuracy_results.csv')
    hac=read(primary.RESULTS/'primary_bias_hac_results.csv')
    failure=read(primary.RESULTS/'failure_rates.csv');negative=read(primary.RESULTS/'raw_negative_rates.csv')
    spec=yaml.safe_load((source.DESIGN/'global_design_final_spec.yaml').read_text())
    formulas={
        'ROLL':('2 sqrt(-sample lag-1 covariance of adjacent simple one-minute returns)',
            'One-minute close; exact physical three-close chains','Within frozen asset-session/day; ddof=1; minimum 2 pairs',
            'Nonnegative covariance undefined/NaN; never zero'),
        'CS':('Overnight-adjusted two-session beta/gamma -> alpha -> 2 tanh(alpha/2)',
            'H/L at t-1,t,t+1; close at t-1,t','Mean corrected intervals (t-1,t) and (t,t+1); both required',
            'Floor each finite interval separately before averaging; retain raw daily signed mean'),
        'AR':('s2=4(log(C_t)-eta_t)(log(C_t)-eta_(t+1)); eta=(log(H)+log(L))/2',
            'H/L at t,t+1; close_t','Assigned to target t; no carry-forward or author empirical imputation',
            'sqrt(max(s2,0)); finite negative raw moment remains defined'),
        'EDGE':('Published Eq26 minimum-variance combination of OHLC log-return moments',
            'OHLC at t-1,t,t+1','Centered three scheduled sessions; local RMS spread assigned to t',
            'sqrt(max(raw s2,0)); abs-root is robustness only')}
    rows=[]
    for row in failure.loc[failure.reporting_scope.isin(['overall','asset_class'])].to_dict('records'):
        method=row['estimator'];cls=row['asset_class'];f=formulas[method]
        raw=negative.loc[negative.reporting_scope.eq(row['reporting_scope'])&negative.asset_class.eq(cls)&negative.estimator.eq(method)]
        dates=spec['primary_calendar_by_class'].get(cls,{})
        rows.append(dict(estimator=method,asset_class=cls,conceptual_formula=f[0],required_inputs=f[1],daily_mapping=f[2],
            negative_treatment=f[3],units='dimensionless relative spread; bps=10000*relative',
            design_eligible_N=row['denominator_N'],defined_N=row['denominator_N']-row['failure_N'],undefined_N=row['failure_N'],
            failure_rate=row['failure_rate'],raw_negative_rate=raw.negative_rate.iloc[0] if len(raw) else np.nan,
            raw_computable_N=raw.raw_computable_N.iloc[0] if len(raw) else np.nan,
            primary_start=dates.get('start','class-specific'),primary_end=dates.get('end','class-specific'),
            status='PRIMARY_FROZEN',source_result_file='outputs/results/primary/failure_rates.csv; outputs/results/primary/raw_negative_rates.csv'))
    rows.append(dict(estimator='ALL',asset_class='fx',status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS',
        conceptual_formula='Unavailable / blocked; no substitute',source_result_file='outputs/diagnostics/final_universe/fx_final/fx_final_spec.yaml'))
    table1=pd.DataFrame(rows)
    table2=accuracy.loc[accuracy.reporting_scope.isin(['overall','asset_class','asset_class_x_tier'])].merge(
        hac.drop(columns=['bias_bps','N_asset_days','T_dates']),on=primary.CELL_KEYS+['estimator'],validate='one_to_one')
    table2['panel']=table2.reporting_scope.map(dict(overall='A',asset_class='B',asset_class_x_tier='C'))
    table2['source_result_file']='outputs/results/primary/primary_accuracy_results.csv; outputs/results/primary/primary_bias_hac_results.csv'
    ranks=read(primary.RESULTS/'descriptive_rankings.csv')
    extremes=read(robustness.RESULTS/'extreme_observation_influence.csv')
    table3=pd.concat([
        failure.loc[failure.reporting_scope.isin(['overall','asset_class'])].assign(panel='A',denominator_policy='ALL design-eligible asset-days',source_result_file='outputs/results/primary/failure_rates.csv'),
        negative.loc[negative.reporting_scope.isin(['overall','asset_class'])].assign(panel='B',denominator_policy='Design-eligible AND finite computable RAW estimate',source_result_file='outputs/results/primary/raw_negative_rates.csv'),
        ranks.loc[ranks.reporting_scope.eq('asset_class')].assign(panel='C',denominator_policy='Primary COMMON sample',source_result_file='outputs/results/primary/descriptive_rankings.csv'),
        extremes.assign(panel='D',denominator_policy='One observation removed per class/method for influence only; primary unchanged',source_result_file='outputs/results/robustness/extreme_observation_influence.csv')],ignore_index=True)
    stability=read(robustness.RESULTS/'robustness_conclusion_stability.csv')
    table4=stability.loc[stability.variant.ne('Primary')&stability.estimator.eq('EDGE')].copy()
    table4['affected_scope']=table4.reporting_scope
    table4['sample_N_display']=table4.N_asset_days.astype(str)
    table4['primary_conclusion_changed']=table4.qualitative_change_from_primary.astype(str)
    table4['source_result_file']='outputs/results/robustness/robustness_conclusion_stability.csv'
    loo=read(robustness.RESULTS/'leave_one_asset_out.csv')
    additional=[]
    for cls,part in loo.groupby('asset_class'):
        additional.append(dict(variant='Leave-one-asset-out',asset_class=cls,liquidity_tier='ALL',estimator='CS/AR/EDGE',
            affected_scope='class',N_asset_days=np.nan,N_min=part.N_asset_days.min(),N_max=part.N_asset_days.max(),
            sample_N_display=f'{part.N_asset_days.min()}–{part.N_asset_days.max()}',
            mae_leader=';'.join(sorted(part.mae_leader.unique())),rmse_leader=';'.join(sorted(part.rmse_leader.unique())),
            primary_conclusion_changed=str(bool(part.mae_leader.ne(part.original_mae_leader).any()|part.rmse_leader.ne(part.original_rmse_leader).any())),
            notes='Nine deterministic asset omissions within class; not a preferred alternative sample',source_result_file='outputs/results/robustness/leave_one_asset_out.csv'))
    for cls,part in extremes.groupby('asset_class'):
        additional.append(dict(variant='Single-extreme influence',asset_class=cls,liquidity_tier='ALL',estimator='CS/AR/EDGE',
            affected_scope='class x method',N_asset_days=part.N_after.iloc[0],sample_N_display=str(part.N_after.iloc[0]),
            mae_leader='NOT_RANKED',rmse_leader='NOT_RANKED',primary_conclusion_changed='NOT_RETESTED',
            notes='Different single observation per method; diagnostic only, not a new common-sample horse race',source_result_file='outputs/results/robustness/extreme_observation_influence.csv'))
    for filename,variant in [('cross_fitted_performance.csv','Cross-fitted error model'),('date_shift_placebo.csv','Lagged placebo')]:
        for row in read(diagnostic.RESULTS/filename).to_dict('records'):
            additional.append(dict(variant=variant,asset_class='ALL',liquidity_tier='ALL',estimator=row['estimator'],
                affected_scope=row['target_type'],N_asset_days=row['N'],sample_N_display=str(row['N']),mae_bps=row['MAE'],rmse_bps=row['RMSE'],
                mae_leader='NOT_APPLICABLE',rmse_leader='NOT_APPLICABLE',primary_conclusion_changed='NOT_RETESTED',
                notes='Prediction of errors, not spread accuracy or a new estimator; association only',source_result_file='outputs/results/error_model/'+filename))
    table4=pd.concat([table4,pd.DataFrame(additional)],ignore_index=True)
    appendix=[]
    for cls in CLASSES+['ALL']:
        f=failure.loc[failure.asset_class.eq(cls)&failure.reporting_scope.eq('overall' if cls=='ALL' else 'asset_class')].set_index('estimator')
        common=accuracy.loc[accuracy.asset_class.eq(cls)&accuracy.reporting_scope.eq('overall' if cls=='ALL' else 'asset_class'),'N_asset_days'].iloc[0]
        calendar=spec['primary_calendar_by_class'].get(cls,{})
        base=dict(asset_class=cls,primary_start=calendar.get('start','class-specific'),primary_end=calendar.get('end','class-specific'),
            status='FROZEN',source_result_file='outputs/results/primary/failure_rates.csv; outputs/results/primary/primary_accuracy_results.csv',
            source_role='Bloomberg adjusted estimator inputs + First Rate minute Roll' if cls in ['stocks','etfs'] else
            'First Rate individual unadjusted contracts' if cls=='futures' else 'First Rate UTC daily/minute common-quote-basis; formal quote UNKNOWN' if cls=='crypto' else 'Four completed classes; FX blocked')
        appendix.append(dict(base,stage='raw_selected_universe',N=sum(len(x) for k,x in spec['selected_assets_by_class'].items()) if cls=='ALL' else len(spec['selected_assets_by_class'][cls]),unit='assets/roots',denominator_N=np.nan,notes='Selected streams/roots, not count of individual futures files'))
        appendix.append(dict(base,stage='primary_calendar',N=calendar.get('exact_common_dates',np.nan),unit='class-specific dates',denominator_N=np.nan,notes='Overall has no single balanced primary calendar'))
        design=int(f.denominator_N.iloc[0])
        appendix.append(dict(base,stage='design_eligible',N=design,unit='asset-days',denominator_N=design,notes='Independent of estimator/benchmark outcomes'))
        for method in ['ROLL','CS','AR','EDGE']:
            appendix.append(dict(base,stage=method+'_defined',N=int(f.loc[method,'denominator_N']-f.loc[method,'failure_N']),unit='asset-days',denominator_N=design,
                notes='Parallel method-defined sets; not sequential/cumulative exclusions'))
        appendix.append(dict(base,stage='common_defined',N=int(common),unit='asset-days',denominator_N=design,notes='Exact conjunction; no extra pair, magnitude, zero or outlier filter'))
        appendix.append(dict(base,stage='additional_loss_after_Roll_defined',N=int(f.loc['ROLL','denominator_N']-f.loc['ROLL','failure_N']-common),unit='asset-days',denominator_N=int(f.loc['ROLL','denominator_N']-f.loc['ROLL','failure_N']),notes='Additional method attrition conditional on Roll defined; do not sum overlapping failures'))
    appendix.append(dict(asset_class='fx',stage='official_source_access',N=np.nan,unit='unavailable / blocked',denominator_N=np.nan,
        status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS',source_role='Official RiskLab intraday_data/fx only',notes='No substitute; no fabricated inventory or zero sample count',source_result_file='outputs/diagnostics/final_universe/fx_final/fx_final_spec.yaml'))
    return {'table1_estimator_definitions_and_coverage':table1,'table2_primary_horse_race':table2,
        'table3_failure_negative_decomposition':table3,'table4_robustness_falsification':table4,
        'appendix_data_lineage_attrition':pd.DataFrame(appendix)}


def table_markdowns(tables):
    notes='\n\n'+PERIODS+' FX: in scope but blocked official source access. '+ ' '.join(LIMITATIONS)+'\n'
    for name,frame in tables.items():
        text='# '+name.replace('_',' ').capitalize()+'\n\n'
        if name.startswith('table1'):
            text+='Definedness uses all design days. Raw-negative rates use finite RAW-computable denominators, not failure denominators. Formulas/mappings are concise summaries of the frozen specifications.\n\n'
            text+=format_md(frame[['asset_class','estimator','design_eligible_N','defined_N','undefined_N','failure_rate','raw_negative_rate','raw_computable_N','primary_start','primary_end','status']])
            text+='\n\n'+format_md(frame.loc[frame.asset_class.eq('ALL'),['estimator','conceptual_formula','required_inputs','daily_mapping','negative_treatment','units']])
        elif name.startswith('table2'):
            text+='**Primary common-defined sample = '+str(int(frame.loc[frame.panel.eq('A'),'N_asset_days'].iloc[0]))+' asset-days.** Equal weight per asset-day. Signed error=estimator minus Roll; bps. HAC uncertainty concerns BIAS only, not MAE/RMSE differences.\n\n'
            for panel in ['A','B','C']:
                cols=['asset_class','liquidity_tier','estimator','bias_bps','mae_bps','rmse_bps','N_asset_days']
                if panel=='A':cols+=['hac_se_bps','ci95_low_bps','ci95_high_bps','p_value_two_sided']
                text+='Panel '+panel+'\n\n'+format_md(frame.loc[frame.panel.eq(panel),cols])+'\n\n'
        elif name.startswith('table3'):
            for panel,cols in [('A',['asset_class','estimator','failure_N','denominator_N','failure_rate']),
                ('B',['asset_class','estimator','negative_N','raw_computable_N','negative_rate']),
                ('C',['asset_class','estimator','mae_rank','rmse_rank','accuracy_leader_status']),
                ('D',['asset_class','estimator','original_N','removed_N','mae_pct_change','rmse_pct_change'])]:
                text+='Panel '+panel+'\n\n'+format_md(frame.loc[frame.panel.eq(panel),cols])+'\n\n'
        elif name.startswith('table4'):
            text+='Step19 sensitivities and Step20 diagnostics NEVER replace Step18. Overall EDGE leadership survives applicable accuracy sensitivities. Stock RMSE is fragile; stock EDGE MAE loses leadership under abs-root; LOW ETF R25/R50 cells can be tiny/unavailable. ML/influence-only rows do not define new spread rankings. Full class/tier sensitivity cells are in the CSV.\n\n'
            show=frame.loc[frame.liquidity_tier.eq('ALL')|frame.asset_class.eq('etfs')&frame.liquidity_tier.eq('LOW')]
            text+=format_md(show[['variant','asset_class','liquidity_tier','affected_scope','sample_N_display','mae_leader','rmse_leader','primary_conclusion_changed','notes']])
        else:
            text+='Raw source -> frozen universe -> class calendar -> design -> parallel method-defined sets -> common conjunction. Roll undefinedness is the principal loss, especially ETFs; additional method losses are not additive.\n\n'+format_md(frame)
        (TABLES/(name+'.md')).write_text(text+notes,encoding='utf-8')


def build_master(tables):
    rows=[]
    folders=[('PRIMARY','Step18',primary.RESULTS),('ROBUSTNESS','Step19',robustness.RESULTS),('DIAGNOSTIC','Step20',diagnostic.RESULTS)]
    paths=[(stage,spec,p) for stage,spec,folder in folders for p in sorted(folder.glob('*.csv'))]
    paths += [('PRESENTATION','Step21',TABLES/(name+'.csv')) for name in tables]
    for stage,spec,path in paths:
        data=read(path)
        numeric=[col for col in data if pd.api.types.is_numeric_dtype(data[col])]
        for index,row in data.iterrows():
            for metric in numeric:
                value=row[metric]
                if pd.isna(value):continue
                n_columns=['raw_computable_N','N_asset_days','N','denominator_N','design_eligible_N'] if 'negative' in metric else ['N_asset_days','N','denominator_N','design_eligible_N','raw_computable_N']
                count=next((row[col] for col in n_columns if col in row and pd.notna(row[col])),np.nan)
                unit='bps2' if 'bps2' in metric else 'bps' if 'bps' in metric or metric in ['MAE','RMSE','baseline_MAE','baseline_RMSE','aligned_MAE','aligned_RMSE'] else 'relative' if 'relative' in metric else 'percent' if 'pct' in metric else 'rate/unitless' if 'rate' in metric or metric in ['R2','baseline_R2','aligned_R2'] else 'count/rank/unitless'
                rows.append(dict(analysis_stage=stage,specification=str(row.get('variant',spec)),reporting_scope=row.get('reporting_scope',row.get('stage','aggregate')),
                    asset_class=row.get('asset_class','ALL'),liquidity_tier=row.get('liquidity_tier','ALL'),estimator=row.get('estimator','ALL'),metric=metric,
                    value=float(value),unit=unit,N=count,
                    T=row.get('T_dates',np.nan),uncertainty_type='HAC_SIGNED_BIAS_ONLY' if metric in ['bias_bps','hac_se_bps','ci95_low_bps','ci95_high_bps','p_value_two_sided'] and 'hac_se_bps' in data else 'NONE_DESCRIPTIVE',
                    standard_error=row.get('hac_se_bps',np.nan) if metric=='bias_bps' else np.nan,
                    ci_low=row.get('ci95_low_bps',np.nan) if metric=='bias_bps' else np.nan,ci_high=row.get('ci95_high_bps',np.nan) if metric=='bias_bps' else np.nan,
                    p_value=row.get('p_value_two_sided',np.nan) if metric=='bias_bps' else np.nan,source_result_file=path.relative_to(PROJECT).as_posix(),source_row=index,
                    target_type=row.get('target_type',''),fold=row.get('fold',''),feature=row.get('feature',''),asset=row.get('asset',''),panel=row.get('panel','')))
    master=pd.DataFrame(rows)
    assert not master.duplicated(['source_result_file','source_row','metric']).any()
    master.to_csv(MASTER,index=False)
    return master


def save_figure(fig,name,note):
    fig.text(.015,.012,PERIODS+'\n'+note,fontsize=7,va='bottom')
    fig.tight_layout(rect=(0,.09,1,.95))
    for ext in ['png','pdf']:fig.savefig(FIGURES/(name+'.'+ext),dpi=300,bbox_inches='tight')
    plt.close(fig)


def figures(common):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False,'pdf.fonttype':42})
    a=read(primary.RESULTS/'primary_accuracy_results.csv');failure=read(primary.RESULTS/'failure_rates.csv')
    metadata=[]
    fig,axes=plt.subplots(1,3,figsize=(11,4.6))
    maximum=max(common.roll_spread_bps.max(),max(common[m+'_primary_spread_bps'].max() for m in primary.METHODS))
    for ax,m in zip(axes,primary.METHODS):
        ax.scatter(common.roll_spread_bps,common[m+'_primary_spread_bps'],s=3,alpha=.09,color=COLORS[m.upper()],linewidths=0,rasterized=True)
        ax.plot([0,maximum],[0,maximum],color='black',ls='--',lw=.8,label='45° reference')
        ax.set(xlabel='Roll spread (bps)',ylabel='Estimator spread (bps)',title=m.upper(),xlim=(0,maximum*1.03),ylim=(0,maximum*1.03))
        ax.set_xscale('asinh',linear_width=5);ax.set_yscale('asinh',linear_width=5);ax.legend(fontsize=7)
        ticks=[v for v in [0,10,100,1000,10000] if v<=maximum*1.03]
        ax.set_xticks(ticks,[str(v) for v in ticks]);ax.set_yticks(ticks,[str(v) for v in ticks])
        ax.set_aspect('equal',adjustable='box')
    fig.suptitle('Estimator versus Roll: full-range common-defined sample')
    save_figure(fig,'figure1_estimator_vs_roll',f'N={len(common):,} asset-days per estimator; both units=bps. Full-range asinh axes (linear near zero); no observations clipped or excluded. Step18 frozen panel.')
    fig,ax=plt.subplots(figsize=(8,4.8))
    for m in primary.METHODS:
        x=np.sort(common[m+'_error_bps'].to_numpy());ax.plot(x,np.arange(1,len(x)+1)/len(x),label=m.upper(),color=COLORS[m.upper()],lw=1.5,rasterized=True)
    ax.axvline(0,color='black',ls='--',lw=.8);ax.set_xscale('asinh',linear_width=5)
    ticks=[-1000,-100,-10,0,10,100,1000,10000]
    ax.set_xticks(ticks,[str(v) for v in ticks])
    ax.set(xlabel='Signed error: estimator − Roll (bps)',ylabel='Empirical cumulative probability',ylim=(0,1));ax.legend()
    fig.suptitle('Signed-error distributions: full-range ECDF')
    save_figure(fig,'figure2_error_distribution',f'Primary common-defined N={len(common):,} per estimator. Asinh x-axis retains all finite extremes; no display clipping. Zero-error reference shown. Step18 frozen errors.')
    fig,axes=plt.subplots(4,2,figsize=(10,11))
    for i,cls in enumerate(CLASSES):
        for j,metric in enumerate(['mae_bps','rmse_bps']):
            ax=axes[i,j]
            for k,m in enumerate(['CS','AR','EDGE']):
                part=a.loc[a.reporting_scope.eq('asset_class_x_tier')&a.asset_class.eq(cls)&a.estimator.eq(m)].set_index('liquidity_tier')
                ax.bar(np.arange(3)+(k-1)*.24,part.loc[['LOW','MEDIUM','HIGH'],metric],width=.24,label=m,color=COLORS[m])
            ax.set_xticks(range(3),['LOW','MEDIUM','HIGH']);ax.set_ylabel(metric.replace('_bps','').upper()+' (bps)');ax.set_title(cls.upper())
            if i==0:ax.legend(ncol=3,fontsize=7)
    fig.suptitle('Primary accuracy by asset class and liquidity tier')
    save_figure(fig,'figure3_relative_performance','Step18 class × tier; same common rows per method in cell; separate y scales. Class-aggregate MAE/RMSE leaders: stocks EDGE/CS, ETFs CS/CS, futures and crypto EDGE/EDGE.\nDescriptive ranks only; no MAE/RMSE significance tests. Tier-specific boundaries may differ from class aggregates.')
    fig,axes=plt.subplots(1,2,figsize=(11,4.8))
    for k,m in enumerate(['ROLL','CS','AR','EDGE']):
        values=failure.loc[failure.reporting_scope.eq('asset_class')&failure.estimator.eq(m)].set_index('asset_class').loc[CLASSES,'failure_rate']*100
        axes[0].bar(np.arange(4)+(k-1.5)*.19,values,width=.19,label=m,color=COLORS[m])
    axes[0].set_xticks(range(4),[x.upper() for x in CLASSES]);axes[0].set(ylabel='Undefined / all design days (%)',ylim=(0,100),title='Primary bottleneck: Roll undefinedness');axes[0].legend(ncol=2,fontsize=7)
    quality=read(robustness.RESULTS/'roll_quality_sensitivity.csv')
    for k,name in enumerate(['Roll R25','Roll R50']):
        part=quality.loc[quality.variant.eq(name)&quality.reporting_scope.eq('asset_class')&quality.estimator.eq('CS')].set_index('asset_class')
        axes[1].bar(np.arange(4)+(k-.5)*.33,part.loc[CLASSES,'retention_pct'],width=.33,label=name,color=['#56B4E9','#CC79A7'][k])
    axes[1].set_xticks(range(4),[x.upper() for x in CLASSES]);axes[1].set(ylabel='Retained / primary common sample (%)',ylim=(0,105),title='Pair-coverage sensitivities ONLY');axes[1].legend(fontsize=7)
    fig.suptitle('Benchmark availability and coverage: ETF attrition is greatest')
    save_figure(fig,'figure4_benchmark_coverage','Left: Step18 design denominators; right: Step19 R25/R50 retention of the already-common sample, not the primary inclusion rule. No threshold replaces the primary sample.')
    importance=read(diagnostic.RESULTS/'feature_importance_stability.csv')
    fig,axes=plt.subplots(1,3,figsize=(12,5.4))
    for ax,m in zip(axes,['CS','AR','EDGE']):
        part=importance.loc[importance.estimator.eq(m)&importance.target_type.eq('absolute_error_bps')].sort_values('mean_importance_bps')
        ax.barh(part.feature,part.mean_importance_bps,xerr=part.std_importance_bps,color=COLORS[m],alpha=.8,capsize=2)
        ax.axvline(0,color='black',lw=.7);ax.set(title=m,xlabel='Increase in held-out MAE (bps)')
    fig.suptitle('Error predictors: robustness / diagnostic only')
    save_figure(fig,'figure5_error_predictors','Step20 absolute-error target. Mean test-only raw-feature permutation importance ± fold SD (not CI); all features retained. Association, not causation; volume units differ across assets.')
    refs={1:['data/analytic/primary_horse_race_common.parquet'],2:['data/analytic/primary_horse_race_common.parquet'],
        3:['outputs/results/primary/primary_accuracy_results.csv'],4:['outputs/results/primary/failure_rates.csv','outputs/results/robustness/roll_quality_sensitivity.csv'],
        5:['outputs/results/error_model/feature_importance_stability.csv']}
    for i,name in enumerate(['figure1_estimator_vs_roll','figure2_error_distribution','figure3_relative_performance','figure4_benchmark_coverage','figure5_error_predictors'],1):
        metadata.append(dict(figure=name,source_result_files=json.dumps(refs[i]),dpi=300,display_clipping=False,analysis_recalculated=False))
    pd.DataFrame(metadata).to_csv(REPRO/'figure_lineage.csv',index=False)


def data_manifest():
    rows=[]
    def add(dataset_id,path,provider,role,unit,frequency,adjustment,timezone,status='VALIDATED_FROZEN',notes='',exclusions='Frozen eligibility/calendars only; no filling'):
        rows.append(dict(dataset_id=dataset_id,source_path=path,provider=provider,role=role,unit=unit,frequency=frequency,
            start='' if frequency in ['reference','static'] else '2015-01-01',end='' if frequency in ['reference','static'] else '2025-12-31',adjustment=adjustment,timezone=timezone,validation_status=status,exclusions=exclusions,notes=notes+'; date range is study/request support, not guaranteed complete provider coverage'))
    for cls in CLASSES+['fx']:
        add('first_rate_'+cls,'${RISKLAB_DATA_ROOT}/intraday_data/'+('cryptos' if cls=='crypto' else cls),'First Rate Data / shared RiskLab',
            'Intraday benchmark; local daily inputs/validation; existing shared source referenced, NEVER duplicated',
            'price + shares' if cls in ['stocks','etfs'] else 'price + contracts' if cls=='futures' else 'provider quote + base crypto units' if cls=='crypto' else 'unavailable',
            'one minute','split+dividend adjusted' if cls in ['stocks','etfs'] else 'individual unadjusted contracts' if cls=='futures' else 'provider unspecified',
            'UTC' if cls=='crypto' else 'America/New_York' if cls!='fx' else 'UNRESOLVED',
            status='IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS' if cls=='fx' else 'VALIDATED_FROZEN',
            notes='No substitute; no fabricated inventory; unavailable is not zero' if cls=='fx' else 'Only selected primary support used; no continuous futures prices; crypto quote UNKNOWN')
    for convention in ['adjusted','unadjusted','reference']:
        stem='bloomberg_reference' if convention=='reference' else 'bloomberg_daily_'+convention
        for kind in ['raw.xlsx','raw_values.xlsx']:
            add('bloomberg_'+convention+'_'+kind,'data/raw_bloomberg/13-10-2026/'+stem+'_'+kind,'Bloomberg',
                'Reference validation' if convention=='reference' else 'PRIMARY daily OHLCV' if convention=='adjusted' else 'ROBUSTNESS daily OHLCV',
                'field-specific','reference' if convention=='reference' else 'daily/EOD','CapChg=T; CshAdjNormal=T; CshAdjAbnormal=UNKNOWN' if convention=='adjusted' else 'F/F/F' if convention=='unadjusted' else 'not applicable',
                'EOD timestamps/session not fully certified',notes='Student-extracted acquisition: preserve unchanged in personal Google Drive; SHA-256 manifest covers 11 files')
    for name in ['bloomberg_source_log.xlsx','field_validation_notes.txt']:
        add(name,'data/raw_bloomberg/13-10-2026/'+name,'Bloomberg / student acquisition','Acquisition metadata','metadata','static','not applicable','not applicable',notes='Preserve unchanged with acquisition')
    raw_manifest=read(PROJECT/'data/raw_bloomberg/sha256_manifest.csv')
    for name in raw_manifest.file_name:
        if name.startswith('bloomberg_pilot_'):
            add(name,'data/raw_bloomberg/'+name,'Bloomberg','Saved legacy acquisition validation pilot','field-specific','static','As saved; validation only','As saved',notes='One of eleven immutable hashed raw files; not primary price substitution')
    add('raw_sha256_registry','data/raw_bloomberg/sha256_manifest.csv','Student acquisition metadata','Immutable raw relative-path SHA registry','SHA-256/bytes','static','not applicable','not applicable')
    add('frozen_spec_bundle','outputs/diagnostics/{benchmark_freeze,daily_input_freeze,design_freeze,estimator_freeze,statistical_freeze,final_universe}/','Project frozen metadata','Authoritative method, session, calendar, root and quote policies','metadata','static','Inherited','Class-specific')
    for cls in CLASSES:
        add('calendar_'+cls,'outputs/diagnostics/design_freeze/'+cls+'_primary_calendar.csv','Frozen project metadata','Primary exact common calendar','dates','daily','not applicable','UTC' if cls=='crypto' else 'class local date/trade date',notes=PERIODS)
    for name,path,role in [
        ('daily_adjusted','data/interim/bloomberg/daily_adjusted.parquet','Frozen Bloomberg daily features/estimator source'),
        ('daily_unadjusted','data/interim/bloomberg/daily_unadjusted.parquet','Frozen robustness source'),
        ('reference','data/interim/bloomberg/reference.parquet','Normalized reference metadata'),
        ('daily_local_equity','outputs/diagnostics/final_universe/local_daily_validation/selected_daily_ohlcv.csv','First Rate local validation only'),
        ('daily_futures','outputs/diagnostics/final_universe/futures_final/historical/*_historical_daily_ohlcv.csv','Verified individual-contract daily panels; primary 2024 only'),
        ('daily_crypto','outputs/diagnostics/final_universe/crypto_final/historical/*_historical_daily_ohlcv.csv','Validated UTC daily panels'),
        ('roll_benchmark_panel','data/analytic/primary_provider_panel.parquet','Roll fields and quality diagnostics'),
        ('estimator_panel','data/analytic/primary_provider_panel.parquet','Frozen CS/AR/EDGE fields; same physical panel as Roll'),
        ('common_accuracy_panel','data/analytic/primary_horse_race_common.parquet','Step18 common accuracy/errors'),
        ('primary_results','outputs/results/primary/*.csv','PRIMARY aggregated results'),
        ('robustness_results','outputs/results/robustness/*.csv','ROBUSTNESS aggregated results'),
        ('robustness_panels','data/analytic/robustness/*','Ignored observation-level sensitivity evidence'),
        ('error_model_results','outputs/results/error_model/*.csv','DIAGNOSTIC aggregated prediction/importance results'),
        ('error_predictions','data/analytic/cross_fitted_error_predictions.parquet','Ignored cross-fitted predictions'),
        ('error_features_models','data/analytic/error_model/*','Ignored features, exact membership and fitted models'),
        ('final_master','outputs/results/final_results_master.csv','Final aggregated number/source reconciliation')]:
        add(name,path,'Derived from immutable acquired/shared sources',role,'field-specific relative/bps/count/metadata','asset-day or aggregate',
            'Inherited frozen source convention','Inherited class date/UTC/trade date',notes='Reproducible from licensed sources + code + frozen metadata; licensed observation data remain ignored; class support '+PERIODS)
    frame=pd.DataFrame(rows)
    spec=yaml.safe_load((source.DESIGN/'global_design_final_spec.yaml').read_text())
    for cls in CLASSES:
        mask=frame.dataset_id.eq('calendar_'+cls)
        frame.loc[mask,'start']=spec['primary_calendar_by_class'][cls]['start'];frame.loc[mask,'end']=spec['primary_calendar_by_class'][cls]['end']
    for name in ['roll_benchmark_panel','estimator_panel','primary_results','robustness_results','error_model_results','final_master']:
        frame.loc[frame.dataset_id.eq(name),'start']='2019-08-01'
    for name in ['common_accuracy_panel','error_predictions','error_features_models']:
        frame.loc[frame.dataset_id.eq(name),['start','end']]=['2019-08-01','2025-12-30']
    return frame


def documentation(tables):
    spec=yaml.safe_load((source.DESIGN/'global_design_final_spec.yaml').read_text())
    t=tables['table2_primary_horse_race'];overall=t.loc[t.panel.eq('A')]
    failures=read(primary.RESULTS/'failure_rates.csv');roll=failures.loc[failures.reporting_scope.eq('overall')&failures.estimator.eq('ROLL')].iloc[0]
    n=int(overall.N_asset_days.iloc[0]);design=int(roll.denominator_N)
    notes='\n'.join('- '+x for x in LIMITATIONS)
    readme='# Which Daily OHLC Spread Estimator Tracks Realized Intraday Cost?\n\n'
    readme+='MMF 1941 Project 1, proposal A04-03. Research question: across asset classes and liquidity regimes over the 2015–2025 study horizon, where do CS, AR and EDGE track a one-minute Roll proxy and where do they break down?\n\n'
    readme+='Original hypothesis (retained, including falsified components): EDGE dominates accuracy and negative-estimate rate; CS is downward-biased in thin/non-continuous markets; ranking is stable across asset classes but levels diverge most in crypto and small-cap equities.\n\n'
    readme+='**Result hierarchy: Step18 PRIMARY; Step19 ROBUSTNESS; Step20 DIAGNOSTIC.** Step21 formats locked results only. No universal EDGE dominance or MAE/RMSE significance claim. Historical checkpoint instructions in AGENTS.md do not describe the final completed phase; later explicit user freezes govern.\n\n'
    readme+='Final selected universe (no estimator outcomes used in selection):\n\n'
    universe=[]
    for cls,tiers in spec['liquidity_tiers'].items():
        for tier,assets in tiers.items():universe.append(dict(asset_class=cls,tier=tier,assets=', '.join(assets)))
    readme+=format_md(pd.DataFrame(universe))+'\n\n'
    readme+='FX remains **IN_SCOPE_BUT_BLOCKED_OFFICIAL_SOURCE_ACCESS**, not an intentional class exclusion or zero-sized observed sample. No substitute source.\n\n'
    calendars=pd.DataFrame([dict(asset_class=cls,**{k:v for k,v in x.items() if k in ['start','end','exact_common_dates','potential_design_eligible_asset_days']}) for cls,x in spec['primary_calendar_by_class'].items()])
    readme+='Frozen primary calendars (not a balanced all-class 2015–2025 panel):\n\n'+format_md(calendars)+'\n\n'
    readme+='Sources: existing shared RiskLab/First Rate one-minute files only for intraday data. Stock/ETF estimator inputs are student-acquired Bloomberg adjusted daily OHLC (CapChg=T, CshAdjNormal=T, CshAdjAbnormal=UNKNOWN); unadjusted Bloomberg is robustness only. Local equity aggregates are validation, not assumed Bloomberg equivalents. Futures use exact provider-mapped unadjusted individual contracts and verified overnight sessions, never continuous adjusted prices. Crypto uses validated UTC daily/minute panels on a common provider quote basis; formal currency UNKNOWN. Shared provider raw data are referenced, not copied.\n\n'
    readme+='Method: asset-day is the observational unit. Stocks/ETFs use 09:30≤America/New_York time<16:00; crypto UTC days; selected futures primary dates use previous 18:00 through trade-date 17:00, excluding maintenance. No missing-minute filling, gap bridging or date compression. Roll uses simple exact-adjacent one-minute returns, physical three-close covariance pairs, lag 1, ddof=1, mathematical minimum two pairs, gamma<0 -> 2 sqrt(-gamma); otherwise undefined/NaN. CS uses overnight-adjusted intervals on (t−1,t) and (t,t+1), flooring each before averaging. AR uses the close-t two-day moment and sqrt(max(s2,0)); EDGE uses the frozen centered three-session RMS mapping and published zero floor. Finite negative raw estimates remain defined; failures stay NaN.\n\n'
    readme+=f'Primary design N={design:,}; exact common-defined accuracy N={n:,}. Common means design eligible AND all four outputs defined; every contributing asset-day has equal weight. Failure denominators are all design days; negative-rate denominators are method-specific finite raw-computable days. Overall Roll undefinedness is {100*roll.failure_rate:.2f}% ({int(roll.failure_N):,}/{design:,}); ETF availability is especially low.\n\n'
    readme+='Primary overall results (bps; saved Step18, no recalculation):\n\n'+format_md(overall[['estimator','bias_bps','hac_se_bps','ci95_low_bps','ci95_high_bps','p_value_two_sided','mae_bps','rmse_bps','N_asset_days']])+'\n\n'
    readme+='EDGE has the lowest overall MAE and RMSE in this frozen sample. ETFs favor CS on both metrics; stocks are mixed (EDGE MAE, CS RMSE); futures and crypto favor EDGE on both. Rankings therefore differ across classes. CS LOW-tier bias is positive in all four classes, contrary to the original downward-bias expectation. EDGE has the lowest overall raw-negative rate, but CS is lower in futures and crypto. Error levels are heterogeneous rather than universally ordered. Rankings are descriptive: HAC inference is for signed bias only, using count-weighted date means, Bartlett L=min(floor(4(T/100)^(2/9)),T−1), no small-sample correction and normal-reference intervals/p-values.\n\n'
    readme+='Robustness: overall EDGE leadership survives applicable R25/R50, equal-asset and alternative-convention accuracy checks. Stock RMSE is sensitive to leaving out SNDL, and stock EDGE MAE loses leadership under abs-root. Thin ETF quality cells become tiny or unavailable. Unadjusted comparisons use matched dates; the independently saved SNDL split boundary breaks crossing unadjusted windows only; heuristic corporate-action flags remain diagnostics. These do not replace the primary specification.\n\n'
    readme+='Cross-fitted diagnostic: fixed HGB models predict signed and absolute errors, not new spreads. Five chronological date blocks, exact input-interval purging, 1% date embargo, training-only preprocessing and test-only permutation importance. Daily range/open-close conditions are consistent predictors; class heterogeneity matters for EDGE; tier adds little stable conditional importance. Lagging features preserves considerable predictability. Block cross-fitting is ex-post, not forward-only forecasting; correlated features and shared OHLC inputs limit causal interpretation. See saved performance/importance tables for negative class R² and unstable ranks.\n\n'
    readme+='Limitations:\n\n'+notes+'\n\n'
    readme+='Repository: src/ reusable construction/estimation/presentation; tests/; docs/ original project briefs; manifests/ lineage and attrition; outputs/results/{primary,robustness,error_model}/ locked aggregates; outputs/tables/ and outputs/figures/ final exhibits; outputs/reproducibility/ guides/checksums; ignored data/raw_bloomberg/, data/interim/, data/analytic/ licensed inputs and granular derived evidence.\n\n'
    readme+='Reproduction: `.venv/Scripts/python.exe -B src/final_artifacts.py --run-tests` rebuilds presentation from locked results. `.venv/Scripts/python.exe -B src/reproduce_final_results.py` independently replays frozen-derived result aggregation without overwriting Steps18–20. Full-from-source order, licensed-data prerequisites, frozen metadata bundle and exact environment are in [the reproduction guide](outputs/reproducibility/final_reproduction_guide.md). This repository alone cannot reproduce licensed observations.\n\n'
    readme+='Data/license: publish code, methodology, aggregated tables, figures and small reproducibility metadata only. Do not distribute raw Bloomberg/First Rate values, observation/error/prediction panels or fitted models. Preserve student-extracted Bloomberg raw acquisition unchanged in the student personal Google Drive; shared RiskLab sources are referenced, never duplicated; derived data are reproducible from raw+code+frozen metadata. No data were uploaded or copied to Drive by this step.\n\n'
    readme+='Publication gate: the legacy executed exploratory notebook and pilot_schema.csv embedded raw provider excerpts. Both local originals are retained unchanged and removed from the Git index; use notebooks/01_initial_exploratory_analysis_code_only.ipynb for code sharing. Old Git commits still contain those excerpts. Publish a clean export/release without old history, or separately authorize history cleanup before publishing this repository history. Step21 did not rewrite commits. See outputs/reproducibility/licensed_data_remediation.json.\n'
    (PROJECT/'README.md').write_text(readme,encoding='utf-8')
    decisions=[
        ('Steps1–3 / Step10.1','Roll benchmark','One-minute close simple-return Roll proxy; exact adjacency, physical pairs, ddof=1, minimum two; nonnegative gamma undefined','Proxy selected without estimator performance; minimum is computability, not precision','PRIMARY'),
        ('Steps2/5/11.3/12.2/14','Sessions','Equity RTH; crypto UTC; verified root-specific futures 18:00–17:00 trade date','No midnight futures day, filling, gap bridging or undocumented session extrapolation','PRIMARY'),
        ('Steps4/7A/7A.1/9/11.3/12','Universe and liquidity','2024 turnover medians within class, deterministic tiers and rank-quantile selection; frozen security-type corrections','No benchmark/estimator selection criterion; REIT/ADS retained; IMDX source-defined history','PRIMARY'),
        ('Step10.2.1','Bloomberg daily source','Adjusted primary, unadjusted robustness; abnormal setting UNKNOWN','Common source across methods; no inferred Bloomberg default','PRIMARY / ROBUSTNESS'),
        ('Steps5/11.3','Futures contracts and calendar','Provider trade-date mapping selects one individual unadjusted contract; no cross-contract estimator window; 2024 all-nine primary','Avoid stitching/back adjustment and calendar/product-composition confounding','PRIMARY'),
        ('Steps12/12.2','Crypto quote and calendar','Verified common provider quote basis, formal currency UNKNOWN; exact nine-way valid UTC intersection','Do not relabel USD; historical extras supplementary only','PRIMARY'),
        ('Steps13/14','FX access','In scope but blocked official sharing/synchronization access; no substitutes','Unavailable source is not a zero sample or intentional class deletion','PRIMARY scope limitation'),
        ('Step14','Common-defined and attrition','Design eligible independent of outputs; common conjunction of Roll/CS/AR/EDGE definedness','Identical accuracy rows, no extra quality/pair/size/zero filter','PRIMARY'),
        ('Step15','Estimator mathematics and mappings','CS overnight-adjusted separately floored paired intervals; AR close-t two-day; EDGE centered three-session paper zero-floor','Literal frozen kernels with explicit project daily mapping; no tuning to provider results','PRIMARY'),
        ('Step15','Negative and failure denominators','Finite raw-negative stays defined; failures/all design; negatives/finite raw-computable design','Do not conflate negative, undefined and zero','PRIMARY'),
        ('Step16','Weighting and HAC','Equal asset-day; WLS date means weighted n_t; Bartlett count-only lag; uncorrected sandwich; normal 95% bias CI/p-value','Preserve pooled point estimand while addressing aggregate date dependence; no MAE/RMSE test','PRIMARY'),
        ('Step16','IMDX identity','Retain source-defined history without OCX stitching; continuity uncertified','Do not fabricate independent identity certification or replace universe after outcomes','PRIMARY'),
        ('Steps17–18','Provider and primary execution','Exact frozen design and common samples; no post-hoc exclusions or metric-difference significance','Outcome audit then primary horse race under prior freezes','PRIMARY'),
        ('Step19','Robustness','R25/R50; equal asset; matched unadjusted with verified split edge; EDGE abs; all asset omissions; single-extreme diagnostic','Prespecified sensitivities never become preferred primary choices; preserve contrary/empty cases','ROBUSTNESS'),
        ('Step20','Error diagnostic','Both targets; fixed 200-iteration HGB; five date blocks; exact purging, 1% embargo; train-only medians/OHE; test-only permutations; scheduled +1 lag','Associations only, no new estimator or hyperparameter/feature search; lagged AR information extended','DIAGNOSTIC'),
        ('Step21','Final presentation freeze','Saved results only; full-range asinh displays; machine-readable source/row/metric ledger','Presentation does not change observations, hypotheses, formulas, inference or result hierarchy','PRESENTATION')]
    log=pd.DataFrame(decisions,columns=['date_or_step','decision','frozen_choice','rationale','role']);log['status']='FROZEN / EXECUTED AS RECORDED'
    text='# Final chronological design decisions\n\nThis is a transcription of existing step-specific decisions, not retrospective optimization. Step identifiers are used where an approval date was not recorded; no supervisor approval/date is invented. Original specifications and Steps18–20 outputs remain immutable. Original hypotheses are retained in docs/project_1.md and README, including falsified components.\n\n'+format_md(log)+'\n\n'+notes+'\n'
    (PROJECT/'design_decisions.md').write_text(text,encoding='utf-8')
    manifest=data_manifest();manifest.to_csv(PROJECT/'data_manifest.csv',index=False);manifest.to_csv(PROJECT/'manifests/data_manifest.csv',index=False)
    tables['appendix_data_lineage_attrition'].to_csv(PROJECT/'manifests/sample_attrition.csv',index=False)
    receipt=dict(approval='Explicit user Step21 documentation authorization; no analytic supersession',authorized_document_paths=DOCS,
        authorized_document_sha256={name:sha256(PROJECT/name) for name in DOCS},historical_test_snapshot='outputs/reproducibility/historical_test_global_design_freeze.py.txt')
    (REPRO/'documentation_transition.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')


def reproduction_guide():
    text='''# Final reproduction guide

Step18 is PRIMARY; Step19 ROBUSTNESS; Step20 DIAGNOSTIC. Step21 performs no estimation or model fitting. Exact frozen metadata and licensed data are prerequisites; GitHub alone is insufficient. FX stays blocked. Do not rerun universe selection or freeze-administration scripts to "refresh" a completed design.

## A. Presentation and saved-output verification (recommended)

1. Restore the private frozen diagnostics/specification bundle plus ignored analytic inputs from the authorized project archive. Retain original relative paths and recorded package versions. This bundle is not raw-data-free: many historical daily panels in outputs/diagnostics are licensed and deliberately ignored.
2. Configure RISKLAB_DATA_ROOT only if source construction is required. Existing raw Bloomberg files remain under data/raw_bloomberg/13-10-2026/, with the three legacy pilot files and original sha256_manifest.csv at their recorded relative locations. Never edit raw workbooks or rerun path-migration administration.
3. `.venv/Scripts/python.exe -B outputs/diagnostics/horse_race/validate_outputs.py`
4. `.venv/Scripts/python.exe -B outputs/diagnostics/robustness/validate_outputs.py`
5. `.venv/Scripts/python.exe -B outputs/diagnostics/error_model/validate_outputs.py`
6. `.venv/Scripts/python.exe -B src/reproduce_final_results.py` replays frozen-derived metric aggregation into ignored staging and compares to original results. It does not overwrite original stages or refit ML; it uses saved cross-fitted predictions.
7. `.venv/Scripts/python.exe -B src/final_artifacts.py --run-tests` rebuilds final tables, figures, docs and master ledger deterministically from saved results.
8. `.venv/Scripts/python.exe -B outputs/diagnostics/final_artifacts/validate_outputs.py` checks final source/row/metric reconciliation, artifact checksums and licensed-data boundaries.

## B. Full-from-source construction (licensed data and frozen metadata required)

Use an isolated replica workspace with the same code/environment, immutable raw sources and frozen metadata bundle. Never experiment in the locked delivery workspace. These expensive commands were NOT run by Step21; full source reproduction is not newly certified here. Keep all prior authoritative result files as read-only comparison references; stage/rebuild granularity before result aggregation.

1. Verify all eleven Bloomberg files against data/raw_bloomberg/sha256_manifest.csv; verify the official First Rate source fingerprints saved by the historical and Step17 runs. Mount the official archive via RISKLAB_DATA_ROOT; no external/minute substitute. Missing licensed inputs block source replay.
2. Rebuild normalized daily Bloomberg inputs with `src/reproduce_final_results.py --ingest-bloomberg-to-staging`. This uses bloomberg_io.read_daily_values on the finalized dated raw VALUES snapshots, with the frozen selected_stocks_etfs.csv; no workbook recalculation or formula/raw edits. Compare staged frames with the normalized inputs before installing them in the isolated replica. The older Step8 CLI assumes pre-migration raw locations and must not be used unmodified for the dated archive.
3. In that replica, reproduce crypto historical daily panels with `.venv/Scripts/python.exe -B src/crypto_historical_materialization.py` and selected futures with `.venv/Scripts/python.exe -B src/futures_historical_sessions.py`. Their frozen metadata dependencies (root mapping, session evidence, selected universe, timezone proof, exact calendars) must be restored. Do not rerun broad universe/session research or extrapolate unresolved historical futures periods. Validate 2024 reconciliations and the exact primary calendars before continuing.
4. `.venv/Scripts/python.exe -B src/provider_run_io.py` constructs/validates individual-asset Roll caches from official minute sources. `.venv/Scripts/python.exe -B src/provider_run.py --run-tests` integrates frozen daily kernels and Roll, with exact design counts and five reproductions. Both require archive access; version-dependent byte/hash mismatches must be investigated, not silently approved or relaxed.
5. For PRIMARY metric reproduction use `.venv/Scripts/python.exe -B src/reproduce_final_results.py` rather than overwrite the archived Step18 lock. Its functions reuse primary_horse_race accuracy/rate/HAC mappings and compare results without changing the baseline manifests.
6. To reconstruct unadjusted robustness source outcomes, call primary_robustness.materialize_unadjusted on the verified provider panel in the replica, then use the result replay. Original executable `src/primary_robustness.py --run-tests` is for a coherent replica with its original prior-stage lock; never replace saved locks to accommodate unexplained differences.
7. Refit the exact Step20 model via `.venv/Scripts/python.exe -B src/cross_fitted_error_model.py --run-tests` in the coherent replica only. Settings, purging, embargo, features and both targets remain fixed. Compare predictions/metrics with the immutable reference bundle, preserving failures and negative results.
8. Run frozen-derived metric replay and presentation checks from route A. Runtime/test-count metadata may differ after new tests, so compare analytic values and frozen inputs separately from execution metadata; do not modify authoritative Steps18–20 in the delivery workspace.

## Licenses and storage

Existing shared RiskLab/First Rate raw data are referenced, not duplicated. Student-extracted Bloomberg raw files must be preserved unchanged in the student's personal Google Drive; this step neither uploads nor copies them. Derived data are reproducible from licensed raw + code + frozen metadata. Granular OHLCV/error/prediction panels, fitted models and historical daily files remain ignored. Only code/tests, methodology, aggregated results, figures and small metadata may be public.

The old executed exploratory notebook and pilot_schema.csv contained raw-row excerpts. Their local originals are unchanged, ignored and removed from the Git index. The separate code-only notebook preserves all source cells with outputs cleared. Old commits STILL contain those excerpts: use a clean export/release excluding old Git history, or obtain separate authorization for history cleanup before publishing history. No commits were rewritten. licensed_data_remediation.json records this distinction; a clean current index does not certify clean history.

## Provenance and environment

final_artifact_manifest.csv lists final artifacts and frozen metadata by relative path, role, SHA-256 and size. It excludes itself to avoid a circular hash. Historical Step14 documentation test was extended only to permit the four explicitly authorized Step21 documentation paths; the original test and its hash remain preserved. No old source/result manifest was rewritten. Full pip environment is saved in environment_requirements.txt; Python/package versions are in environment.json. Dependencies are local scientific Python, including numpy, pandas, pyarrow, matplotlib, openpyxl, PyYAML, scipy, statsmodels, scikit-learn and threadpoolctl. Do not claim reproduction without the licensed archive and private frozen metadata bundle.
'''
    (REPRO/'final_reproduction_guide.md').write_text(text,encoding='utf-8')


def artifact_manifest():
    paths=[PROJECT/name for name in DOCS]+[PROJECT/'manifests/sample_attrition.csv',MASTER]
    paths += [PROJECT/'.gitignore',PROJECT/'notebooks/01_initial_exploratory_analysis_code_only.ipynb']
    paths += [p for folder in [TABLES,FIGURES,REPRO,OUT] for p in folder.iterdir() if p.is_file() and p.name not in ['final_artifact_manifest.csv','run_manifest.json','output_validation.json']]
    paths += list((PROJECT/'src').glob('*.py'))+list((PROJECT/'tests').glob('*.py'))+list((PROJECT/'docs').glob('*.md'))
    paths += list((source.DIAG).rglob('*spec.yaml'))
    paths += [p for folder in [primary.RESULTS,robustness.RESULTS,diagnostic.RESULTS] for p in folder.glob('*.csv')]
    rows=[]
    for p in sorted(set(paths)):
        rows.append(dict(relative_path=p.relative_to(PROJECT).as_posix(),sha256=sha256(p),size_bytes=p.stat().st_size,
            role='private_frozen_specification' if source.DIAG in p.parents else 'code_or_test' if p.suffix=='.py' else 'final_artifact_or_aggregate',
            distribution='PRIVATE_METADATA_BUNDLE' if source.DIAG in p.parents else 'CODE_OR_AGGREGATED_ONLY_NO_LICENSED_OBSERVATIONS'))
    pd.DataFrame(rows).to_csv(REPRO/'final_artifact_manifest.csv',index=False)


def distribution_receipt():
    """Verify local retention and the output-free public notebook; never rewrite Git history."""
    original=PROJECT/'notebooks/01_initial_exploratory_analysis.ipynb'
    clean=PROJECT/'notebooks/01_initial_exploratory_analysis_code_only.ipynb'
    old=json.loads(original.read_text(encoding='utf-8'));new=json.loads(clean.read_text(encoding='utf-8'))
    assert [(c['cell_type'],c['source']) for c in old['cells']]==[(c['cell_type'],c['source']) for c in new['cells']]
    assert all(not c.get('outputs') and c.get('execution_count') is None for c in new['cells'] if c['cell_type']=='code')
    retained=[]
    for name in ['notebooks/01_initial_exploratory_analysis.ipynb','outputs/diagnostics/pilot_schema.csv']:
        p=PROJECT/name
        blob=subprocess.run(['git','show','HEAD:'+name],cwd=PROJECT,capture_output=True,check=True).stdout
        assert blob.decode('utf-8').splitlines()==p.read_text(encoding='utf-8').splitlines(),name
        assert subprocess.run(['git','ls-files','--error-unmatch',name],cwd=PROJECT,capture_output=True).returncode!=0
        assert subprocess.run(['git','check-ignore',name],cwd=PROJECT,capture_output=True).returncode==0
        retained.append(dict(relative_path=name,local_file_retained=True,local_sha256=sha256(p),contents_match_historical_git_blob=True))
    receipt=dict(current_index_raw_excerpts_removed=True,local_originals_unchanged=retained,
        code_only_notebook=clean.relative_to(PROJECT).as_posix(),historical_git_blobs_still_present=True,
        publication_policy='Use a clean release/export excluding old Git history, or separately authorize history cleanup before publishing; no history rewrite was performed')
    (REPRO/'licensed_data_remediation.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')


def run(run_tests=False):
    for folder in [TABLES,FIGURES,REPRO,OUT,MASTER.parent]:folder.mkdir(parents=True,exist_ok=True)
    _,common=inputs();lock=analytic_lock()
    tables=build_tables()
    for name,frame in tables.items():frame.to_csv(TABLES/(name+'.csv'),index=False)
    table_markdowns(tables);build_master(tables);figures(common);documentation(tables);reproduction_guide();distribution_receipt()
    environment=subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,text=True,check=True).stdout
    (REPRO/'environment_requirements.txt').write_text(environment,encoding='utf-8')
    (REPRO/'environment.json').write_text(json.dumps(dict(python=sys.version,numpy=np.__version__,pandas=pd.__version__,matplotlib=matplotlib.__version__),indent=2),encoding='utf-8')
    tests=dict(status='NOT_RUN',passed=0,failed=0)
    if run_tests:
        completed=subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests'],cwd=PROJECT,capture_output=True,text=True)
        output=completed.stdout+completed.stderr;(OUT/'test_results.txt').write_text(output,encoding='utf-8');print(output,flush=True)
        match=re.search(r'Ran (\d+) tests?',output)
        if completed.returncode or not match:raise RuntimeError('Full suite failed')
        tests=dict(status='PASSED',passed=int(match.group(1)),failed=0)
    robustness.check_lock(lock);inputs();raw,_=verify_hashes(PROJECT/'data/raw_bloomberg');require_verified(raw)
    status='FINAL_ANALYTIC_ARTIFACTS_COMPLETE' if run_tests else 'GENERATED_PENDING_FULL_SUITE'
    result=dict(status=status,step=21,tests=tests,analytic_methods_changed=False,prior_steps_18_19_20_unchanged=True,
        raw_bloomberg_hashes_verified=len(raw),full_source_reproduction_run=False,
        code_sha256={p.relative_to(PROJECT).as_posix():sha256(p) for p in [Path(__file__),PROJECT/'tests/test_final_artifacts.py']},prior_lock_sha256=lock)
    (OUT/'run_manifest.json').write_text(json.dumps(result,indent=2),encoding='utf-8');artifact_manifest();print(status)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-tests',action='store_true')
    run(parser.parse_args().run_tests)
