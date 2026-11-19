"""Descarga de audio con yt-dlp, sin ventanas ni subprocess."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import yt_dlp

AUDIO_EXTS = {".mp3", ".m4a", ".opus", ".ogg", ".flac", ".wav"}


@dataclass
class Progress:
    """Estado puntual de una descarga."""

    status: str  # downloading | converting | tagging
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    title: str = ""


@dataclass
class SearchResult:
    title: str
    url: str
    duration: float | None = None
    uploader: str = ""


def _fmt_size(value: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _fmt_speed(bps: float | None) -> str:
    return f"{_fmt_size(bps)}/s" if bps else ""


def _fmt_eta(seconds: float | None) -> str:
    if not seconds or seconds <= 0:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


class Downloader:
    """Busca en YouTube y guarda el audio en ``outdir``."""

    def __init__(
        self,
        outdir: Path,
        fmt: str = "mp3",
        quality: str = "192",
        cookies_from_browser: str = "",
    ) -> None:
        self.outdir = outdir
        self.fmt = fmt
        self.quality = quality
        self.cookies_from_browser = cookies_from_browser

    def _options(self) -> dict:
        options: dict = {
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 12,
        }
        if self.cookies_from_browser:
            options["cookiesfrombrowser"] = (self.cookies_from_browser,)
        return options

    def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        options = {
            **self._options(),
            "extract_flat": True,
            "skip_download": True,
            "noplaylist": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)

        results: list[SearchResult] = []
        for entry in (info or {}).get("entries") or []:
            if not entry:
                continue
            video_id = entry.get("id")
            url = entry.get("url") or entry.get("webpage_url") or ""
            if video_id and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={video_id}"
            if not url:
                continue
            results.append(
                SearchResult(
                    title=entry.get("title") or "Sin título",
                    url=str(url),
                    duration=entry.get("duration"),
                    uploader=entry.get("uploader") or entry.get("channel") or "",
                )
            )
        return results

    def download(
        self, url: str, on_progress: Callable[[Progress], None]
    ) -> Path:
        self.outdir.mkdir(parents=True, exist_ok=True)

        def hook(data: dict) -> None:
            info = data.get("info_dict") or {}
            title = info.get("title") or ""
            status = data.get("status")
            if status == "downloading":
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                done = data.get("downloaded_bytes") or 0
                percent = (done / total * 100.0) if total else 0.0
                on_progress(
                    Progress(
                        "downloading",
                        percent,
                        _fmt_speed(data.get("speed")),
                        _fmt_eta(data.get("eta")),
                        title,
                    )
                )
            elif status == "finished":
                on_progress(Progress("converting", 100.0, title=title))

        def postprocessor_hook(data: dict) -> None:
            info = data.get("info_dict") or {}
            title = info.get("title") or ""
            status = data.get("status")
            if status == "started":
                on_progress(Progress("converting", 100.0, title=title))
            elif status == "finished":
                on_progress(Progress("tagging", 100.0, title=title))

        options = {
            **self._options(),
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(self.outdir / "%(title)s.%(ext)s"),
            "noprogress": True,
            "noplaylist": True,
            "retries": 3,
            "fragment_retries": 3,
            "concurrent_fragment_downloads": 4,
            "overwrites": False,
            "continuedl": True,
            "progress_hooks": [hook],
            "postprocessor_hooks": [postprocessor_hook],
            "writethumbnail": True,
            "convert_thumbnails": "jpg",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": self.fmt,
                    "preferredquality": self.quality,
                },
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            ],
        }

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            if not info:
                raise RuntimeError("yt-dlp no devolvió información del vídeo")
            path = Path(ydl.prepare_filename(info))

        final = path.with_suffix(f".{self.fmt}")
        if final.exists():
            return final
        if path.exists():
            return path

        # La conversión pudo cambiar el nombre: busca el audio más reciente.
        candidates = [
            item
            for item in self.outdir.iterdir()
            if item.is_file()
            and item.stem == path.stem
            and item.suffix.lower() in AUDIO_EXTS
        ]
        if candidates:
            return max(candidates, key=lambda item: item.stat().st_mtime)
        raise RuntimeError("la descarga terminó pero no encuentro el archivo")
