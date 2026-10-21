"""S2-07: heurística de release corretiva (v1) e Change Failure Rate por entrega, variante (b).

Uma release falha quando é seguida, em até 7 dias, por uma release corretiva. O GitHub
não marca releases corretivas, então `eh_corretiva` aplica a heurística v1:

1. Se a tag é SemVer, decide o SemVer: é corretiva quando, em relação à anterior, muda
   apenas o patch (v2.3.0 → v2.3.1), nunca em major ou minor. Sem anterior menor que
   ela (primeira release, backport de uma linha antiga, retag), decide o próprio patch.
2. Se a tag não é SemVer (`2024-05-10`), decidem os commits: é corretiva quando ao
   menos metade das mensagens (primeira linha) cita `fix`, `hotfix` ou `revert` como
   palavra inteira.

Repositórios que mantêm várias linhas ao mesmo tempo (v1.35.x e v1.36.x) intercalam
releases: por isso `cfr_entrega` compara cada release com a anterior da mesma linha
(`major.minor`) e só atribui a falha a uma release da mesma linha da corretiva.

Funções puras, sem rede nem persistência, como em `metrics`.
"""
import re
import hashlib
import inspect
from datetime import timedelta
from .metrics import moment


HEURISTIC_VERSION = "v1"
FAILURE_WINDOW = timedelta(days=7)
# Fração mínima de commits corretivos quando o SemVer não decide.
FIX_COMMIT_SHARE = 0.5
# Prefixo sem dígitos (`v`, `release-`, `pkg@`), núcleo X.Y[.Z] e sufixo SemVer opcional.
SEMVER = re.compile(r"^\D*?(\d+)\.(\d+)(?:\.(\d+))?(?:[-+][0-9A-Za-z.+-]*)?$")
# Fronteira de palavra: não casa com `prefix`, `fixture` ou `bugfix`.
FIX_WORDS = re.compile(r"\b(fix|hotfix|revert)\b", re.IGNORECASE)
# Maior "major" aceito; acima disso a tag é tratada como CalVer (2024.05.10), não SemVer.
MAX_MAJOR = 999


def parse_semver(tag):
    """Versão `(major, minor, patch)` da tag; None quando a tag não é SemVer parseável."""
    match = SEMVER.match(tag.strip()) if isinstance(tag, str) else None
    if match is None:
        return None
    major, minor, patch = (int(part) if part is not None else 0 for part in match.groups())
    return None if major > MAX_MAJOR else (major, minor, patch)


def eh_fix_commit(commit):
    """Commit corretivo: a primeira linha da mensagem cita fix, hotfix ou revert."""
    message = (commit or {}).get("message")
    return isinstance(message, str) and bool(FIX_WORDS.search(message.split("\n", 1)[0]))


def semver_patch_only(release, release_anterior):
    """True/False quando a tag é SemVer; None quando não é e os commits decidem."""
    current = parse_semver((release or {}).get("tag_name"))
    if current is None:
        return None
    previous = parse_semver((release_anterior or {}).get("tag_name"))
    if previous is not None and current > previous:
        return current[:2] == previous[:2]
    return current[2] > 0


def same_line(release, other):
    """Mesma linha `major.minor`; tags fora do SemVer não restringem a comparação."""
    first = parse_semver((release or {}).get("tag_name"))
    second = parse_semver((other or {}).get("tag_name"))
    return first is None or second is None or first[:2] == second[:2]


def eh_corretiva(release, release_anterior, commits):
    """Heurística v1: a release corrige a anterior? Detalhes no docstring do módulo."""
    decided = semver_patch_only(release, release_anterior)
    if decided is not None:
        return decided
    commits = [commit for commit in (commits or []) if commit]
    return bool(commits) and sum(map(eh_fix_commit, commits)) >= FIX_COMMIT_SHARE * len(commits)


def ordered_releases(releases):
    """Releases em ordem de publicação, desempate pelo id; as sem data ficam de fora."""
    dated, undated = [], 0
    for release in releases if releases is not None else []:
        release = release or {}
        when = moment(release.get("published_at"))
        if when is None:
            undated += 1
        else:
            identity = release.get("release_id")
            dated.append((when, identity if isinstance(identity, int) else 0, release))
    dated.sort(key=lambda item: item[:2])
    return [(when, release) for when, _, release in dated], undated


def classify_releases(releases):
    """Aplica a regra com o mesmo predecessor usado no CFR, incluindo backports."""
    ordered, undated = ordered_releases(releases)
    corrective = []
    for index, (_, release) in enumerate(ordered):
        previous = ordered[index - 1][1] if index else {"tag_name": release.get("previous_tag_name")}
        previous = next((earlier for _, earlier in reversed(ordered[:index])
                         if parse_semver(earlier.get("tag_name")) and same_line(release, earlier)), previous)
        corrective.append(eh_corretiva(release, previous, release.get("commits")))
    return ordered, undated, corrective


def rule_fingerprint():
    """Detecta mudança na regra: alterar a implementação exige reavaliação."""
    text = '\n'.join(inspect.getsource(function) for function in
                     (parse_semver, eh_fix_commit, semver_patch_only, same_line, eh_corretiva,
                      ordered_releases, classify_releases))
    text += repr((SEMVER.pattern, SEMVER.flags, FIX_WORDS.pattern, FIX_WORDS.flags,
                  FIX_COMMIT_SHARE, MAX_MAJOR))
    return hashlib.sha256(text.encode()).hexdigest()


