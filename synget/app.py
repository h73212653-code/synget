"""SYNGET: descarga música de YouTube a tu carpeta, sin salir del terminal."""

from __future__ import annotations

import os
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.events import Key
from textual.message import Message
from textual.widgets import (
    Footer,
    Input,
    Label,
    OptionList,
    ProgressBar,
    Static,
)
from textual.widgets.option_list import Option

from .downloader import Downloader, Progress, SearchResult

CONFIG_PATH = Path.home() / ".config" / "synget" / "config.toml"


def load_config() -> dict:
    config: dict = {
        "music_dir": "~/Musica",
        "format": "mp3",
        "quality": "192",
        "cookies_from_browser": "",
    }
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("rb") as handle:
                config.update(tomllib.load(handle))
        except (OSError, tomllib.TOMLDecodeError):
            pass
    if os.environ.get("SYNGET_MUSIC_DIR"):
        config["music_dir"] = os.environ["SYNGET_MUSIC_DIR"]
    return config


def is_url(text: str) -> bool:
    return text.startswith(("http://", "https://", "www.")) or "youtu.be/" in text


def format_duration(seconds: float | None) -> str:
    if not seconds:
        return ""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def clean_error(exc: Exception) -> str:
    text = str(exc).strip()
    for prefix in ("ERROR: ", "Error: "):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    text = text.splitlines()[0] if text else "error desconocido"
    if "Sign in to confirm" in text:
        text += " · YouTube pide verificación"
    return text[:160]


@dataclass
class Job:
    id: int
    url: str
    title: str
    status: str = "queued"  # queued | downloading | done | error
    path: Path | None = None
    error: str = ""


class SearchDone(Message):
    def __init__(self, results: list[SearchResult], error: str = "", seq: int = 0) -> None:
        super().__init__()
        self.results = results
        self.error = error
        self.seq = seq


class JobProgress(Message):
    def __init__(self, job_id: int, progress: Progress) -> None:
        super().__init__()
        self.job_id = job_id
        self.progress = progress


class JobDone(Message):
    def __init__(self, job_id: int, path: Path) -> None:
        super().__init__()
        self.job_id = job_id
        self.path = path


class JobFailed(Message):
    def __init__(self, job_id: int, error: str) -> None:
        super().__init__()
        self.job_id = job_id
        self.error = error


class JobRow(Vertical):
    """Una descarga: título, barra de progreso y estado."""

    def __init__(self, job_id: int, title: str) -> None:
        super().__init__(id=f"job-{job_id}", classes="job")
        self.job_id = job_id
        self._initial_title = self._clean(title) or "En cola…"

    def compose(self) -> ComposeResult:
        yield Label(self._initial_title, classes="job-title", id=f"title-{self.job_id}")
        yield ProgressBar(
            total=100,
            show_percentage=False,
            show_eta=False,
            id=f"bar-{self.job_id}",
        )
        yield Label("Preparando…", classes="job-status", id=f"status-{self.job_id}")

    @staticmethod
    def _clean(text: str) -> str:
        return " ".join(text.split())

    def set_title(self, title: str) -> None:
        self.query_one(f"#title-{self.job_id}", Label).update(self._clean(title))

    def set_status(self, text: str) -> None:
        self.query_one(f"#status-{self.job_id}", Label).update(self._clean(text))

    def set_progress(self, percent: float) -> None:
        bar = self.query_one(f"#bar-{self.job_id}", ProgressBar)
        bar.update(total=100, progress=max(0.0, min(100.0, percent)))


class SyngetApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "SYNGET"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Salir"),
        Binding("ctrl+o", "open_folder", "Carpeta"),
        Binding("ctrl+l", "focus_input", "Enlace", show=False),
        Binding("escape", "dismiss", "Limpiar", show=False),
    ]

    def __init__(
        self,
        music_dir: Path,
        fmt: str = "mp3",
        quality: str = "192",
        initial_query: str = "",
        cookies_from_browser: str = "",
    ) -> None:
        super().__init__()
        self.music_dir = music_dir
        self.downloader = Downloader(
            music_dir,
            fmt=fmt,
            quality=quality,
            cookies_from_browser=cookies_from_browser,
        )
        self.initial_query = initial_query
        self.jobs: dict[int, Job] = {}
        self._next_id = 1
        self._active: int | None = None
        self._search_seq = 0

    # ---------------------------------------------------------------- interfaz

    def compose(self) -> ComposeResult:
        with Horizontal(id="banner"):
            yield Static("[b #67e8f9]SYNGET[/] [#64748b]· descarga rápida[/]", id="banner-title")
            yield Static(escape(self._short_dir()), id="banner-path")
        yield Input(
            placeholder="Pega un enlace de YouTube o escribe para buscar…",
            id="query",
        )
        yield Static("", id="notice")
        yield OptionList(id="results")
        with VerticalScroll(id="queue"):
            yield Static(
                "Aún no hay descargas.\nPega un enlace y pulsa Enter.",
                id="empty",
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#query", Input).focus()
        if self.initial_query:
            self._start_search(self.initial_query)
        else:
            self._notice("Pega un enlace y pulsa Enter, o escribe para buscar en YouTube.")

    def _short_dir(self) -> str:
        text = str(self.music_dir)
        home = str(Path.home())
        return text.replace(home, "~", 1)

    def _notice(self, text: str) -> None:
        self.query_one("#notice", Static).update(text)

    # ----------------------------------------------------------------- entrada

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return
        event.input.value = ""
        parts = value.split()
        if parts and all(is_url(part) for part in parts):
            for url in parts:
                self._enqueue(url)
            self._notice(f"{len(parts)} enlace(s) añadido(s) a la cola.")
            return
        if is_url(value):
            self._enqueue(value)
            return
        self._start_search(value)

    def on_key(self, event: Key) -> None:
        """Si escribes con la lista de resultados enfocada, vuelve al buscador."""
        if not event.is_printable or not event.character:
            return
        if not isinstance(self.focused, OptionList):
            return
        query = self.query_one("#query", Input)
        self._hide_results()
        query.focus()
        query.insert_text_at_cursor(event.character)
        event.stop()

    def _start_search(self, query: str) -> None:
        self._hide_results()
        self._notice(f"Buscando «{escape(query)}»…")
        self._search_seq += 1
        self._search_worker(query, self._search_seq)

    @work(thread=True, exclusive=True, group="search")
    def _search_worker(self, query: str, seq: int) -> None:
        try:
            results = self.downloader.search(query)
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            self.post_message(SearchDone([], clean_error(exc), seq))
            return
        self.post_message(SearchDone(results, "", seq))

    def on_search_done(self, message: SearchDone) -> None:
        if message.seq != self._search_seq:
            return
        results = self.query_one("#results", OptionList)
        results.clear_options()
        if message.error:
            self._notice(f"[#f87171]No pude buscar:[/] {escape(message.error)}")
            return
        if not message.results:
            self._notice("[#f59e0b]Sin resultados.[/] Prueba con otras palabras.")
            return
        for item in message.results:
            meta = " · ".join(
                part
                for part in (format_duration(item.duration), item.uploader)
                if part
            )
            prompt = Text(item.title)
            if meta:
                prompt.append(f"\n   {meta}", style="#64748b")
            results.add_option(Option(prompt, id=item.url))
        results.styles.display = "block"
        results.highlighted = 0
        results.focus()
        self._notice(f"{len(message.results)} resultados · Enter para descargar.")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        title = event.option.prompt.plain.splitlines()[0] if event.option.prompt else ""
        if event.option.id:
            self._enqueue(event.option.id, title)
        self._hide_results()
        self.query_one("#query", Input).focus()

    def _hide_results(self) -> None:
        self.query_one("#results", OptionList).styles.display = "none"

    # ------------------------------------------------------------------- cola

    def _enqueue(self, url: str, title: str = "") -> None:
        job = Job(self._next_id, url, title or url)
        self._next_id += 1
        self.jobs[job.id] = job
        self.query_one("#empty", Static).styles.display = "none"
        queue = self.query_one("#queue", VerticalScroll)
        queue.mount(JobRow(job.id, job.title))
        self.call_after_refresh(queue.scroll_end, animate=False)
        self._notice(f"En cola: {escape(job.title)}")
        self._start_next()

    def _start_next(self) -> None:
        if self._active is not None:
            return
        for job in self.jobs.values():
            if job.status == "queued":
                job.status = "downloading"
                self._active = job.id
                self._download_worker(job.id)
                return
        if self.jobs:
            self._notice(
                f"[#34d399]Terminado.[/] {len(self.jobs)} descarga(s) en "
                f"{escape(self._short_dir())}"
            )

    @work(thread=True, group="downloads")
    def _download_worker(self, job_id: int) -> None:
        job = self.jobs[job_id]
        try:
            path = self.downloader.download(
                job.url,
                lambda progress: self.post_message(JobProgress(job_id, progress)),
            )
        except Exception as exc:  # noqa: BLE001 - se muestra al usuario
            self.post_message(JobFailed(job_id, clean_error(exc)))
        else:
            self.post_message(JobDone(job_id, path))

    def on_job_progress(self, message: JobProgress) -> None:
        job = self.jobs.get(message.job_id)
        row = self.query_one(f"#job-{message.job_id}", JobRow)
        progress = message.progress
        if progress.title and job is not None and job.title != progress.title:
            job.title = progress.title
            row.set_title(progress.title)
        if progress.status == "downloading":
            row.set_progress(progress.percent)
            details = [f"{progress.percent:4.0f} %"]
            if progress.speed:
                details.append(progress.speed)
            if progress.eta:
                details.append(f"faltan {progress.eta}")
            row.set_status("  ·  ".join(details))
            row.add_class("active")
        else:
            row.set_progress(100)
            row.set_status("Convirtiendo y añadiendo carátula…")

    def on_job_done(self, message: JobDone) -> None:
        job = self.jobs[message.job_id]
        job.status = "done"
        job.path = message.path
        row = self.query_one(f"#job-{message.job_id}", JobRow)
        row.remove_class("active")
        row.add_class("done")
        row.set_progress(100)
        row.set_status(f"✓ {message.path.name}")
        self._active = None
        self._start_next()

    def on_job_failed(self, message: JobFailed) -> None:
        job = self.jobs[message.job_id]
        job.status = "error"
        job.error = message.error
        row = self.query_one(f"#job-{message.job_id}", JobRow)
        row.remove_class("active")
        row.add_class("error")
        row.set_status(f"✗ {message.error}")
        self._active = None
        self._start_next()

    # ---------------------------------------------------------------- acciones

    def action_focus_input(self) -> None:
        self.query_one("#query", Input).focus()

    def action_dismiss(self) -> None:
        self._hide_results()
        query = self.query_one("#query", Input)
        query.value = ""
        query.focus()
        self._notice("")

    def action_open_folder(self) -> None:
        try:
            subprocess.Popen(
                ["xdg-open", str(self.music_dir)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            self._notice(f"[#f87171]No pude abrir la carpeta:[/] {escape(str(exc))}")


def main() -> None:
    config = load_config()
    music_dir = Path(str(config["music_dir"])).expanduser()
    app = SyngetApp(
        music_dir,
        fmt=str(config.get("format", "mp3")),
        quality=str(config.get("quality", "192")),
        cookies_from_browser=str(config.get("cookies_from_browser", "")),
    )
    app.run()

