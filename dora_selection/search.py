"""Busca particionada: estrelas e, em faixas saturadas, data de criação."""
from datetime import datetime, timezone
from .api import APIError


class CandidateSearch:
    def __init__(self, client, min_stars=1001):
        self.client = client
        self.min_stars = min_stars
        self.found = 0
        self.unique = 0
        self._seen = set()

    @staticmethod
    def _validate(data):
        if (not isinstance(data, dict) or not isinstance(data.get("items"), list)
                or not isinstance(data.get("total_count"), int)):
            raise APIError("Resposta de busca inválida.")
        if data.get("incomplete_results"):
            raise APIError("Busca incompleta; execute novamente.")

    def candidates(self):
        top, _ = self.client.get("/search/repositories", {
            "q": f"is:public stars:>={self.min_stars}",
            "sort": "stars", "order": "desc", "per_page": 1,
        })
        self._validate(top)
        if not top.get("items"):
            return
        maximum = top["items"][0]["stargazers_count"]
        yield from self._range(self.min_stars, maximum)

    def _range(self, low, high, start=None, end=None):
        query = f"is:public stars:{low}..{high}"
        if start is not None:
            fmt = lambda n: datetime.fromtimestamp(n, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            query += f" created:{fmt(start)}..{fmt(end)}"
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": 100}
        data, _ = self.client.get("/search/repositories", params)
        self._validate(data)
        if data.get("total_count", 0) > 1000:
            if low < high:
                mid = (low + high) // 2
                yield from self._range(mid + 1, high)
                yield from self._range(low, mid)
            else:
                start = start if start is not None else 0
                end = end if end is not None else int(datetime.now(timezone.utc).timestamp())
                if start >= end:
                    raise APIError("Faixa de busca indivisível excede 1000 resultados.")
                mid = (start + end) // 2
                yield from self._range(low, high, mid + 1, end)
                yield from self._range(low, high, start, mid)
            return
        for page in range(1, (data.get("total_count", 0) + 99) // 100 + 1):
            current = data if page == 1 else self.client.get("/search/repositories", {**params, "page": page})[0]
            if current.get("incomplete_results") or not isinstance(current.get("items"), list):
                raise APIError("Página de busca inválida ou incompleta.")
            for repo in current["items"]:
                if not isinstance(repo, dict) or not repo.get("full_name"):
                    raise APIError("Candidato sem identificação na busca.")
                self.found += 1
                identity = repo.get("id") or repo["full_name"].casefold()
                if identity not in self._seen:
                    self._seen.add(identity)
                    self.unique += 1
                    yield repo
