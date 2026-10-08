"""Card 6: classificação DORA (Elite, High, Medium, Low) e casos especiais.

Funções puras sobre os resultados do Card 5: sem rede, sem CLI e sem persistência.
Cada métrica recebe sua própria escala de limites; a classificação geral converte
os quatro níveis em notas (Elite = 4 a Low = 1), tira a mediana e arredonda para
baixo. Métrica sem amostra fica `null` com o motivo explícito, nunca é tratada como
zero nem como Elite, e por isso não entra na mediana.
"""
from dataclasses import dataclass
from math import floor, isfinite
from .metrics import median


ELITE, HIGH, MEDIUM, LOW = "Elite", "High", "Medium", "Low"
LEVELS = (ELITE, HIGH, MEDIUM, LOW)
SCORES = {ELITE: 4, HIGH: 3, MEDIUM: 2, LOW: 1}
BY_SCORE = {score: level for level, score in SCORES.items()}
METRICS = ("deployment_frequency", "lead_time", "change_failure_rate", "recovery_time")

HOUR = 1.0
DAY = 24.0
WEEK = 168.0
MONTH = 720.0
DAYS_PER_WEEK = 7.0
# Mês médio do calendário gregoriano, para converter "uma release por mês" em semanas.
DAYS_PER_MONTH = 365.2425 / 12
DAILY = DAYS_PER_WEEK
WEEKLY = 1.0
MONTHLY = DAYS_PER_WEEK / DAYS_PER_MONTH


@dataclass(frozen=True)
class Scale:
    """Faixas de uma métrica, da melhor para a pior; a última faixa é o resto.

    `higher_is_better` define o sentido da comparação e `inclusive` se o limite
    pertence à faixa. Deployment Frequency usa limites inferiores inclusivos;
    Lead Time e tempo de recuperação, limites superiores exclusivos; Change
    Failure Rate, limites superiores inclusivos.
    """

    metric: str
    unit: str
    higher_is_better: bool
    inclusive: bool
    bands: tuple

    def level(self, value):
        """Nível da faixa em que o valor cai; None quando o valor não é numérico."""
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            return None
        for level, limit in self.bands:
            if limit is None:
                return level
            if self.higher_is_better:
                if value >= limit if self.inclusive else value > limit:
                    return level
            elif value <= limit if self.inclusive else value < limit:
                return level
        return LOW


DEPLOYMENT_FREQUENCY = Scale("deployment_frequency", "releases_per_week", True, True,
                             ((ELITE, DAILY), (HIGH, WEEKLY), (MEDIUM, MONTHLY), (LOW, None)))
# Enunciado: Elite < 1 dia, High < 1 semana, Medium < 30 dias, Low >= 30 dias.
LEAD_TIME = Scale("lead_time", "hours", False, False,
                  ((ELITE, DAY), (HIGH, WEEK), (MEDIUM, MONTH), (LOW, None)))
CHANGE_FAILURE_RATE = Scale("change_failure_rate", "rate", False, True,
                            ((ELITE, 0.15), (HIGH, 0.30), (MEDIUM, 0.45), (LOW, None)))
RECOVERY_TIME = Scale("recovery_time", "hours", False, False,
                      ((ELITE, HOUR), (HIGH, DAY), (MEDIUM, WEEK), (LOW, None)))
SCALES = {scale.metric: scale for scale in
          (DEPLOYMENT_FREQUENCY, LEAD_TIME, CHANGE_FAILURE_RATE, RECOVERY_TIME)}

# Motivos de release sem Lead Time (Card 5) traduzidos para os casos especiais do Card 6.
LEAD_TIME_REASONS = {"no_previous_release": "single_release",
                     "no_comparison": "comparison_unavailable",
                     "no_date": "release_without_date",
                     "no_commits": "releases_without_new_commits",
                     "no_commit_dates": "commits_without_date"}
# Desempate entre motivos com a mesma contagem. A primeira release da janela sempre
# produz `no_previous_release`, que por isso só prevalece quando é o único motivo.
LEAD_TIME_PRIORITY = ("no_commits", "no_comparison", "no_commit_dates", "no_date",
                      "no_previous_release")


def score(level):
    """Nota da classificação: Elite = 4, High = 3, Medium = 2, Low = 1."""
    return SCORES.get(level)


def level_from_score(value):
    """Classificação correspondente a uma nota inteira de 1 a 4."""
    return BY_SCORE.get(value)


def rated(scale, value, basis="value"):
    """Classificação de um valor medido, com a nota correspondente."""
    level = scale.level(value)
    return {"metric": scale.metric, "unit": scale.unit, "value": value, "level": level,
            "score": score(level), "basis": basis if level else None,
            "reason": None if level else "no_value"}


def unmeasured(scale, reason):
    """Métrica sem amostra: fica fora da mediana e registra o motivo."""
    return {"metric": scale.metric, "unit": scale.unit, "value": None, "level": None,
            "score": None, "basis": None, "reason": reason}


