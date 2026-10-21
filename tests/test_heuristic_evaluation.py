import csv
import json
from copy import deepcopy

import pytest
import yaml

from dora_selection import cfr
from dora_selection.pipeline import compute_dora
from dora_selection.selection import Window, timestamp
from validacao.avaliar_heuristica import (approve, evaluate, main, predict, read_consensus,
                                        read_csv, validate_sample)


def write_csv(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def data(tmp_path):
    sample, consensus, repositories = [], [], []
    for number in range(60):
        name = f'owner/project-{number}'
        releases = []
        for offset in range(5):
            identity = number*5+offset+1
            sample.append({'sample_id': str(number+1), 'repository': name,
                           'release_id': str(identity), 'tag_name': f'build-{offset}',
                           'release_url': f'https://github.com/{name}/releases/tag/build-{offset}',
                           'commits_url': f'https://github.com/{name}/compare/base...build-{offset}'})
            # Por repositório: TP, FP, FN, TN, TN. P=R=F1=0,5.
            consensus.append({'dimension': 'is_corrective', 'level': 'release',
                              'repository': name, 'release_id': str(identity),
                              'label': 'yes' if offset in (0, 2) else 'no'})
            releases.append({'repository': name, 'release_id': identity, 'tag_name': f'build-{offset}',
                             'published_at': f'2025-02-{offset+1:02d}T00:00:00Z',
                             'draft': False, 'prerelease': False, 'comparison_status': 'completed',
                             'commits': [{'message': 'fix: crash' if offset in (0, 1) else 'feat: option'}]})
        # O formato real tem também duas dimensões de repositório.
        for dimension,label in [('project_type','cli'),('releases_represent_deliveries','yes')]:
            consensus.append({'dimension': dimension, 'level': 'repository',
                              'repository': name, 'release_id': '', 'label': label})
        repositories.append({'full_name': name, 'releases': releases, 'errors': []})
    sample_path, consensus_path = tmp_path/'sample.csv', tmp_path/'consenso.csv'
    write_csv(sample_path, sample)
    write_csv(consensus_path, consensus)
    deployments = tmp_path/'deployments.json'
    deployments.write_text(json.dumps(repositories), encoding='utf-8')
    config = tmp_path/'config.yaml'
    config.write_text('heuristica_corretiva:\n  versao_candidata: v1\n  versao_oficial: null\n  avaliacao: null\n', encoding='utf-8')
    history = tmp_path/'versions.md'
    history.write_text('# Histórico sintético\n', encoding='utf-8')
    return sample, consensus, repositories, sample_path, consensus_path, deployments, config, history


def test_long_consensus_and_matrix_orientation(data):
    sample,consensus,_,_,reference_path,deployments,_,_=data
    write_csv(reference_path, list(reversed(consensus)))
    validate_sample(sample)
    report, rows = evaluate(predict(sample, deployments), read_consensus(reference_path, sample))
    assert report['precision'] == report['recall'] == report['f1'] == 0.5
    assert report['confusion_matrix'] == [[120,60],[60,60]]
    assert len(rows) == 300 and report['false_positive'] == report['false_negative'] == 60
    assert not report['threshold_met']


@pytest.mark.parametrize('problem', ['blank','invalid','duplicate','missing','wrong_id','wrong_level'])
def test_invalid_consensus_rejected(data, problem):
    sample,consensus,_,_,path,_,_,_=data
    rows=deepcopy(consensus)
    if problem=='blank': rows[0]['label']=''
    elif problem=='invalid': rows[0]['label']='uncertain'
    elif problem=='duplicate': rows[1]=rows[0].copy()
    elif problem=='missing': rows.pop(0)
    elif problem=='wrong_id': rows[0]['release_id']='999999'
    else: rows[0]['level']='repository'
    write_csv(path,rows)
    with pytest.raises(ValueError): read_consensus(path,sample)


def test_wide_consensus_is_supported(data):
    sample,consensus,_,_,path,_,_,_=data
    rows=[{'repository':r['repository'],'release_id':r['release_id'],'is_corrective':r['label']}
          for r in consensus if r['dimension']=='is_corrective']
    write_csv(path,rows)
    assert len(read_consensus(path,sample))==300


def test_incomplete_non_semver_history_and_wrong_tags_fail(data):
    sample,_,repos,_,_,path,_,_=data
    repos[0]['releases'][0]['comparison_status']='error'
    path.write_text(json.dumps(repos),encoding='utf-8')
    with pytest.raises(ValueError,match='histórico incompleto'): predict(sample,path)
    repos[0]['releases'][0]['comparison_status']='completed'
    repos[0]['releases'][0]['tag_name']='other-build'
    path.write_text(json.dumps(repos),encoding='utf-8')
    with pytest.raises(ValueError,match='tag'): predict(sample,path)


def test_full_history_used_instead_of_only_sampled_releases(tmp_path):
    releases=[{'release_id':1,'tag_name':'v1.4.1','published_at':'2025-01-01T00:00:00Z'},
              {'release_id':2,'tag_name':'v1.5.3','published_at':'2025-01-02T00:00:00Z'}]
    path=tmp_path/'deployments.json'
    path.write_text(json.dumps([{'full_name':'owner/repo','releases':releases}]),encoding='utf-8')
    # Sem a anterior real, o patch próprio 3 resultaria em yes.
    assert cfr.eh_corretiva(releases[1],None,[]) is True
    sample=[{'repository':'owner/repo','release_id':'2','tag_name':'v1.5.3'}]
    assert predict(sample,path)[0]['predicted_corrective']=='no'


def test_no_positive_class_is_zero_and_matrix_remains_two_by_two(data):
    sample,_,_,_,_,path,_,_=data
    predictions=predict(sample,path)
    for row in predictions: row['predicted_corrective']='no'
    reference={(r['repository'],r['release_id']):{'is_corrective':'no'} for r in sample}
    report,_=evaluate(predictions,reference)
    assert report['precision']==report['recall']==report['f1']==0
    assert report['confusion_matrix']==[[300,0],[0,0]]


def test_cli_saves_metrics_errors_history_and_blocks_unjustified_approval(data,tmp_path):
    _,_,_,sample,consensus,deployments,config,history=data
    args=['--sample',str(sample),'--consensus',str(consensus),'--deployments',str(deployments),
          '--config',str(config),'--output',str(tmp_path/'results'),'--history',str(history)]
    assert main(args)==1
    folder=next((tmp_path/'results').iterdir())
    assert len(read_csv(folder/'falsos_positivos.csv'))==60
    assert len(read_csv(folder/'falsos_negativos.csv'))==60
    assert len(read_csv(folder/'predicoes.csv'))==300
    assert read_csv(folder/'matriz_confusao.csv')[0]['previsto_yes']=='60'
    assert 'F1=0.500000' in history.read_text(encoding='utf-8')
    assert cfr.official_version(config) is None
    with pytest.raises(SystemExit): main(args+['--approve'])
    assert cfr.official_version(config) is None


def test_predict_only_cannot_fabricate_metrics_or_approve(data,tmp_path):
    _,_,_,sample,_,deployments,config,history=data
    args=['--sample',str(sample),'--deployments',str(deployments),'--consensus',str(tmp_path/'missing.csv'),
          '--config',str(config),'--output',str(tmp_path/'results'),'--history',str(history)]
    with pytest.raises(SystemExit): main(args)
    assert not (tmp_path/'results').exists()
    assert main(args+['--predict-only'])==0
    folder=next((tmp_path/'results').iterdir())
    report=json.loads((folder/'resultado.json').read_text(encoding='utf-8'))
    assert report['releases']==300 and 'f1' not in report
    assert not (folder/'matriz_confusao.csv').exists()
    assert cfr.official_version(config) is None
    with pytest.raises(SystemExit): main(args+['--predict-only','--approve'])


def test_approval_exceptions_threshold_and_changed_rule(data):
    sample,_,_,_,consensus,path,config,_=data
    report,_=evaluate(predict(sample,path),read_consensus(consensus,sample))
    report['consensus_sha256']='synthetic'
    with pytest.raises(ValueError,match='abaixo'): approve(config,report)
    approve(config,report,'Exceção usada apenas neste teste sintético.')
    assert cfr.official_version(config)=='v1'
    report['f1']=0.70;report['threshold_met']=True
    approve(config,report)
    assert cfr.official_version(config)=='v1'
    section=yaml.safe_load(config.read_text())
    section['heuristica_corretiva']['avaliacao']['regra_sha256']='changed'
    config.write_text(yaml.safe_dump(section),encoding='utf-8')
    with pytest.raises(ValueError,match='mudou'): cfr.official_version(config)


def test_pipeline_cfr_b_uses_shared_release_predictions(data):
    _,_,repos,*_=data
    repo=repos[0]
    window=Window(timestamp('2025-01-01T00:00:00Z'),timestamp('2025-12-31T23:59:59Z'))
    selected=[{'full_name':repo['full_name']}]
    rows,metrics,_=compute_dora(window,selected,[repo],[],corrective_version='v1')
    expected=cfr.cfr_entrega(repo['releases'],window.end)
    assert metrics[0]['change_failure_rate_b']==expected
    assert rows[0]['cfr_b']==expected['change_failure_rate']
    assert rows[0]['cfr_b_version']=='v1'
    with pytest.raises(ValueError,match='não implementada'):
        compute_dora(window,selected,[repo],[],corrective_version='unknown')
