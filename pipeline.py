"""Comando único do experimento: `python -m pipeline --config config.yaml`.

A seção `coleta` do arquivo de configuração define a janela, a meta e as pastas; o
restante é o pipeline de `dora_selection.pipeline`, cujas opções continuam aceitas
aqui e prevalecem sobre o arquivo.
"""
import argparse
import sys
from pathlib import Path
from dora_selection.pipeline import main as run


OPTIONS = {"inicio": "--start", "fim": "--end", "alvo": "--target", "min_estrelas": "--min-stars",
           "saida": "--output", "processados": "--processed", "tipo_projeto": "--project-types",
           "workers": "--workers"}


def arguments(path):
    """Opções de linha de comando equivalentes à seção `coleta` da configuração."""
    import yaml
    try:
        config = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Configuração ilegível em {path}: {exc}") from exc
    section = config.get("coleta") if isinstance(config, dict) else None
    if not isinstance(section, dict):
        raise ValueError(f"{path}: seção coleta ausente.")
    unknown = sorted(set(section) - set(OPTIONS))
    if unknown:
        raise ValueError(f"{path}: opções desconhecidas em coleta: {', '.join(unknown)}.")
    result = ["--config", str(path)]
    for key, value in section.items():
        if value is not None:
            result += [OPTIONS[key], str(value)]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m pipeline", description="Lab03 — coleta, métricas DORA e dataset final",
        epilog="Demais opções são repassadas a dora_selection.pipeline e prevalecem sobre a configuração.")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args, extra = parser.parse_known_args(argv)
    try:
        configured = arguments(args.config)
    except (ValueError, ImportError) as exc:
        parser.error(str(exc))
    return run(configured + extra)


if __name__ == "__main__":
    sys.exit(main())
