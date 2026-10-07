"""Card 4: cache local das respostas, retomada por diário, logs e opções de linha de comando."""
import hashlib
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from .api import APIError, LOGGER, header


class ResponseCache:
    """Respostas GET em arquivos JSON, com escrita atômica para sobreviver a interrupções."""

    def __init__(self, directory, ttl=0):
        self.directory = Path(directory)
        self.ttl = max(0, int(ttl))
        self.hits = 0
        self.misses = 0
        self.writes = 0

    @staticmethod
    def normalize(url):
        """A ordem dos parâmetros não muda a resposta; a chave precisa ser a mesma."""
        parts = urlsplit(url)
        query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))

    def _path(self, url):
        digest = hashlib.sha256(self.normalize(url).encode("utf-8")).hexdigest()
        return self.directory / digest[:2] / (digest + ".json")

    def get(self, url):
        """Devolve (data, headers) gravados ou None; entrada ilegível conta como ausência."""
        try:
            entry = json.loads(self._path(url).read_text(encoding="utf-8"))
            if entry["url"] != self.normalize(url):
                raise ValueError("colisão de chave")
            stored_at = float(entry["stored_at"])
            headers = dict(entry["headers"])
            data = entry["data"]
        except FileNotFoundError:
            self.misses += 1
            return None
        except (OSError, ValueError, TypeError, KeyError) as exc:
            LOGGER.warning("Entrada de cache inválida para %s (%s); nova chamada será feita.", url, exc)
            self.misses += 1
            return None
        if self.ttl and time.time() - stored_at > self.ttl:
            self.misses += 1
            return None
        self.hits += 1
        return data, headers

    def set(self, url, data, headers):
        """Só o Link é guardado: cota e datas de uma resposta antiga não valem depois."""
        link = header(headers, "Link")
        entry = {"url": self.normalize(url), "stored_at": time.time(), "data": data,
                 "headers": {"Link": link} if link else {}}
        path = self._path(url)
        temporary = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=path.stem, suffix=".tmp", delete=False) as file:
                temporary = file.name
                json.dump(entry, file, ensure_ascii=False)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, path)
            self.writes += 1
        except (OSError, TypeError, ValueError) as exc:
            LOGGER.warning("Falha ao gravar cache de %s: %s", url, exc)
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


class Checkpoint:
    """Diário append-only: cada unidade concluída é gravada e não é recoletada depois."""

    def __init__(self, path, meta):
        self.path = Path(path)
        self.meta = dict(meta)
        self.loaded = {}
        self.reused = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load()
        self._file = self.path.open("a", encoding="utf-8")
        if not self.path.stat().st_size:
            self._write({"meta": self.meta})

    def _load(self):
        lines = self.path.read_text(encoding="utf-8").splitlines()
        valid = []
        for number, line in enumerate(lines, start=1):
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    raise ValueError("linha não é um objeto")
            except ValueError:
                # Interrupção durante a gravação só pode truncar a última linha.
                if number == len(lines):
                    LOGGER.warning("Última linha de %s está incompleta; descartada na retomada.", self.path)
                    break
                raise APIError(f"Estado corrompido em {self.path}, linha {number}.") from None
            if number == 1:
                if entry.get("meta") != self.meta:
                    raise APIError(f"{self.path} pertence a outra configuração; "
                                   "use --output/--state diferente ou --no-resume.")
            elif isinstance(entry.get("unit"), str) and "result" in entry:
                self.loaded[entry["unit"]] = entry
            valid.append(line)
        if len(valid) != len(lines):
            self.path.write_text("".join(line + "\n" for line in valid), encoding="utf-8")

    def _write(self, entry):
        json.dump(entry, self._file, ensure_ascii=False)
        self._file.write("\n")
        self._file.flush()
        os.fsync(self._file.fileno())

    def done(self, unit):
        """Resultado sem erro de uma execução anterior; None quando é preciso coletar."""
        entry = self.loaded.get(unit)
        if entry is None or not entry.get("complete"):
            return None
        self.reused += 1
        return entry["result"]

    def record(self, unit, result, complete=True):
        self._write({"unit": unit, "complete": bool(complete), "result": result})

    def close(self):
        if not self._file.closed:
            self._file.close()


def configure_logging(path=None, level=logging.INFO):
    """Erros e esperas vão para stderr e, quando pedido, também para arquivo."""
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
        handler.close()
    LOGGER.setLevel(level)
    LOGGER.propagate = False
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    LOGGER.addHandler(stream)
    if path:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(path, encoding="utf-8")
            file_handler.setFormatter(formatter)
            LOGGER.addHandler(file_handler)
        except OSError as exc:
            LOGGER.warning("Sem log em arquivo (%s): %s", path, exc)
    return LOGGER


def add_resilience_arguments(parser):
    """Mesmas opções nos três comandos."""
    parser.add_argument("--cache-dir", help="Cache das respostas (padrão <output>/cache)")
    parser.add_argument("--no-cache", action="store_true", help="Ignorar e não gravar cache")
    parser.add_argument("--cache-ttl", type=int, default=0, help="Validade do cache em segundos; 0 não expira")
    parser.add_argument("--state", help="Diário de retomada (padrão <output>/state.jsonl)")
    parser.add_argument("--no-resume", action="store_true", help="Recoletar tudo, sem usar o diário")
    parser.add_argument("--max-attempts", type=int, default=5, help="Tentativas por chamada, incluindo a primeira")
    parser.add_argument("--backoff", type=float, default=1.0, help="Base do backoff exponencial em segundos")
    parser.add_argument("--max-backoff", type=float, default=60.0, help="Teto de cada espera do backoff")
    parser.add_argument("--max-wait", type=float, default=3600.0, help="Espera máxima aceita por reset de cota")
    parser.add_argument("--rate-limit-reserve", type=int, default=0, help="Chamadas mantidas de reserva na cota")
    parser.add_argument("--log-file", help="Arquivo de log (padrão <output>/collection.log)")


def cache_from_args(args):
    if args.no_cache:
        return None
    return ResponseCache(args.cache_dir or Path(args.output) / "cache", args.cache_ttl)


def client_options(args):
    """Parâmetros de rate limit e retry para o GitHubClient."""
    return {"cache": cache_from_args(args), "max_attempts": args.max_attempts,
            "backoff": args.backoff, "max_backoff": args.max_backoff,
            "max_wait": args.max_wait, "reserve": args.rate_limit_reserve}


def open_checkpoint(args, meta):
    if args.no_resume:
        return None
    return Checkpoint(args.state or Path(args.output) / "state.jsonl", meta)


def collection_report(client, checkpoint=None):
    """Números de cache, cota, retries e retomada para o resumo de cada card."""
    stats = getattr(client, "stats", None)
    report = dict(stats) if isinstance(stats, dict) else {}
    cache = getattr(client, "cache", None)
    if isinstance(cache, ResponseCache):
        report.update(cache_misses=cache.misses, cache_entries_written=cache.writes,
                      cache_directory=str(cache.directory))
    report["resumed_units"] = checkpoint.reused if isinstance(checkpoint, Checkpoint) else 0
    return report