def deployment_frequency_rating(frequency):
    """Classifica Deployment Frequency pelas releases por semana da janela.

    Zero release é uma medição válida (Low), não ausência de dados. A métrica só
    fica sem classificação quando a janela não fornece duração em semanas.
    """
    frequency = frequency or {}
    value = frequency.get("releases_per_week")
    if value is None:
        return unmeasured(DEPLOYMENT_FREQUENCY, "no_window")
    return rated(DEPLOYMENT_FREQUENCY, value)


def releases_considered(per_commit):
    """Releases avaliadas pelo Card 5: medidas mais ignoradas por motivo."""
    per_commit = per_commit or {}
    ignored = per_commit.get("releases_ignored") or {}
    measured = per_commit.get("releases_measured") or 0
    return measured, {key: ignored.get(key) or 0 for key in LEAD_TIME_REASONS}


def lead_time_reason(ignored):
    """Motivo predominante da ausência de Lead Time, com ordem de desempate fixa."""
    key = max(LEAD_TIME_PRIORITY,
              key=lambda name: (ignored.get(name, 0), -LEAD_TIME_PRIORITY.index(name)))
    return LEAD_TIME_REASONS[key] if ignored.get(key) else "no_releases"


def lead_time_rating(per_commit, per_release=None):
    """Classifica Lead Time pela mediana por release (variante (a) do enunciado).

    O lead time de uma release vai do commit mais antigo do intervalo até a sua
    publicação. A mediana por commit (variante (b)) serve de alternativa quando a
    por release está ausente. Sem amostra, o motivo aponta o caso especial: release
    única, comparação indisponível, release sem commits novos ou commits sem data.
    """
    value = (per_release or {}).get("median_hours")
    if value is None:
        value = (per_commit or {}).get("median_hours")
        if value is not None:
            return rated(LEAD_TIME, value, "commit_median")
        return unmeasured(LEAD_TIME, lead_time_reason(releases_considered(per_commit)[1]))
    return rated(LEAD_TIME, value, "release_median")


def change_failure_rate_rating(failure_rate):
    """Classifica Change Failure Rate sobre os runs considerados (sucesso + falha).

    Runs ignoráveis — cancelados, pulados, neutros, em andamento ou com conclusão
    desconhecida — ficam fora do denominador. Quando todos os runs são ignoráveis,
    a taxa permanece sem classificação em vez de virar 0% e, com isso, Elite.
    """
    failure_rate = failure_rate or {}
    value = failure_rate.get("change_failure_rate")
    if value is None:
        total = failure_rate.get("total") or 0
        return unmeasured(CHANGE_FAILURE_RATE, "only_ignored_runs" if total else "no_runs")
    return rated(CHANGE_FAILURE_RATE, value)


def episode_list(recovery):
    """Episódios de falha, aceitando o resultado por workflow ou de uma série única."""
    recovery = recovery or {}
    episodes = recovery.get("episodes")
    if isinstance(episodes, list):
        return [episode or {} for episode in episodes]
    return [episode or {} for workflow in (recovery.get("workflows") or [])
            for episode in ((workflow or {}).get("episodes") or [])]


def censored_bound(episodes):
    """Mediana do tempo observado dos episódios nunca recuperados (limite inferior)."""
    return median([episode.get("observed_hours") for episode in episodes
                   if episode.get("censored")])


def recovery_time_rating(recovery):
    """Classifica o tempo de recuperação pela mediana dos episódios recuperados.

    Falha nunca recuperada não é recuperação instantânea nem dado inexistente: o
    episódio é censurado e só informa um limite inferior. Sem nenhum episódio
    recuperado, esse limite classifica a métrica apenas quando já basta para Low;
    nos demais casos a métrica fica sem classificação, com o motivo
    `never_recovered`. Repositório sem falhas não recebe Elite por omissão.
    """
    recovery = recovery or {}
    value = recovery.get("median_recovery_hours")
    if value is not None:
        return rated(RECOVERY_TIME, value, "recovered_median")
    episodes = episode_list(recovery)
    censored = [episode for episode in episodes if episode.get("censored")]
    if censored:
        bound = censored_bound(censored)
        # O limite inferior só decide quando a recuperação já passou do pior limite.
        if RECOVERY_TIME.level(bound) == LOW:
            return rated(RECOVERY_TIME, bound, "censored_lower_bound")
        return unmeasured(RECOVERY_TIME, "never_recovered")
    if episodes:
        return unmeasured(RECOVERY_TIME, "inconsistent_recovery")
    return unmeasured(RECOVERY_TIME, "no_failures")


