"""The desktop installer writes the right double-click launcher per OS (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

import install_desktop as ins


@pytest.mark.parametrize(
    ("system", "name", "needle"),
    [
        ("Darwin", "quantos.command", "quantos.dashboard.launch"),
        ("Windows", "quantos.vbs", "quantos.dashboard.launch"),
        ("Linux", "quantos.desktop", "[Desktop Entry]"),
    ],
)
def test_write_launcher_per_os(tmp_path: Path, system: str, name: str, needle: str) -> None:
    launcher = ins.write_launcher(tmp_path, tmp_path / "python.exe", system)
    assert launcher.name == name
    assert needle in launcher.read_text()


def test_windows_launcher_is_silent(tmp_path: Path) -> None:
    """The Windows launcher hides the console: pythonw + WScript Run ..., 0."""
    launcher = ins.write_launcher(tmp_path, tmp_path / "python.exe", "Windows")
    text = launcher.read_text()
    assert "WScript.Shell" in text
    assert "pythonw.exe" in text  # no black console window
    assert ", 0, False" in text  # hidden window, don't wait


def test_unix_launchers_are_executable(tmp_path: Path) -> None:
    for system in ("Darwin", "Linux"):
        launcher = ins.write_launcher(tmp_path, tmp_path / "py", system)
        assert launcher.stat().st_mode & 0o111  # has an execute bit


def test_no_install_needs_an_existing_venv(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    # With --no-install and a missing venv it fails loudly instead of guessing.
    code = ins.main(["--no-install", "--venv", str(tmp_path / "absent")])
    assert code == 1
    assert "entorno" in capsys.readouterr().out.lower()
