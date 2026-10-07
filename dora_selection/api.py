"""Cliente REST direto, com cache, rate limit, retry e erros explícitos."""
import json
import logging
import os
import re
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


class GitHubClient:
    """Card 4: consulta o cache antes de cada chamada, respeita a cota e repete erros temporários."""

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
        self.stats = {"requests": 0, "cache_hits": 0, "retries": 0, "rate_limit_waits": 0,
                      "rate_limit_remaining": None, "rate_limit_reset": None}

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
                self.stats["cache_hits"] += 1
                return cached
        data, headers = self._request(url, parsed.path)
        if self.cache is not None:
            self.cache.set(url, data, headers)
        return data, headers

    def _request(self, url, path):
        request = Request(url, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Lab03S01-Card4",
        })
        attempt = 0
        while True:
            attempt += 1
            self._wait_for_quota(path)
            try:
                with urlopen(request, timeout=60) as response:
                    headers = dict(response.headers)
                    body = response.read()
                self.stats["requests"] += 1
                self._read_quota(headers)
                return (json.loads(body) if body else [], headers)
            except HTTPError as exc:
                headers = dict(exc.headers or {})
                self._read_quota(headers)
                delay = self._quota_delay(headers, exc.code, path)
                # 4xx sem sinal de cota é definitivo: repetir não muda a resposta.
                if delay is None and exc.code < 500:
                    LOGGER.error("HTTP %s em %s; erro definitivo, sem nova tentativa.", exc.code, path)
                    raise APIError(f"HTTP {exc.code} em {path}", status_code=exc.code) from None
                reason, status = f"HTTP {exc.code}", exc.code
            except ValueError:
                LOGGER.error("JSON inválido em %s.", path)
                raise APIError(f"Falha de conexão ou JSON inválido em {path}") from None
            except (URLError, TimeoutError, OSError) as exc:
                delay, reason, status = None, f"falha de conexão ({type(exc).__name__})", None
            if attempt >= self.max_attempts:
                LOGGER.error("%s em %s após %d tentativa(s); desistindo.", reason, path, attempt)
                raise APIError(f"{reason} em {path} após {attempt} tentativa(s).", status_code=status) from None
            wait = delay if delay is not None else min(self.max_backoff, self.backoff * 2 ** (attempt - 1))
            self.stats["retries"] += 1
            if delay is not None:
                self.stats["rate_limit_waits"] += 1
            LOGGER.warning("%s em %s; tentativa %d de %d em %.1fs.",
                           reason, path, attempt + 1, self.max_attempts, wait)
            self._sleep(wait)

    def _read_quota(self, headers):
        """X-RateLimit-Remaining e X-RateLimit-Reset de cada resposta, inclusive de erro."""
        remaining = integer(header(headers, "X-RateLimit-Remaining"))
        reset = integer(header(headers, "X-RateLimit-Reset"))
        if remaining is not None:
            self.stats["rate_limit_remaining"] = remaining
        if reset is not None:
            self.stats["rate_limit_reset"] = reset

    def _wait_for_quota(self, path):
        remaining, reset = self.stats["rate_limit_remaining"], self.stats["rate_limit_reset"]
        if remaining is None or reset is None or remaining > self.reserve:
            return
        wait = reset - self._now() + 1
        if wait <= 0:
            self.stats["rate_limit_remaining"] = None
            return
        if wait > self.max_wait:
            raise APIError(f"Reset da cota em {wait:.0f}s excede o limite de {self.max_wait:.0f}s.")
        LOGGER.warning("Cota esgotada (%s restantes) antes de %s; aguardando %.0fs até o reset.",
                       remaining, path, wait)
        self.stats["rate_limit_waits"] += 1
        self._sleep(wait)
        # A próxima resposta traz a cota renovada; o valor antigo não vale mais.
        self.stats["rate_limit_remaining"] = None

    def _quota_delay(self, headers, code, path):
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
        self.stats["rate_limit_remaining"] = None
        return wait

    def pages(self, path, params=None, key=None):
        data, headers = self.get(path, {**(params or {}), "per_page": 100})
        while True:
            items = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(items, list):
                raise APIError(f"Resposta inesperada em {path}")
            yield from items
            next_url = links(header(headers, "Link")).get("next")
            if not next_url:
                return
            data, headers = self.get(next_url)