def official_version(path):
    """Versão aprovada no config.yaml; None enquanto não houver avaliação humana."""
    import yaml
    try:
        config = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as exc:
        raise ValueError(f'Configuração YAML inválida: {exc}') from exc
    if not isinstance(config, dict) or not isinstance(config.get('heuristica_corretiva'), dict):
        raise ValueError('Configuração sem heuristica_corretiva.')
    section = config['heuristica_corretiva']
    version = section.get('versao_oficial')
    if version is None:
        return None
    if version != HEURISTIC_VERSION:
        raise ValueError(f'Versão oficial não implementada: {version}.')
    evaluation = section.get('avaliacao') or {}
    if not isinstance(evaluation, dict):
        raise ValueError('Registro de avaliação oficial inválido.')
    f1 = evaluation.get('f1')
    if not isinstance(f1, (int, float)) or isinstance(f1, bool) or not 0 <= f1 <= 1:
        raise ValueError('F1 da versão oficial ausente ou inválido.')
    if f1 < 0.70 and not (evaluation.get('justificativa') or '').strip():
        raise ValueError('F1 abaixo de 0,70 sem justificativa documentada.')
    if evaluation.get('regra_sha256') != rule_fingerprint():
        raise ValueError('A regra mudou ou não possui avaliação registrada; reavalie antes de usar.')
    return version


def cfr_entrega(releases, fim_janela):
    """Change Failure Rate (b) = releases que falharam / releases avaliáveis.

    Uma release falha quando alguma release posterior da mesma linha, publicada em até
    7 dias, é corretiva. Releases publicadas nos últimos 7 dias da janela não têm 7 dias
    observados: ficam fora do denominador e são contadas em `censored`. Releases sem
    data entram em `ignored_missing_date`. Sem release avaliável, a taxa é None.

    Cada release é comparada com a anterior mais recente da mesma linha; sem ela, com a
    anterior da lista e, para a primeira, com `previous_tag_name`, que pode estar fora
    da janela.
    """
    ordered, undated, corrective = classify_releases(releases)
    end = moment(fim_janela)
    if end is None:
        raise ValueError("fim_janela precisa ser um instante com fuso horário.")
    result = {"heuristic": HEURISTIC_VERSION, "releases": len(ordered) + undated,
              "ignored_missing_date": undated, "corrective": 0, "evaluated": 0, "failed": 0,
              "censored": 0, "change_failure_rate": None, "details": []}
    result["corrective"] = sum(corrective)
    for index, (when, release) in enumerate(ordered):
        censored = when > end - FAILURE_WINDOW
        fixed_by = None if censored else next(
            (later for (later_when, later), is_fix in zip(ordered[index + 1:], corrective[index + 1:])
             if is_fix and same_line(release, later) and when < later_when <= when + FAILURE_WINDOW), None)
        result["details"].append({
            "repository": release.get("repository"), "release_id": release.get("release_id"),
            "tag_name": release.get("tag_name"), "published_at": release.get("published_at"),
            "corrective": corrective[index], "censored": censored, "failed": fixed_by is not None,
            "fixed_by_tag_name": (fixed_by or {}).get("tag_name")})
        if censored:
            result["censored"] += 1
        else:
            result["evaluated"] += 1
            result["failed"] += int(fixed_by is not None)
    if result["evaluated"]:
        result["change_failure_rate"] = result["failed"] / result["evaluated"]
    return result


def rework_rate(releases):
    """Deployment rework rate (DORA, 2024) = releases corretivas / releases avaliáveis.

    Usa a mesma heurística e o mesmo predecessor do CFR (b) (`classify_releases`), mas mede
    outra coisa: o CFR (b) marca a release que **falhou** (a seguida por uma correção em até
    7 dias); o rework rate marca **a própria correção**, sem janela de tempo. Por isso não
    há censura: nenhuma release fica fora do denominador por ser recente.

    Fica fora do denominador a primeira release da história (`comparison_status` igual a
    `no_previous_release`), que não tem release anterior para ser corrigida, e as releases
    sem data. Ambas são contadas. Sem nenhuma release avaliável, a taxa é None, nunca zero.
    As releases cujo `compare` falhou continuam no denominador, como no CFR (b): a decisão
    por SemVer não depende dos commits, e a de tags fora do SemVer vira "não corretiva"
    por falta de commits, o que subestima a taxa.
    """
    ordered, undated, corrective = classify_releases(releases)
    result = {"heuristic": HEURISTIC_VERSION, "releases": len(ordered) + undated,
              "ignored_missing_date": undated, "no_previous": 0, "evaluated": 0,
              "corrective": 0, "rework_rate": None}
    for (_, release), is_fix in zip(ordered, corrective):
        if release.get("comparison_status") == "no_previous_release":
            result["no_previous"] += 1
            continue
        result["evaluated"] += 1
        result["corrective"] += int(is_fix)
    if result["evaluated"]:
        result["rework_rate"] = result["corrective"] / result["evaluated"]
    return result