def overall_classification(ratings):
    """Mediana das quatro classificações, arredondada para baixo.

    Aceita níveis ou notas. Métricas sem classificação não entram na mediana, que
    é calculada sobre as disponíveis; sem nenhuma delas o resultado é `null`.
    """
    scores = []
    for item in ratings if ratings is not None else []:
        value = item.get("score") if isinstance(item, dict) else item
        value = score(value) if isinstance(value, str) else value
        if value in BY_SCORE:
            scores.append(value)
    middle = median(scores)
    rounded = int(floor(middle)) if middle is not None else None
    return {"scores": scores, "classified_metrics": len(scores), "median_score": middle,
            "overall_score": rounded, "overall": level_from_score(rounded)}


def special_cases(metrics, ratings):
    """Casos de borda que afetam os cálculos, contados e nunca silenciados."""
    metrics = metrics or {}
    frequency = metrics.get("deployment_frequency") or {}
    per_commit = metrics.get("lead_time_per_commit") or {}
    per_release = metrics.get("lead_time_per_release") or {}
    failure_rate = metrics.get("change_failure_rate") or {}
    recovery = metrics.get("recovery_time") or {}
    measured, ignored = releases_considered(per_commit)
    releases = measured + sum(ignored.values())
    return {
        # A release sem commits novos continua sendo um deployment para a frequência.
        "deployments_counted": frequency.get("releases") or 0,
        "releases_considered": releases,
        "single_release": releases == 1 or (frequency.get("releases") or 0) == 1,
        "releases_without_previous": ignored["no_previous_release"],
        "releases_without_new_commits": ignored["no_commits"],
        "releases_without_comparison": ignored["no_comparison"],
        "releases_without_commit_dates": ignored["no_commit_dates"],
        "releases_without_date": ignored["no_date"],
        "releases_ignored_by_date": frequency.get("ignored_missing_date") or 0,
        "commits_without_date": per_commit.get("commits_without_date") or 0,
        "negative_lead_times": per_commit.get("negative") or 0,
        "release_lead_time_available": per_release.get("median_hours") is not None,
        "ignored_runs": failure_rate.get("ignored") or 0,
        "considered_runs": failure_rate.get("considered") or 0,
        "only_ignored_runs": bool(failure_rate.get("total")) and not failure_rate.get("considered"),
        "runs_without_date": sum((workflow or {}).get("runs_without_date") or 0
                                 for workflow in (recovery.get("workflows") or [])),
        "failure_episodes": len(episode_list(recovery)),
        "failures_never_recovered": recovery.get("censored") or 0,
        "recoveries_with_inconsistent_dates": recovery.get("inconsistent") or 0,
        # Mediana sobre poucos episódios recuperados tende a subestimar a recuperação.
        "censored_majority": (recovery.get("censored") or 0) > (recovery.get("recovered") or 0),
        "unclassified_metrics": {name: rating["reason"] for name, rating in ratings.items()
                                 if rating["level"] is None},
    }


def classify_repository(metrics, repository=None):
    """Classificação DORA de um repositório a partir de `repository_metrics`."""
    metrics = metrics or {}
    ratings = {
        "deployment_frequency": deployment_frequency_rating(metrics.get("deployment_frequency")),
        "lead_time": lead_time_rating(metrics.get("lead_time_per_commit"),
                                      metrics.get("lead_time_per_release")),
        "change_failure_rate": change_failure_rate_rating(metrics.get("change_failure_rate")),
        "recovery_time": recovery_time_rating(metrics.get("recovery_time")),
    }
    return {"repository": repository or metrics.get("repository"),
            "window_start": metrics.get("window_start"), "window_end": metrics.get("window_end"),
            "ratings": {name: ratings[name] for name in METRICS},
            **overall_classification([ratings[name] for name in METRICS]),
            "special_cases": special_cases(metrics, ratings)}


def classify_sample(classifications):
    """Distribuição por métrica, classificação geral e casos especiais da amostra."""
    rows = [row for row in (classifications if classifications is not None else []) if row]
    distribution = {name: dict({level: 0 for level in LEVELS}, unclassified=0) for name in METRICS}
    overall = dict({level: 0 for level in LEVELS}, unclassified=0)
    cases = {}
    for row in rows:
        for name in METRICS:
            level = (row.get("ratings") or {}).get(name, {}).get("level")
            distribution[name][level if level in SCORES else "unclassified"] += 1
        overall[row.get("overall") if row.get("overall") in SCORES else "unclassified"] += 1
        for key, value in (row.get("special_cases") or {}).items():
            if isinstance(value, bool):
                cases[key] = cases.get(key, 0) + int(value)
            elif isinstance(value, int):
                cases[key] = cases.get(key, 0) + value
    sample = overall_classification([row.get("overall_score") for row in rows])
    return {"repositories": len(rows), "by_metric": distribution, "by_overall": overall,
            "median_score": sample["median_score"], "overall_score": sample["overall_score"],
            "overall": sample["overall"], "classified_repositories": sample["classified_metrics"],
            "special_cases": cases}
