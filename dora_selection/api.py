"""Cliente REST direto, com paginação e erros explícitos."""
import json
import os
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class APIError(RuntimeError):
    pass


def links(header):
    return dict((rel, url) for url, rel in re.findall(r'<([^>]+)>;\s*rel="([^"]+)"', header or ""))


class GitHubClient:
    def __init__(self):
        self._token = os.environ.get("GITHUB_TOKEN")
        if not self._token:
            raise APIError("Defina GITHUB_TOKEN no ambiente.")

    def get(self, path, params=None):
        url = path if path.startswith("https://") else "https://api.github.com" + path
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.github.com":
            raise APIError("URL fora da API oficial do GitHub.")
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Lab03S01-Card1",
        })
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read()
                return (json.loads(body) if body else [], dict(response.headers))
        except HTTPError as exc:
            raise APIError(f"HTTP {exc.code} em {parsed.path}") from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise APIError(f"Falha de conexão ou JSON inválido em {parsed.path}") from None

    def pages(self, path, params=None, key=None):
        data, headers = self.get(path, {**(params or {}), "per_page": 100})
        while True:
            items = data.get(key) if key and isinstance(data, dict) else data
            if not isinstance(items, list):
                raise APIError(f"Resposta inesperada em {path}")
            yield from items
            next_url = links(headers.get("Link", headers.get("link", ""))).get("next")
            if not next_url:
                return
            data, headers = self.get(next_url)
