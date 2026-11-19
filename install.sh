#!/usr/bin/env bash
# Instala SYNGET en su propio entorno virtual y crea el lanzador.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "Falta ffmpeg: instálalo antes de usar SYNGET." >&2
    echo "  Arch:   sudo pacman -S ffmpeg" >&2
    echo "  Debian: sudo apt install ffmpeg" >&2
    echo "  Fedora: sudo dnf install ffmpeg" >&2
    exit 1
fi

python3 -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install --quiet --upgrade pip
"$ROOT/.venv/bin/pip" install --quiet -r "$ROOT/requirements.txt"

mkdir -p "$HOME/.local/bin"
ln -sfn "$ROOT/bin/synget" "$HOME/.local/bin/synget"

echo "SYNGET instalado."
echo "Ejecuta: synget"
echo "Si «synget» no aparece, añade ~/.local/bin al PATH."
