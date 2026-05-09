"""Генератор MP3-метрономов через ffmpeg.

Без ffmpeg в системе скрипт мягко завершится с инструкцией; ничего не
ломает. CI его не запускает, чтобы не плодить артефакты в репо — он для
локальной сборки `make metronome`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "audio"

BPMS = (100, 110, 120)
DURATION_SECONDS = 60
CALM_BPM = 6
CALM_DURATION = 90


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _make_click(bpm: int, duration: int, out: Path) -> None:
    interval = 60.0 / bpm
    click_filter = f"sine=f=1100:d=0.05," f"adelay=0|0," f"apad=pad_dur={interval - 0.05:.6f}"
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        click_filter,
        "-t",
        f"{interval:.6f}",
        "-ar",
        "44100",
        "-ac",
        "1",
        f"{out.with_suffix('.tick.wav')}",
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    list_path = out.with_suffix(".list.txt")
    repeats = max(int(duration / interval), 1)
    list_path.write_text(
        "\n".join(f"file '{out.with_suffix('.tick.wav').name}'" for _ in range(repeats)),
        encoding="utf-8",
    )

    final_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "5",
        str(out),
    ]
    subprocess.run(final_cmd, check=True, capture_output=True, cwd=str(out.parent))

    out.with_suffix(".tick.wav").unlink(missing_ok=True)
    list_path.unlink(missing_ok=True)


def main() -> int:
    if not _have_ffmpeg():
        print(
            "ffmpeg не установлен. Поставь его (Ubuntu: sudo apt-get install ffmpeg)\n"
            "и запусти `python tools/generate_metronome.py` ещё раз.\n"
            "Альтернативно — скачай готовые mp3 (см. audio/README.md).",
            file=sys.stderr,
        )
        return 1
    AUDIO.mkdir(exist_ok=True)
    for bpm in BPMS:
        out = AUDIO / f"metronome_{bpm}.mp3"
        print(f"Генерирую {out}…")
        _make_click(bpm, DURATION_SECONDS, out)
    calm = AUDIO / f"metronome_{CALM_BPM}.mp3"
    print(f"Генерирую {calm} (медленный тон для panic-режима)…")
    _make_click(CALM_BPM, CALM_DURATION, calm)
    print("Готово. Положи коммит файлов из audio/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
