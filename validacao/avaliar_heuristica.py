"""S2-08: avaliação da heurística existente contra as 300 decisões de consenso."""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ''):
    sys.path.insert(0, str(ROOT))
from dora_selection import cfr


RULE = ('SemVer: mudança apenas de patch em relação à anterior da mesma linha; '
        'sem anterior menor, patch próprio > 0. Tags não SemVer: ao menos 50% '
        'dos títulos de commits contêm fix, hotfix ou revert como palavra inteira.')


def read_csv(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        header = handle.readline()
        handle.seek(0)
        reader = csv.DictReader(handle, delimiter=';' if header.count(';') > header.count(',') else ',')
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'{path}: cabeçalho vazio ou duplicado.')
        return list(reader)


def identity(row):
    name = (row.get('repository') or '').strip().casefold()
    value = str(row.get('release_id') or '').strip()
    if len(name.split('/')) != 2 or not all(name.split('/')) or not value.isdecimal() or int(value) < 1:
        raise ValueError('Cada release precisa de repository owner/repo e release_id numérico positivo.')
    return name, str(int(value))


def validate_sample(sample):
    keys = [identity(row) for row in sample]
    counts = Counter(name for name, _ in keys)
    if len(sample) != 300 or len(set(keys)) != 300 or len(counts) != 60 or set(counts.values()) != {5}:
        raise ValueError('A amostra deve conter 300 releases únicas: cinco em cada um dos 60 repositórios.')
    if any(not row.get(field) for row in sample for field in ('release_url', 'commits_url')):
        raise ValueError('A amostra precisa preservar os links de release e commits.')


def read_consensus(path, sample):
    rows = read_csv(path)
    if rows and 'dimension' in rows[0]:
        # Formato de validacao.consenso: 60 + 60 + 300 itens; só a terceira dimensão é avaliada.
        rows = [row for row in rows if row.get('dimension') == 'is_corrective']
        if any(row.get('level') != 'release' for row in rows):
            raise ValueError('is_corrective precisa ter level=release no consenso.')
        label_column = 'label'
    else:
        label_column = 'is_corrective'
    reference = {}
    for row in rows:
        key = identity(row)
        label = (row.get(label_column) or '').strip().lower()
        if key in reference:
            raise ValueError(f'Consenso duplicado: {key}.')
        if label not in {'yes', 'no'}:
            raise ValueError(f'{key}: consenso vazio ou inválido; use yes/no.')
        reference[key] = {**row, 'is_corrective': label}
    if len(rows) != 300 or set(reference) != {identity(row) for row in sample}:
        raise ValueError('O consenso deve cobrir exatamente as mesmas 300 releases da amostra.')
    for row in sample:
        for field in ('release_url', 'commits_url'):
            if field in reference[identity(row)] and reference[identity(row)][field] != row[field]:
                raise ValueError(f'{identity(row)}: {field} difere da amostra.')
    return reference


def predict(sample, deployments):
    import ijson
    wanted = {identity(row): row for row in sample}
    names = {key[0] for key in wanted}
    predictions = {}
    with deployments.open('rb') as handle:
        # Mantém os predecessores reais: não compara somente as cinco releases sorteadas.
        for repository in ijson.items(handle, 'item'):
            name = repository['full_name'].casefold()
            if name not in names:
                continue
            ordered, _, flags = cfr.classify_releases(repository.get('releases'))
            for (_, release), flag in zip(ordered, flags):
                key = name, str(release['release_id'])
                if key not in wanted:
                    continue
                if key in predictions:
                    raise ValueError(f'Release coletada duplicada: {key}.')
                row = wanted[key]
                if release.get('tag_name') != row.get('tag_name', row.get('release_tag')):
                    raise ValueError(f'{key}: tag coletada difere da amostra.')
                if release.get('draft') or release.get('prerelease'):
                    raise ValueError(f'{key}: draft/prerelease não pode entrar na avaliação.')
                if cfr.parse_semver(release.get('tag_name')) is None:
                    if release.get('comparison_status') != 'completed':
                        raise ValueError(f'{key}: histórico incompleto de commits para uma tag não SemVer.')
                    commits = release.get('commits')
                    if not isinstance(commits, list) or any(not isinstance(c, dict) or not isinstance(c.get('message'), str) for c in commits):
                        raise ValueError(f'{key}: mensagens de commits ausentes ou inválidas.')
                predictions[key] = 'yes' if flag else 'no'
    if set(predictions) != set(wanted):
        raise ValueError(f'Faltam {len(set(wanted)-set(predictions))} releases na coleta.')
    return [{**row, 'heuristic_version': cfr.HEURISTIC_VERSION,
             'predicted_corrective': predictions[identity(row)]} for row in sample]


