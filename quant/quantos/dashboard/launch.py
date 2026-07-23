"""``quantos-app`` — launch the Streamlit dashboard with one command.

Wraps ``streamlit run <app.py>`` so users never type the path. Two Windows
robustness details matter here:

* Streamlit is launched with the **console** ``python.exe`` (never the
  windowless ``pythonw.exe``); under ``pythonw`` Streamlit can fail to start.
  The child window is hidden with ``CREATE_NO_WINDOW`` so nothing flashes.
* Because the launcher runs silently, its output is written to a **log file**
  (:func:`log_path`) — so when the app doesn't open, the reason is on disk
  instead of lost.

The runner is injectable so the command construction is unit-tested without
Streamlit or a subprocess (I6).
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

__all__ = ["build_command", "log_path", "main"]


def _console_python() -> str:
    """The console interpreter for the child — never ``pythonw.exe``."""
    exe = Path(sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console = exe.with_name("python.exe")
        if console.exists():
            return str(console)
    return sys.executable


def build_command(extra: Sequence[str] = ()) -> list[str]:
    """The ``streamlit run`` argv that opens the app in the browser."""
    app = Path(__file__).resolve().parent / "app.py"
    return [_console_python(), "-m", "streamlit", "run", str(app), *extra]


def log_path() -> Path:
    """Where a silent launch writes its output, for diagnostics."""
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    return base / "quantos" / "last-run.log"


def main(
    argv: Sequence[str] | None = None, runner: Callable[[list[str]], int] | None = None
) -> int:
    """Launch the dashboard; returns the child process's exit code.

    Args:
        argv: extra args forwarded to ``streamlit run``.
        runner: process launcher; injectable so tests never spawn Streamlit.
    """
    extra = list(argv) if argv is not None else sys.argv[1:]
    command = build_command(extra)
    if runner is not None:
        return runner(command)

    import subprocess  # pragma: no cover - real launch path

    log = log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # hide the console on Windows
    try:
        with open(log, "w", encoding="utf-8") as handle:
            handle.write("$ " + " ".join(command) + "\n\n")
            handle.flush()
            return subprocess.call(
                command, stdout=handle, stderr=subprocess.STDOUT, creationflags=flags
            )
    except FileNotFoundError:
        message = (
            "Streamlit no está instalado — vuelve a correr INSTALAR (pip install .[dashboard])."
        )
        log.write_text(message + "\n", encoding="utf-8")
        print(message, file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - record any startup failure to the log
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(f"\nError al iniciar quantos: {exc}\n")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
