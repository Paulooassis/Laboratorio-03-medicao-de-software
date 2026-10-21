"""Cliente REST e GraphQL direto, com cache, rate limit, retry e erros explícitos."""
import gzip
import hashlib
import json
import logging
import os
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("dora_selection")


class APIError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def links(value):
    return dict((rel, url) for url, rel in re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', value or ""))


def header(headers, name):
    """Nomes de header não diferenciam maiúsculas; urllib devolve o nome recebido."""
    name = name.lower()
    for key, value in (headers or {}).items():
        if key.lower() == name:
            return value
    return None


def integer(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError, AttributeError):
        return None


GRAPHQL_URL = "https://api.github.com/graphql"


class GitHubClient:
    """Card 4: consulta o cache antes de cada chamada, respeita a cota e repete erros temporários.

    REST e GraphQL têm cotas separadas na API; cada uma é lida e respeitada por conta própria.
    """

    def __init__(self, cache=None, max_attempts=5, backoff=1.0, max_backoff=60.0,
                 max_wait=3600.0, reserve=0, sleep=time.sleep, now=time.time):
        self._token = os.environ.get("GITHUB_TOKEN")
        if not self._token:
            raise APIError("Defina GITHUB_TOKEN no ambiente.")
        if max_attempts < 1 or backoff <= 0 or max_backoff < backoff or max_wait < 0 or reserve < 0:
            raise APIError("Parâmetros de retry/rate limit inválidos.")
        self.cache = cache
        self.max_attempts = max_attempts
        self.backoff = backoff
        self.max_backoff = max_backoff
        self.max_wait = max_wait
        self.reserve = reserve
        self._sleep = sleep
        self._now = now
        # Os coletores podem consultar em paralelo; os contadores são compartilhados.
        self._lock = threading.Lock()
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "rate_limit_waits": 0,
                      "rate_limit_remaining": None, "rate_limit_reset": None,
                      "graphql_requests": 0, "graphql_remaining": None, "graphql_reset": None}

    def get(self, path, params=None):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise APIError("URL fora da API oficial do GitHub.")
        if params:
            url += "?" + urlencode(params)
        if self.cache is not None:
            cached = self.cache.get(url)
            if cached is not None:
                self._count("cache_hits")
                return cached
        data, headers = self._request(url, parsed.path)
        if self.cache is not None:
            self.cache.set(url, data, headers)
        return data, headers

    def graphql(self, query, variables=None):
        """Consulta GraphQL com o mesmo cache, retry e espera de cota das chamadas REST.

        A chave de cache é o hash do corpo: a mesma consulta com as mesmas variáveis não
        é repetida. Erros na resposta não são gravados e viram APIError; a falta de cota
        (`RATE_LIMITED`) espera o reset e tenta de novo.
        """
        body = json.dumps({"query": query, "variables": variables or {}}, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
        key = GRAPHQL_URL + "?body=" + hashlib.sha256(body).hexdigest()
        if self.cache is not None:
            cached = self.cache.get(key)
            if cached is not None:
                self._count("cache_hits")
                return cached[0]
        for attempt in range(1, self.max_attempts + 1):
            data, headers = self._request(GRAPHQL_URL, "/graphql", body, "graphql")
            errors = data.get("errors") if isinstance(data, dict) else [{"message": "resposta inválida"}]
            if not errors:
                if self.cache is not None:
                    self.cache.set(key, data, {})
                return data
            if not any(error.get("type") == "RATE_LIMITED" for error in errors) or attempt == self.max_attempts:
                messages = "; ".join(str(error.get("message")) for error in errors)
                raise APIError(f"GraphQL: {messages}")
            reset = integer(header(headers, "X-RateLimit-Reset"))
            wait = max(0.0, reset - self._now()) + 1 if reset is not None else self.backoff * 2 ** (attempt - 1)
            if wait > self.max_wait:
                raise APIError(f"Reset da cota GraphQL em {wait:.0f}s excede o limite de {self.max_wait:.0f}s.")
            LOGGER.warning("Cota GraphQL esgotada; aguardando %.0fs até o reset.", wait)
            self._count("rate_limit_waits")
            self._sleep(wait)

    def _count(self, name):
        with self._lock:
            self.stats[name] += 1

    def _request(self, url, path, body=None, quota="rate_limit"):
        request = Request(url, data=body, method="POST" if body is not None else "GET", headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            # Páginas de runs e de comparação passam de 1 MB; comprimidas ficam ~10x menores.
            "Accept-Encoding": "gzip",
            "User-Agent": "Lab03S01-Card4",
            **({"Content-Type": "application/json"} if body is not None else {}),
        })
        attempt = 0
        while True:
            attempt += 1
            self._wait_for_quota(path, quota)
            try:
                with urlopen(request, timeout=60) as response:
                    headers = dict(response.headers)
                    body_read = response.read()
                if (header(headers, "Content-Encoding") or "").lower() == "gzip":
                    body_read = gzip.decompress(body_read)
                self._count("requests" if quota == "rate_limit" else "graphql_requests")
                self._read_quota(headers, quota)
                return (json.loads(body_read) if body_read else [], headers)
            except HTTPError as exc:
                headers = dict(exc.headers or {})
                self._read_quota(headers, quota)
                delay = self._quota_delay(headers, exc.code, path, quota)
                # 4xx sem sinal de cota é definitivo: repetir não muda a resposta.
                if delay is None and exc.code < 500:
                    LOGGER.error("HTTP %s em %s; erro definitivo, sem nova tentativa.", exc.code, path)
                    raise APIError(f"HTTP {exc.code} em {path}", status_code=exc.code) from None
                reason, status = f"HTTP {exc.code}", exc.code
            except (ValueError, EOFError):
                LOGGER.error("JSON inválido em %s.", path)
                raise APIError(f"Falha de conexão ou JSON inválido em {path}") from None
            except (URLError, TimeoutError, OSError) as exc:
                delay, reason, status = None, f"falha de conexão ({type(exc).__name__})", None
            if attempt >= self.max_attempts:
                LOGGER.error("%s em %s após %d tentativa(s); desistindo.", reason, path, attempt)
                raise APIError(f"{reason} em {path} após {attempt} tentativa(s).", status_code=status) from None
            wait = delay if delay is not None else min(self.max_backoff, self.backoff * 2 ** (attempt - 1))
            self._count("retries")
            if delay is not None:
                self._count("rate_limit_waits")
            LOGGER.warning("%s em %s; tentativa %d de %d em %.1fs.",
                           reason, path, attempt + 1, self.max_attempts, wait)
            self._sleep(wait)

    def _read_quota(self, headers, quota="rate_limit"):
        """X-RateLimit-Remaining e X-RateLimit-Reset de cada resposta, inclusive de erro.

        `quota` separa a cota REST (`rate_limit`) da GraphQL (`graphql`).
        """
        remaining = integer(header(headers, "X-RateLimit-Remaining"))
        reset = integer(header(headers, "X-RateLimit-Reset"))
        if remaining is not None:
            self.stats[quota + "_remaining"] = remaining
        if reset is not None:
            self.stats[quota + "_reset"] = reset

    def _wait_for_quota(self, path, quota="rate_limit"):
        remaining, reset = self.stats[quota + "_remaining"], self.stats[quota + "_reset"]
        if remaining is None or reset is None or remaining > self.reserve:
            return
        wait = reset - self._now() + 1
        if wait <= 0:
            self.stats[quota + "_remaining"] = None
            return
        if wait > self.max_wait:
            raise APIError(f"Reset da cota em {wait:.0f}s excede o limite de {self.max_wait:.0f}s.")
        LOGGER.warning("Cota esgotada (%s restantes) antes de %s; aguardando %.0fs até o reset.",
                       remaining, path, wait)
        self._count("rate_limit_waits")
        self._sleep(wait)
        # A próxima resposta traz a cota renovada; o valor antigo não vale mais.
        self.stats[quota + "_remaining"] = None

    def _quota_delay(self, headers, code, path, quota="rate_limit"):
        """Espera pedida pela API em 403/429; None quando o erro não é de cota."""
        if code not in (403, 429):
            return None
        retry_after = integer(header(headers, "Retry-After"))
        remaining = integer(header(headers, "X-RateLimit-Remaining"))
        reset = integer(header(headers, "X-RateLimit-Reset"))
        if retry_after is not None:
            wait = max(0, retry_after) + 1
        elif remaining is not None and remaining <= 0 and reset is not None:
            wait = max(0.0, reset - self._now()) + 1
        else:
            return None
        if wait > self.max_wait:
            raise APIError(f"Espera de {wait:.0f}s pedida por {path} excede o limite de {self.max_wait:.0f}s.")
        # A espera até o reset já está contabilizada aqui; não repetir antes da chamada.
        self.stats[quota + "_remaining"] = None
        return wait

    def pages(self, path, params=None, key=None, first_page=None):
        data, headers = first_page if first_page is not None else self.get(path, {**(params or {}), "per_page": 100})
        while True:
            items = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(items, list):
                raise APIError(f"Resposta inesperada em {path}")
            yield from items
            next_url = links(header(headers, "Link")).get("next")
            if not next_url:
                return
            data, headers = self.get(next_url)