def evaluate(predictions, reference):
    from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
    rows = []
    truth, predicted = [], []
    for row in predictions:
        human = reference[identity(row)]['is_corrective']
        automatic = row['predicted_corrective']
        truth.append(int(human == 'yes'))
        predicted.append(int(automatic == 'yes'))
        error = 'FP' if automatic == 'yes' and human == 'no' else 'FN' if automatic == 'no' and human == 'yes' else ''
        rows.append({**row, 'consensus_corrective': human, 'error': error})
    precision, recall, f1, _ = precision_recall_fscore_support(truth, predicted, average='binary', pos_label=1, zero_division=0)
    matrix = confusion_matrix(truth, predicted, labels=[0, 1]).tolist()
    report = {'version': cfr.HEURISTIC_VERSION, 'rule': RULE, 'rule_sha256': cfr.rule_fingerprint(),
              'releases': len(rows), 'positive_support': sum(truth),
              'precision': float(precision), 'recall': float(recall), 'f1': float(f1),
              'threshold_met': bool(f1 >= 0.70), 'confusion_matrix': matrix,
              'matrix_labels': ['no', 'yes'], 'matrix_rows': 'consenso', 'matrix_columns': 'heurística',
              'false_positive': matrix[0][1], 'false_negative': matrix[1][0]}
    return report, rows


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_csv(path, fields, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def save_results(directory, report, rows):
    directory.mkdir(parents=True, exist_ok=False)
    (directory/'resultado.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    save_csv(directory/'predicoes.csv', list(rows[0]), rows)
    if report.get('status') == 'awaiting_consensus':
        return
    for name, error in [('falsos_positivos', 'FP'), ('falsos_negativos', 'FN')]:
        save_csv(directory/f'{name}.csv', list(rows[0]), [row for row in rows if row['error'] == error])
    save_csv(directory/'matriz_confusao.csv', ['consenso', 'previsto_no', 'previsto_yes'], [
        {'consenso': label, 'previsto_no': values[0], 'previsto_yes': values[1]}
        for label, values in zip(['no', 'yes'], report['confusion_matrix'])])


def record_version(path, report, reason, justification):
    text = (f"\n## {report['version']} — {report['evaluated_at']}\n\n"
            f"Regra: {report['rule']}\n\n"
            f"P={report['precision']:.6f}; R={report['recall']:.6f}; F1={report['f1']:.6f}. "
            f"FP={report['false_positive']}; FN={report['false_negative']}; n={report['releases']}.\n\n"
            f"Motivo: {reason}\n\nJustificativa de exceção: {justification or 'Não informada.'}\n\n"
            f"Regra SHA-256: `{report['rule_sha256']}`. Consenso SHA-256: `{report['consensus_sha256']}`. "
            f"Coleta SHA-256: `{report['deployments_sha256']}`.\n\n"
            "Reavaliação após refinamento nesta mesma amostra pode inflar o F1; registrar como ameaça à validade.\n")
    with path.open('a', encoding='utf-8') as handle:
        handle.write(text)


def approve(path, report, justification=''):
    import yaml
    if not report['threshold_met'] and not justification.strip():
        raise ValueError('F1 abaixo de 0,70: refinar a regra ou documentar uma exceção com --justification.')
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    config['heuristica_corretiva'].update({'versao_oficial': report['version'], 'avaliacao': {
        'f1': report['f1'], 'regra_sha256': report['rule_sha256'],
        'consenso_sha256': report['consensus_sha256'], 'justificativa': justification.strip()}})
    path.write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sample', type=Path, default=ROOT/'outputs/gold_sample/sample_releases.csv')
    parser.add_argument('--deployments', type=Path, default=ROOT/'outputs/pipeline/deployments.json')
    parser.add_argument('--consensus', type=Path, default=ROOT/'validacao/consenso.csv')
    parser.add_argument('--output', type=Path, default=ROOT/'validacao/resultados/heuristica')
    parser.add_argument('--history', type=Path, default=ROOT/'validacao/heuristica_versoes.md')
    parser.add_argument('--config', type=Path, default=ROOT/'config.yaml')
    parser.add_argument('--version', choices=[cfr.HEURISTIC_VERSION], default=cfr.HEURISTIC_VERSION)
    parser.add_argument('--predict-only', action='store_true', help='Aplica a regra sem consenso; não calcula P/R/F1 nem aprova versão.')
    parser.add_argument('--approve', action='store_true', help='Registra a versão avaliada como oficial.')
    parser.add_argument('--reason', default='Avaliação inicial da heurística existente.')
    parser.add_argument('--justification', default='')
    args = parser.parse_args(argv)
    if args.predict_only and (args.approve or args.justification):
        parser.error('--predict-only não permite aprovação nem justificativa de exceção.')
    try:
        if not args.predict_only and not args.consensus.is_file():
            raise ValueError('Consenso humano ausente: execute validacao.consenso com as planilhas independentes completas. Use --predict-only apenas para obter as previsões.')
        sample = read_csv(args.sample)
        validate_sample(sample)
        reference = None if args.predict_only else read_consensus(args.consensus, sample)
        predictions = predict(sample, args.deployments)
        if args.predict_only:
            report = {'version': cfr.HEURISTIC_VERSION, 'rule': RULE, 'rule_sha256': cfr.rule_fingerprint(),
                      'releases': len(predictions), 'status': 'awaiting_consensus'}
            rows = predictions
        else:
            report, rows = evaluate(predictions, reference)
        report.update({'evaluated_at': datetime.now(timezone.utc).isoformat(), 'reason': args.reason,
                       'sample_sha256': sha256(args.sample), 'deployments_sha256': sha256(args.deployments)})
        if not args.predict_only:
            report['consensus_sha256'] = sha256(args.consensus)
            report['justification'] = args.justification
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        destination = args.output/f'{args.version}-{stamp}'
        save_results(destination, report, rows)
        if args.predict_only:
            print(f'{len(rows)} previsões geradas em {destination}; consenso ausente, P/R/F1 não calculados.')
            return 0
        record_version(args.history, report, args.reason, args.justification)
        if args.approve:
            approve(args.config, report, args.justification)
        print(f"P={report['precision']:.4f}; R={report['recall']:.4f}; F1={report['f1']:.4f}. Resultados: {destination}")
        if not report['threshold_met']:
            print('F1 abaixo de 0,70: analisar os erros, implementar uma nova versão e reavaliar.')
        return 0 if report['threshold_met'] or (args.approve and args.justification.strip()) else 1
    except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    sys.exit(main())
