"""Instala quantos como app de escritorio — un ícono para abrir con doble clic.

Corre esto EN TU COMPUTADORA, una sola vez, desde la carpeta ``quant/``::

    python install_desktop.py

Qué hace (detecta tu sistema solo: Windows, macOS o Linux):
  1. crea un entorno aislado en ``.venv`` e instala quantos + el dashboard,
  2. deja un lanzador en tu Escritorio (``quantos.command`` / ``.bat`` /
     ``.desktop``) que abre la app en el navegador con doble clic.

No publica nada en internet: la app corre local en tu máquina. Con
``--no-install`` solo escribe el lanzador (si ya instalaste antes).
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent


def venv_python(venv: Path) -> Path:
    """Ruta al Python del entorno, según el sistema."""
    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def ensure_venv(venv: Path) -> Path:
    """Crea ``.venv`` e instala quantos[dashboard] si aún no existe."""
    python = venv_python(venv)
    if python.exists():
        print(f"Entorno ya existe: {venv}")
        return python
    print("Creando entorno e instalando (una sola vez, puede tardar un par de minutos)...")
    subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
    subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    subprocess.check_call([str(python), "-m", "pip", "install", "-e", f"{REPO}[dashboard]"])
    return python


def desktop_dir() -> Path:
    """El Escritorio del usuario (con respaldos razonables)."""
    for candidate in (Path.home() / "Desktop", Path.home() / "OneDrive" / "Desktop"):
        if candidate.is_dir():
            return candidate
    return Path.home()


def write_launcher(dest: Path, python: Path, system: str, repo: Path = REPO) -> Path:
    """Escribe el lanzador de doble clic apropiado para ``system`` en ``dest``."""
    if system == "Windows":
        # A .vbs launcher runs the app SILENTLY (no black console window) via
        # pythonw.exe — the "feels like a real app" trick. Run ..., 0, False =
        # hidden window, don't wait.
        pythonw = python.with_name("pythonw.exe")
        path = dest / "quantos.vbs"
        path.write_text(
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.CurrentDirectory = "{repo}"\r\n'
            f'sh.Run """{pythonw}"" -m quantos.dashboard.launch", 0, False\r\n',
            encoding="utf-8",
        )
    elif system == "Darwin":
        path = dest / "quantos.command"
        path.write_text(
            f'#!/bin/bash\ncd "{repo}"\nexec "{python}" -m quantos.dashboard.launch\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
    else:  # Linux y otros Unix
        path = dest / "quantos.desktop"
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=quantos\n"
            "Comment=AI Quant Research Platform (research only)\n"
            f'Exec="{python}" -m quantos.dashboard.launch\n'
            f"Path={repo}\n"
            "Terminal=true\n"
            "Categories=Office;Finance;\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
    return path


def write_stop_launcher(dest: Path, system: str) -> Path:
    """Escribe el lanzador de 'detener' (apaga la app corriendo) para ``system``."""
    if system == "Windows":
        # Termina solo los procesos de python cuya línea de comando menciona
        # nuestra app (nunca otros python). Silencioso, con un aviso al final.
        path = dest / "Detener quantos.vbs"
        path.write_text(
            'Set svc = GetObject("winmgmts:\\\\.\\root\\cimv2")\r\n'
            "Set procs = svc.ExecQuery("
            '"SELECT * FROM Win32_Process WHERE Name=\'python.exe\' OR Name=\'pythonw.exe\'")\r\n'
            "For Each p In procs\r\n"
            "  If Not IsNull(p.CommandLine) Then\r\n"
            '    If InStr(p.CommandLine, "quantos") > 0 And InStr(p.CommandLine, "dashboard") > 0 '
            "Then\r\n"
            "      p.Terminate()\r\n"
            "    End If\r\n"
            "  End If\r\n"
            "Next\r\n"
            'MsgBox "quantos se detuvo.", 64, "quantos"\r\n',
            encoding="utf-8",
        )
    elif system == "Darwin":
        path = dest / "Detener quantos.command"
        path.write_text(
            "#!/bin/bash\npkill -f 'quantos.*dashboard'\n"
            'echo "quantos se detuvo."; sleep 1\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
    else:  # Linux
        path = dest / "Detener quantos.desktop"
        path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Detener quantos\n"
            "Comment=Stop the running quantos app\n"
            "Exec=pkill -f 'quantos.*dashboard'\n"
            "Terminal=false\n"
            "Categories=Office;Finance;\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instala quantos como app de escritorio.")
    parser.add_argument(
        "--no-install", action="store_true", help="solo escribir el lanzador (no crear el entorno)"
    )
    parser.add_argument("--venv", default=str(REPO / ".venv"), help="ruta del entorno virtual")
    args = parser.parse_args(argv)

    venv = Path(args.venv)
    python = venv_python(venv) if args.no_install else ensure_venv(venv)
    if not python.exists():
        print(f"No encuentro el Python del entorno en {python}. Corre sin --no-install primero.")
        return 1

    desktop = desktop_dir()
    launcher = write_launcher(desktop, python, platform.system())
    stopper = write_stop_launcher(desktop, platform.system())
    print("\n¡Listo! Se crearon 2 íconos en tu Escritorio:")
    print(f"   ▶  {launcher.name}   (abrir la app)")
    print(f"   ■  {stopper.name}   (detenerla)")
    print(f"\nEscritorio: {desktop}")
    print("Haz doble clic en el primero para abrir la app en tu navegador.")
    if platform.system() == "Darwin":
        print("(La primera vez, si macOS pregunta, permite abrirlo: clic derecho → Abrir.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
