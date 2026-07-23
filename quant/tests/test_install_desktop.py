"""The desktop installer writes the right double-click launcher per OS (offline)."""

from __future__ import annotations

from pathlib import Path

import pytest

import install_desktop as ins


@pytest.mark.parametrize(
    ("system", "name", "needle"),
    [
        ("Darwin", "quantos.command", "quantos.dashboard.launch"),
        ("Windows", "quantos.bat", "quantos.dashboard.launch"),
        ("Linux", "quantos.desktop", "[Desktop Entry]"),
    ],
)
def test_write_launcher_per_os(tmp_path: Path, system: str, name: str, needle: str) -> None:
    python = tmp_path / "py"
    launcher = ins.write_launcher(tmp_path, python, system)
    assert launcher.name == name
    assert needle in launcher.read_text()
    assert str(python) in launcher.read_text()  # points at the venv's interpreter


def test_unix_launchers_are_executable(tmp_path: Path) -> None:
    for system in ("Darwin", "Linux"):
        launcher = ins.write_launcher(tmp_path, tmp_path / "py", system)
        assert launcher.stat().st_mode & 0o111  # has an execute bit


def test_no_install_needs_an_existing_venv(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    # With --no-install and a missing venv it fails loudly instead of guessing.
    code = ins.main(["--no-install", "--venv", str(tmp_path / "absent")])
    assert code == 1
    assert "entorno" in capsys.readouterr().out.lower()
