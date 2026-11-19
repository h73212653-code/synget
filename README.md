# SYNGET

Descargador de música para el terminal. Pegas un enlace de YouTube (o buscas
por nombre), eliges y el audio acaba en `~/Musica` en MP3 con carátula y
etiquetas, listo para que [SYN](https://github.com/h73212653-code/syn) lo reproduzca.

```
┌ SYNGET · descarga rápida                              ~/Musica ┐
│ Pega un enlace de YouTube o escribe para buscar…              │
│                                                               │
│ ● COQUETA - Fuerza Regida [Slowed + Reverb]                   │
│   ███████████████████░░░░░  78 %   2.1 MB/s   faltan 0:04     │
│   ✓ Baldi's Basics Song - Basics in Behavior.mp3              │
└ ^q Salir            ^o Carpeta                                   ┘
```

## Requisitos

- Python 3.11 o superior
- `ffmpeg` (conversión y carátula)
- `textual`, `yt-dlp` y `mutagen` (se instalan en el entorno virtual)

## Instalación

```bash
cd ~/synget
./install.sh
```

El script crea `.venv`, instala las dependencias y enlaza el lanzador en
`~/.local/bin/synget`. Comprueba que `~/.local/bin` está en el `PATH`.

Si prefieres hacerlo a mano:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
ln -s ~/synget/bin/synget ~/.local/bin/synget
```

## Uso

```bash
synget                          # abre la interfaz
synget "lofi hip hop"           # abre buscando eso
synget "https://youtu.be/..."   # descarga directa, sin interfaz
synget URL1 URL2 URL3           # varias descargas seguidas
```

En la interfaz:

| Tecla | Acción |
| :--- | :--- |
| `Enter` | Buscar, o descargar el enlace pegado |
| `Enter` en un resultado | Añadirlo a la cola |
| `Ctrl+O` | Abrir la carpeta de música |
| `Ctrl+L` | Volver al cuadro de texto |
| `Esc` | Limpiar búsqueda |
| `Ctrl+Q` | Salir |

Puedes pegar varios enlaces a la vez, separados por espacios o saltos de
línea. Las descargas se hacen de una en una y ves el progreso, la velocidad y
el tiempo restante de cada una.

## Configuración

Copia `config.example.toml` a `~/.config/synget/config.toml`:

```toml
music_dir = "~/Musica"
format = "mp3"      # mp3, m4a u opus
quality = "192"     # kbps para mp3; "0" = VBR de máxima calidad
cookies_from_browser = ""   # "firefox", "chrome"… si YouTube pide verificación
```

También puedes cambiar solo la carpeta con `SYNGET_MUSIC_DIR=~/Otra synget`.

## Detalles

- **Una URL = una canción.** Los enlaces de playlist descargan solo el primer
  vídeo. Para varias canciones, pega varias URLs.
- El archivo se guarda con el título del vídeo y lleva carátula y metadatos
  incrustados (título, artista/canal).
- Si el archivo ya existe, no se vuelve a descargar.
- Si YouTube pide verificación («Sign in to confirm you're not a bot»), pon
  `cookies_from_browser = "firefox"` (o tu navegador) en la configuración.
  Actualizar `yt-dlp` también suele resolverlo:
  `.venv/bin/pip install -U yt-dlp`.
- Descarga únicamente contenido que tengas derecho a usar.
