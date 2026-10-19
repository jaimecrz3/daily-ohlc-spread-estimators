"""Packaging only: preserve results, assemble exhibits and audit publication files."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from zipfile import ZipFile

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/diagnostics/publication'
REPRO=ROOT/'outputs/reproducibility'
OFFENDING=['notebooks/01_initial_exploratory_analysis.ipynb','outputs/diagnostics/pilot_schema.csv']


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):return subprocess.run(['git',*args],cwd=ROOT,capture_output=True,check=True).stdout.decode('utf-8').strip()


def initial_lock():
    path=OUT/'frozen_packaging_lock.json'
    if path.exists():return json.loads(path.read_text())
    files=[]
    for directory in ['outputs/results','outputs/tables','outputs/figures']:
        files += [p for p in (ROOT/directory).rglob('*') if p.is_file()]
    files += list((ROOT/'data/raw_bloomberg').rglob('*'))
    files += [ROOT/p for p in ['paper/final_paper_draft.md','paper/paper_claims_audit.csv','presentation/MMF1941_Project1_Final_Presentation.pptx','README.md','design_decisions.md']]
    for directory in ['horse_race','robustness','error_model']:
        files += [p for p in (ROOT/'outputs/diagnostics'/directory).iterdir() if p.is_file()]
    lock={p.relative_to(ROOT).as_posix():sha(p) for p in files if p.is_file()}
    path.write_text(json.dumps(lock,indent=2),encoding='utf-8')
    return lock


def check_lock():
    for name,expected in initial_lock().items():
        if name=='README.md' and (OUT/'readme_original.md').exists():
            original=(OUT/'readme_original.md').read_text(encoding='utf-8')
            current=(ROOT/name).read_text(encoding='utf-8')
            assert original.split('Publication gate:')[0]==current.split('Publication gate:')[0]
        else:assert sha(ROOT/name)==expected,name


def audit():
    OUT.mkdir(parents=True,exist_ok=True);initial_lock();check_lock()
    head=git('rev-parse','HEAD');tracked=git('ls-tree','-r','--name-only','HEAD').splitlines()
    records=[]
    secret=re.compile(r'ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----')
    for name in tracked:
        payload=subprocess.run(['git','show','HEAD:'+name],cwd=ROOT,capture_output=True,check=True).stdout
        reasons=[]
        if name in OFFENDING:reasons.append('Confirmed embedded licensed raw excerpts; exact historical path')
        if name.startswith('data/') or Path(name).suffix.lower() in ['.xlsx','.xls','.xlsm','.parquet','.feather','.joblib','.pickle','.pkl']:reasons.append('Forbidden provider/binary path')
        if secret.search(payload.decode('utf-8',errors='ignore')):reasons.append('Potential credential; values withheld')
        records.append(dict(path=name,sha256=hashlib.sha256(payload).hexdigest(),status='EXCLUDE' if reasons else 'REVIEWED_SAFE',reason='; '.join(reasons) or 'Code, aggregated evidence, methodology or project document'))
    pd.DataFrame(records).to_csv(REPRO/'publication_file_review.csv',index=False)
    text='# Publication content audit\n\n'
    text+=f'Initial HEAD: `{head}`. HEAD files reviewed: {len(records)}. The working tree contains the completed, previously uncommitted study; it is understood and retained.\n\n'
    text+='Review inventory: [publication_file_review.csv](publication_file_review.csv). Secret-pattern scanning reports file paths only; no credential material is reproduced. Aggregate tables/results are retained. Office containers were checked for embedded workbooks; the final presentation has no embedded workbook payload. The public notebook copy has no executed output.\n\n'
    text+='Exact historical exclusions (verified by Git log, not inferred names):\n\n'+''.join('- `'+p+'`\n' for p in OFFENDING)
    text+='\nOther previously tracked diagnostics contain checkpoint metadata, not raw rows; they will be untracked under the new private-diagnostics policy without deleting local files. No broad history purge of data folders or notebooks is authorized or performed.\n\nPublication-safe status: pending exact-path history cleanup and final staged-tree audit. The external private bundle must never be uploaded to GitHub or the submission package because it preserves the original licensed history.\n'
    (REPRO/'publication_audit.md').write_text(text,encoding='utf-8')
    return records


def safe_specs():
    files=list((ROOT/'outputs/diagnostics').rglob('*spec.yaml'))
    for p in files:
        text=p.read_text(encoding='utf-8')
        assert not re.search(r'sample_raw_rows_json|last_raw_row_json|BEGIN PRIVATE KEY',text)
        target=ROOT/'config/frozen'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
        if p.name=='fx_final_spec.yaml':
            import yaml
            public=yaml.safe_load(text)
            public['official_path']='${RISKLAB_DATA_ROOT}/intraday_data/fx'
            public['access_error']='Official shared folder unavailable at design freeze; machine-specific path retained only in the private original access audit.'
            target.write_text(yaml.safe_dump(public,sort_keys=False,allow_unicode=True),encoding='utf-8')
    names=['outputs/diagnostics/final_universe/selected_stocks_etfs.csv',
        'outputs/diagnostics/final_universe/crypto_final/selected_crypto.csv',
        'outputs/diagnostics/final_universe/crypto_final/selection_audit.csv']
    names += [p.relative_to(ROOT).as_posix() for p in (ROOT/'outputs/diagnostics/design_freeze').glob('*_primary_calendar.csv')]
    for name in names:
        p=ROOT/name
        if not p.exists():raise FileNotFoundError(name)
        columns=pd.read_csv(p,nrows=0).columns
        assert not set(columns)&{'open','high','low','close','volume','roll_spread_bps','prediction'}
        target=ROOT/'config/frozen'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    review_names=[
        'outputs/diagnostics/estimator_freeze/step15_estimator_freeze_review.md',
        'outputs/diagnostics/daily_input_freeze/daily_input_convention_review.md',
        'outputs/diagnostics/benchmark_freeze/benchmark_definition_review.md',
        'outputs/diagnostics/statistical_freeze/step16_final_pre_estimation_freeze.md',
        'outputs/diagnostics/horse_race/step18_primary_horse_race_review.md',
        'outputs/diagnostics/robustness/step19_robustness_review.md',
        'outputs/diagnostics/error_model/step20_cross_fitted_error_model_review.md']
    mapping={}
    for name in review_names:
        target=ROOT/'docs/frozen'/Path(name).name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,target);mapping['../'+name]='../'+target.relative_to(ROOT).as_posix()
    for p in files:mapping['../'+p.relative_to(ROOT).as_posix()]='../config/frozen/'+p.relative_to(ROOT).as_posix()
    (ROOT/'config/frozen_specification_inventory.csv').parent.mkdir(exist_ok=True)
    pd.DataFrame([dict(relative_path=p.relative_to(ROOT).as_posix(),sha256=sha(p),role='Safe specification or selected-universe/calendar metadata; FX path/error only portability-redacted, original private file unchanged') for p in (ROOT/'config/frozen').rglob('*') if p.is_file()]).to_csv(ROOT/'config/frozen_specification_inventory.csv',index=False)
    return mapping


def paper():
    mapping=safe_specs()
    draft=(ROOT/'paper/final_paper_draft.md').read_text(encoding='utf-8')
    text=draft
    text=text.replace('The existing publication gate for legacy raw excerpts in Git history remains unresolved: use a clean release/export or separately authorized history cleanup before publishing that history.',
        'Repository publication and history-cleanup status is recorded separately in outputs/reproducibility/git_history_cleanup_report.md; provider observations are not included in the public paper.')
    for old,new in mapping.items():text=text.replace('('+old+')','('+new+')')
    # Verbatim frozen exhibits; only their outer heading level is normalized.
    insertions={
        '## 4. Primary Results': [('Table 1. Estimator definitions and usable observations','table1_estimator_definitions_and_coverage.md')],
        '## 5. Robustness and Falsification': [('Table 2. Primary horse race','table2_primary_horse_race.md'),('Table 3. Failures, raw negatives and influence','table3_failure_negative_decomposition.md')],
        '## 6. Cross-Fitted Error Diagnostics': [('Table 4. Prespecified robustness and diagnostic summary','table4_robustness_falsification.md')],
        '## References': [('Appendix Table. Data lineage and attrition','appendix_data_lineage_attrition.md')]}
    for before,items in insertions.items():
        added=''
        for title,filename in items:
            exhibit=(ROOT/'outputs/tables'/filename).read_text(encoding='utf-8').split('\n',1)[1]
            # Technical column names wrap more legibly with spaces; values are untouched.
            exhibit='\n'.join(line.replace('_',' ') if line.startswith('|') else line for line in exhibit.splitlines())
            added+='\n\n### '+title+'\n\n'+exhibit+'\n\n'
        text=text.replace(before,added+before)
    figures=[('figure1_estimator_vs_roll','Estimator versus Roll; full common-defined sample, basis points. Both axes use the labeled asinh display; no observations clipped.'),
        ('figure2_error_distribution','Signed-error distributions; full-range ECDF, basis points. The zero-error reference is retained.'),
        ('figure3_relative_performance','Primary MAE and RMSE by class and liquidity tier. Panel scales differ; ranks are descriptive.'),
        ('figure4_benchmark_coverage','Roll undefinedness and pair-coverage sensitivities. The right panel is robustness evidence, not the primary sample.'),
        ('figure5_error_predictors','Secondary diagnostic: absolute-error permutation importance, mean and fold standard deviation, not confidence intervals or causal effects.')]
    for i,(stem,caption) in enumerate(figures,1):
        pattern=re.compile(r'(?m)^.*\[Figure '+str(i)+r'\]\(\.\./outputs/figures/'+stem+r'\.png\).*$')
        match=pattern.search(text)
        assert match,(i,stem)
        paragraph_end=text.find('\n\n',match.end())
        if paragraph_end<0:paragraph_end=match.end()
        block=f'\n\n### Figure {i}. {caption}\n\n![Figure {i}. {caption}](../outputs/figures/{stem}.png)\n\n'
        text=text[:paragraph_end]+block+text[paragraph_end:]
    # Published source refers to portable public reviews rather than ignored diagnostic paths.
    for target in re.findall(r'\]\(([^)]+)\)',text):
        assert not re.match(r'[A-Za-z]:[\\/]',target)
        assert (ROOT/'paper'/target).resolve().exists(),target
        assert 'outputs/diagnostics/' not in target or target.startswith('../config/frozen/')
    source=ROOT/'paper/MMF1941_Project1_Final_Paper.md';source.write_text(text,encoding='utf-8')
    import pypandoc
    pandoc=pypandoc.get_pandoc_path()
    subprocess.run([pandoc,str(source),'-o',str(source.with_suffix('.docx')),'--resource-path='+str(ROOT)+';'+str(ROOT/'paper'),'--standalone'],cwd=ROOT,check=True,capture_output=True)
    format_docx(source.with_suffix('.docx'))
    check_lock()


def format_docx(path):
    from docx import Document
    from docx.shared import Inches,Pt
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    doc=Document(path)
    normal=doc.styles['Normal'];normal.font.name='Times New Roman';normal.font.size=Pt(11)
    normal.paragraph_format.space_after=Pt(6)
    for section in doc.sections:
        section.page_width=Inches(8.5);section.page_height=Inches(11)
        section.top_margin=section.bottom_margin=Inches(.7)
        section.left_margin=section.right_margin=Inches(.7)
    def section_break(landscape):
        p=OxmlElement('w:p');pp=OxmlElement('w:pPr');sp=OxmlElement('w:sectPr')
        typ=OxmlElement('w:type');typ.set(qn('w:val'),'nextPage');sp.append(typ)
        size=OxmlElement('w:pgSz');size.set(qn('w:w'),'15840' if landscape else '12240');size.set(qn('w:h'),'12240' if landscape else '15840')
        if landscape:size.set(qn('w:orient'),'landscape')
        sp.append(size);mar=OxmlElement('w:pgMar')
        for k,v in dict(top=1008,bottom=1008,left=1008,right=1008,header=360,footer=360,gutter=0).items():mar.set(qn('w:'+k),str(v))
        sp.append(mar);pp.append(sp);p.append(pp);return p
    # Every table receives a landscape section. No row content or numeric value changes.
    for t in doc.tables:
        t._tbl.addprevious(section_break(False));t._tbl.addnext(section_break(True))
        t.autofit=False
        cols=len(t.columns);widths=[9.6/cols]*cols
        if cols==9:widths=[1.1,.6,.65,.85,.7,.65,.65,1.05,3.35]
        elif cols>=10:widths=[9.6/cols]*cols
        for idx,col in enumerate(t.columns):col.width=Inches(widths[idx])
        for ri,r in enumerate(t.rows):
            if ri==0:
                header=OxmlElement('w:tblHeader');r._tr.get_or_add_trPr().append(header)
            for ci,c in enumerate(r.cells):
                c.width=Inches(widths[ci])
                for p in c.paragraphs:
                    p.paragraph_format.space_after=Pt(3)
                    for run in p.runs:run.font.size=Pt(8 if cols>=9 else 9)
        borders=OxmlElement('w:tblBorders')
        for edge in ['top','left','bottom','right','insideH','insideV']:
            border=OxmlElement('w:'+edge);border.set(qn('w:val'),'single');border.set(qn('w:sz'),'4');border.set(qn('w:color'),'B0B0B0');borders.append(border)
        t._tbl.tblPr.append(borders)
    for shape in doc.inline_shapes:
        maxw=Inches(7.0);maxh=Inches(8.3)
        ratio=min(maxw/shape.width,maxh/shape.height)
        shape.width=int(shape.width*ratio);shape.height=int(shape.height*ratio)
    for p in doc.paragraphs:
        if p.style.name.startswith('Heading'):
            p.paragraph_format.keep_with_next=True
            if p.text.startswith('Figure '):p.paragraph_format.page_break_before=True
    doc.save(path)


def html_for_pdf():
    import pypandoc
    from lxml import html,etree
    source=ROOT/'paper/MMF1941_Project1_Final_Paper.md'
    completed=subprocess.run([pypandoc.get_pandoc_path(),str(source),'-t','html5','--standalone','--resource-path='+str(ROOT)],capture_output=True,check=True,cwd=ROOT)
    document=html.fromstring(completed.stdout)
    for anchor in document.xpath('//a'):
        if not anchor.get('href','').startswith(('https://','http://')):anchor.drop_tag()
    for image in document.xpath('//img'):
        image.set('src',(ROOT/'paper'/image.get('src')).resolve().as_uri())
    # Keep each full exhibit's caption, panels and notes in the same print
    # section; do not leave captions alone on portrait pages.
    for heading in list(document.xpath('//h3')):
        if not heading.text_content().startswith(('Table ','Appendix Table.')):continue
        wrapper=etree.Element('div',{'class':'wide-table'})
        heading.addprevious(wrapper);current=heading
        while current is not None and (current is heading or current.tag not in ['h1','h2','h3']):
            following=current.getnext();wrapper.append(current);current=following
    for t in document.xpath('//table'):
        heads=[h.text_content().lower() for h in t.xpath('.//thead//th')]
        if 'source result file' in heads and 'denominator n' in heads:
            # Reflow the lineage exhibit: repeated group metadata becomes a
            # full-width paragraph, while every stage/count/denominator remains.
            groups={}
            for r in t.xpath('./tbody/tr'):
                vals=[c.text_content() for c in r]
                groups.setdefault(vals[0],[]).append(vals)
            container=etree.Element('div',{'class':'lineage-groups'})
            for cls,rows in groups.items():
                h=etree.SubElement(container,'h4');h.text='Asset class: '+cls
                p=etree.SubElement(container,'p')
                p.text='; '.join(heads[i]+': '+rows[0][i] for i in [1,2,3,4,5])
                nt=etree.SubElement(container,'table',{'class':'lineage-table'})
                header=etree.SubElement(etree.SubElement(nt,'thead'),'tr')
                indices=[6,7,8,9,10]
                for i in indices:etree.SubElement(header,'th').text=heads[i]
                body=etree.SubElement(nt,'tbody')
                for vals in rows:
                    nr=etree.SubElement(body,'tr')
                    for i in indices:etree.SubElement(nr,'td').text=vals[i]
            t.addprevious(container);t.getparent().remove(t)
            continue
        if heads==['variant','asset class','liquidity tier','affected scope','sample n display','mae leader','rmse leader','primary conclusion changed','notes']:
            rows=[[c.text_content() for c in r] for r in t.xpath('./tbody/tr')]
            nt=etree.Element('table',{'class':'robustness-table'})
            header=etree.SubElement(etree.SubElement(nt,'thead'),'tr')
            indices=[0,1,2,4,5,6,7]
            for i in indices:etree.SubElement(header,'th').text=heads[i]
            body=etree.SubElement(nt,'tbody')
            for vals in rows:
                nr=etree.SubElement(body,'tr')
                for i in indices:etree.SubElement(nr,'td').text=vals[i]
                note=etree.SubElement(etree.SubElement(body,'tr'),'td',colspan='7')
                note.text='Scope: '+vals[3]+'. Notes: '+vals[8]
            t.addprevious(nt);t.getparent().remove(t)
            continue
        if 'notes' in heads:
            group=etree.Element('colgroup')
            for h in heads:
                col=etree.SubElement(group,'col')
                col.set('style','width:30%' if h=='notes' else 'width:20%' if h=='source result file' else 'width:15%' if h in ['source role','variant'] else 'width:auto')
            existing=t.find('colgroup')
            if existing is not None:t.remove(existing)
            t.insert(0,group)
    css='''@page {size:letter;margin:0.65in} @page wide {size:letter landscape;margin:0.55in}
body {font:11pt Georgia,"Times New Roman",serif;line-height:1.28;color:#111;max-width:none;margin:0}
h1 {font-size:21pt;line-height:1.15} h2 {font-size:15pt;margin-top:20pt} h3 {font-size:11pt;line-height:1.2}
h1,h2,h3 {break-after:avoid} p {orphans:3;widows:3} a {color:inherit;text-decoration:none}
.wide-table {page:wide;break-before:page;break-after:page} table {page:wide;border-collapse:collapse;width:100%;font:9pt Georgia,serif;table-layout:auto}
.lineage-table th:nth-child(2),.lineage-table td:nth-child(2),.lineage-table th:nth-child(4),.lineage-table td:nth-child(4) {min-width:45pt;white-space:nowrap}
.lineage-table th:first-child {width:20%} .lineage-table th:last-child {width:42%}
th,td {border:0.5pt solid #aaa;padding:4pt;overflow-wrap:anywhere;vertical-align:top} th {font-weight:bold;background:#eee}
thead {display:table-header-group} tr {break-inside:avoid} img {display:block;max-width:100%;max-height:8in;width:auto;height:auto;margin:auto}
figure {margin:0;break-inside:avoid} figcaption {font-size:9pt;line-height:1.15}
'''
    style=etree.Element('style');style.text=css;document.find('head').append(style)
    target=OUT/'final_paper_print.html';target.write_bytes(etree.tostring(document,encoding='utf-8',method='html',doctype='<!DOCTYPE html>'))
    # Keep the optional DOCX consistent with the same readable layout reflow.
    docx=ROOT/'paper/MMF1941_Project1_Final_Paper.docx'
    subprocess.run([pypandoc.get_pandoc_path(),str(target),'-o',str(docx),'--standalone'],cwd=ROOT,capture_output=True,check=True)
    format_docx(docx)
    print(target)


def documentation():
    current=(ROOT/'README.md').read_text(encoding='utf-8')
    if not (OUT/'readme_original.md').exists():(OUT/'readme_original.md').write_text(current,encoding='utf-8')
    original=(OUT/'readme_original.md').read_text(encoding='utf-8')
    current=original.split('Publication gate:')[0]+'''Publication gate: release/history checks are recorded in [the publication audit](outputs/reproducibility/publication_audit.md) and [history-cleanup report](outputs/reproducibility/git_history_cleanup_report.md). The executed legacy notebook and pilot raw-row schema remain private local originals; the public notebook is output-free. The external recovery bundle contains original licensed history and must never be published. The final [paper PDF](paper/MMF1941_Project1_Final_Paper.pdf), [portable paper source](paper/MMF1941_Project1_Final_Paper.md) and [final presentation](presentation/MMF1941_Project1_Final_Presentation.pptx) are publication artifacts. See [delivery and reproduction notes](docs/PUBLICATION.md).\n'''
    (ROOT/'README.md').write_text(current,encoding='utf-8')
    receipt_path=REPRO/'documentation_transition.json'
    old=REPRO/'step21_documentation_transition_original.json'
    if not old.exists():shutil.copy2(receipt_path,old)
    receipt=json.loads(old.read_text())
    receipt['authorized_document_sha256']['README.md']=sha(ROOT/'README.md')
    receipt['publication_amendment']='Explicit Step24 publication authorization; only README publication-gate paragraph changed. Original Step21 receipt preserved separately; empirical prose and all numbers untouched.'
    receipt_path.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    publication='''# Publication and delivery

The analytical results are frozen. Publication tooling does not estimate spreads, fit models, change samples or reselect assets. The README empirical content is unchanged; only its administrative publication-gate paragraph was updated. The original Step21 documentation receipt is retained alongside the explicit publication amendment.

Final paper: `paper/MMF1941_Project1_Final_Paper.md`, `.pdf` and the optional `.docx`. Final presentation: `presentation/MMF1941_Project1_Final_Presentation.pptx`. The paper draft, its claims audit, aggregate results and all frozen figures remain unchanged. Public copies of method reviews are under `docs/frozen/`; small frozen configurations and selected-universe/calendar metadata are under `config/frozen/`. Only the public FX configuration path/error is portability-redacted; the original private freeze is untouched and FX remains blocked.

Shared First Rate/RiskLab raw files are referenced through RISKLAB_DATA_ROOT and are never duplicated. Personal Bloomberg raw data are excluded from GitHub and copied byte-for-byte only into the authorized private Drive submission. Restoring licensed raw sources is required for source reproduction. The code and public aggregates alone cannot reproduce granular observations.

## Drive package layout and reproduction

The requested delivery layout puts code under `code/` and outputs/data at package root. For source reproduction, create an independent local repository-shaped workspace: copy the CONTENTS of `code/` into that workspace, then copy package `outputs/`, `paper/`, `presentation/` and personally acquired `data/raw_bloomberg/` into its root. Do not execute the source pipeline in the delivery directory. Never duplicate the shared First Rate archive: configure RISKLAB_DATA_ROOT to its official mounted location.

Safe metadata in `config/frozen/` mirrors original relative paths; restore needed specifications, selected lists and exact calendars to their original locations under ignored `outputs/diagnostics/` before source construction. The safe specification inventory records checksums and the FX-only portability amendment. Historical scripts also require their recorded stage/provenance metadata and reconstruct their granular outputs from licensed inputs; missing metadata must be investigated, never invented or bypassed. No hidden interim, analytic, prediction or fitted-model panels are included in delivery.

Follow the full-source order in `outputs/reproducibility/final_reproduction_guide.md` in that isolated workspace. Frozen-derived verification is a separate route for an existing licensed working archive. Full source reconstruction was not rerun or newly certified at publication. Historical artifact manifests remain records of earlier stages; `release_artifact_manifest.csv` is the publication checksum inventory. Packaging checks do not rewrite old analytical locks to accommodate differences.

The private Git bundle is recovery-only and excluded from both release and submission. Rewriting branch history does not change GitHub visibility settings or guarantee removal of provider excerpts from external clones, caches or pre-existing pull requests. No credentials or private acquisition observations belong in the public tree.
'''
    (ROOT/'docs/PUBLICATION.md').write_text(publication,encoding='utf-8')
    guide=REPRO/'final_reproduction_guide.md'
    saved=OUT/'reproduction_guide_original.md'
    if not saved.exists():shutil.copy2(guide,saved)
    guide.write_text(saved.read_text(encoding='utf-8')+'\n\n## Publication-stage addendum\n\n'+publication+'\n',encoding='utf-8')
    check_lock()


def candidates():
    names=git('ls-files','--cached','--others','--exclude-standard').splitlines()
    allowed=[];review=[]
    secret=re.compile(rb'ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----')
    rawline=re.compile(rb'20\d\d-\d\d-\d\d [012]\d:[0-5]\d:[0-5]\d,\d+\.\d+,\d+\.\d+,\d+\.\d+')
    for name in sorted(set(names)):
        p=ROOT/name
        if not p.is_file():continue
        assert not name.startswith(('data/','outputs/diagnostics/','outputs/models/','.venv/')) and name not in OFFENDING,name
        assert p.suffix.lower() not in ['.xlsx','.xls','.xlsm','.parquet','.feather','.pkl','.pickle','.joblib'],name
        data=p.read_bytes()
        if p.suffix in ['.pptx','.docx']:
            with ZipFile(p) as archive:
                embedded=[n for n in archive.namelist() if '/embeddings/' in n and not n.endswith('/')]
                assert not embedded,(name,embedded)
                data=b'\n'.join(archive.read(n) for n in archive.namelist() if n.endswith('.xml'))
        assert not secret.search(data),('Potential secret',name)
        assert not rawline.search(data),('Potential minute OHLCV row',name)
        if p.suffix=='.ipynb':
            notebook=json.loads(data)
            assert not any(c.get('outputs') for c in notebook['cells']),name
        if name=='README.md':assert not re.search(rb'\]\([A-Za-z]:[\\/]',data)
        allowed.append(name);review.append(dict(relative_path=name,sha256=sha(p),size_bytes=p.stat().st_size,status='PUBLICATION_SAFE'))
    pd.DataFrame(review).to_csv(REPRO/'publication_candidate_review.csv',index=False)
    (OUT/'publication_candidates.json').write_text(json.dumps(allowed,indent=2),encoding='utf-8')
    print('PUBLICATION_SAFE_CANDIDATES',len(allowed))


def pdf_validation():
    import pymupdf
    pdf=ROOT/'paper/MMF1941_Project1_Final_Paper.pdf';doc=pymupdf.open(pdf)
    text='\n'.join(p.get_text() for p in doc)
    assert len(doc)>5 and sum(len(p.get_images()) for p in doc)==5
    out=[]
    for i,p in enumerate(doc):
        for b in p.get_text('blocks'):
            if b[0]<0 or b[1]<0 or b[2]>p.rect.width+1 or b[3]>p.rect.height+1:out.append(i+1)
        assert not any(str(link.get('uri','')).startswith(('file:','C:')) for link in p.get_links())
    assert not out,out
    for needle in ['Abstract','1. Introduction','8. Conclusion','References','53.59','122.18','24,377','35.93','63.22']:
        assert needle in text,needle
    for i in range(1,6):assert 'Figure '+str(i)+'.' in text
    for i in range(1,5):assert 'Table '+str(i)+'.' in text
    assert 'Appendix Table.' in text
    report=f'''# Final paper validation

PASS. PDF: `paper/MMF1941_Project1_Final_Paper.pdf`; {len(doc)} pages; SHA-256 `{sha(pdf)}`.

Pandoc and a local Microsoft Word export were checked. No LaTeX engine was available; Word's hidden COM export stalled and was stopped. The reliable fallback was Pandoc HTML plus local headless Microsoft Edge PDF printing. The optional DOCX is also retained. No online document conversion was used.

All five frozen figures are embedded, with captions. All four tables and the appendix lineage exhibit are included. Wide tables use landscape print pages and repeated headers. The lineage table repeats common group metadata once per class for legibility; counts, denominators, notes and numeric values are copied unchanged. The administrative history-publication note was updated without changing the paper's empirical prose or numbers. Original draft and claims audit remain unchanged.

Automated QA: no text blocks outside page bounds; no missing images; no file/Windows-local PDF hyperlinks; expected title/abstract/sections/references/appendix and headline values present. Visual QA inspected the complete page contact sheet and enlarged accuracy, robustness and lineage tables. Page orientation changes create some short continuation pages; no table is cut outside the page. Sources are aggregate tables and frozen figures only, not provider observation panels.

Final source: `paper/MMF1941_Project1_Final_Paper.md`. Optional editable copy: `paper/MMF1941_Project1_Final_Paper.docx`. The PDF contains no new estimates, tests or robustness results.
'''
    (REPRO/'final_paper_validation.md').write_text(report,encoding='utf-8')
    print('PAPER_PDF_QA_PASSED',len(doc),'pages')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['audit','paper','html','documentation','pdf-validation','candidates','check'])
    args=parser.parse_args()
    if args.phase=='audit':audit()
    elif args.phase=='paper':paper()
    elif args.phase=='html':html_for_pdf()
    elif args.phase=='documentation':documentation()
    elif args.phase=='pdf-validation':pdf_validation()
    elif args.phase=='candidates':candidates()
    else:check_lock();print('FROZEN_ANALYTIC_AND_RAW_FILES_UNCHANGED')
