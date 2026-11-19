"""Punto de entrada: ``synget`` abre la TUI o descarga enlaces directos."""

from __future__ import annotations

import sys
from pathlib import Path

from .app import SyngetApp, clean_error, is_url, load_config
from .downloader import Downloader

HELP = """\
SYNGET · descarga música desde YouTube al terminal

Uso:
  synget                     abre la interfaz
  synget «búsqueda»          abre la interfaz buscando eso
  synget URL [URL…]          descarga los enlaces directamente
  synget --help              esta ayuda

Carpeta de destino: ~/Musica (configurable en ~/.config/synget/config.toml)
"""


def _download_cli(urls: list[str]) -> int:
    config = load_config()
    downloader = Downloader(
        Path(str(config["music_dir"])).expanduser(),
        fmt=str(config.get("format", "mp3")),
        quality=str(config.get("quality", "192")),
        cookies_from_browser=str(config.get("cookies_from_browser", "")),
    )

    failures = 0
    for index, url in enumerate(urls, 1):
        print(f"[{index}/{len(urls)}] {url}")
        last_percent = -1
        last_status = ""

        def show(progress) -> None:
            nonlocal last_percent, last_status
            if progress.status == "downloading":
                percent = int(progress.percent)
                if percent != last_percent:
                    last_percent = percent
                    last_status = "downloading"
                    tail = "  ".join(
                        part
                        for part in (
                            progress.speed,
                            f"faltan {progress.eta}" if progress.eta else "",
                        )
                        if part
                    )
                    print(f"\r  {percent:3d} %  {tail:<24}", end="", flush=True)
            elif last_status != "processing":
                last_status = "processing"
                print("\r  Procesando…            ", end="", flush=True)

        try:
            path = downloader.download(url, show)
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            failures += 1
            print(f"\r  ✗ {clean_error(exc)}")
        else:
            print(f"\r  ✓ {path.name}")

    return 1 if failures else 0


def main() -> int:
    args = sys.argv[1:]

    if "-h" in args or "--help" in args:
        print(HELP)
        return 0

    if args and all(is_url(arg) for arg in args):
        return _download_cli(args)

    config = load_config()
    app = SyngetApp(
        Path(str(config["music_dir"])).expanduser(),
        fmt=str(config.get("format", "mp3")),
        quality=str(config.get("quality", "192")),
        initial_query=" ".join(args),
        cookies_from_browser=str(config.get("cookies_from_browser", "")),
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
