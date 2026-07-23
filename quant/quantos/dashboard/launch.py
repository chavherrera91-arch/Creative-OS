"""``quantos-app`` — launch the Streamlit dashboard with one command.

Wraps ``streamlit run <app.py>`` so users never type the path. The runner is
injectable so the command construction is unit-tested without Streamlit or a
subprocess (I6).
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from pathlib import Path

__all__ = ["build_command", "main"]


def build_command(extra: Sequence[str] = ()) -> list[str]:
    """The ``streamlit run`` argv that opens the app in the browser."""
    app = Path(__file__).resolve().parent / "app.py"
    return [sys.executable, "-m", "streamlit", "run", str(app), *extra]


def main(
    argv: Sequence[str] | None = None, runner: Callable[[list[str]], int] | None = None
) -> int:
    """Launch the dashboard; returns the child process's exit code.

    Args:
        argv: extra args forwarded to ``streamlit run`` (after ``--``).
        runner: process launcher (``subprocess.call`` by default); injectable
            so tests never spawn Streamlit.
    """
    extra = list(argv) if argv is not None else sys.argv[1:]
    command = build_command(extra)
    if runner is None:  # pragma: no cover - real launch path
        import subprocess

        try:
            return subprocess.call(command)
        except FileNotFoundError:
            print(
                "Streamlit is not installed — run: pip install -e '.[dashboard]'",
                file=sys.stderr,
            )
            return 1
    return runner(command)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
