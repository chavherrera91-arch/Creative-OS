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
import os
import platform
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
ASSETS = REPO / "quantos" / "dashboard" / "assets"


def default_venv() -> Path:
    """Where to create the virtual environment.

    On Windows the environment goes in a SHORT, stable location
    (``%LOCALAPPDATA%\\quantos\\.venv``) instead of inside the (often deeply
    nested, long-named) download folder — otherwise Streamlit's deep files blow
    past the 260-character path limit (WinError 206). Elsewhere it lives beside
    the code.
    """
    if platform.system() == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        return base / "quantos" / ".venv"
    return REPO / ".venv"


def icon_path(system: str, assets: Path = ASSETS) -> Path:
    """The icon file for ``system`` — .ico on Windows, .png elsewhere."""
    return assets / ("quantos.ico" if system == "Windows" else "quantos.png")


def venv_python(venv: Path) -> Path:
    """Ruta al Python del entorno, según el sistema."""
    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def ensure_venv(venv: Path) -> Path:
    """Crea ``.venv`` (si falta) e instala/re-apunta quantos[dashboard] a ESTA carpeta.

    El ``pip install -e`` corre siempre — así, si vuelves a correr el instalador
    desde una descarga nueva, el entorno usa ese código (no el de una carpeta
    vieja). Es rápido cuando las dependencias ya están.
    """
    python = venv_python(venv)
    if not python.exists():
        print(f"Creando entorno en {venv} (una sola vez, puede tardar un par de minutos)...")
        venv.parent.mkdir(parents=True, exist_ok=True)
        subprocess.check_call([sys.executable, "-m", "venv", str(venv)])
        subprocess.check_call([str(python), "-m", "pip", "install", "--upgrade", "pip"])
    else:
        print(f"Entorno ya existe: {venv} (actualizando al código de esta carpeta)")
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
            f"Icon={icon_path('Linux')}\n"
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
            "\"SELECT * FROM Win32_Process WHERE Name='python.exe' OR Name='pythonw.exe'\")\r\n"
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
            "#!/bin/bash\npkill -f 'quantos.*dashboard'\necho \"quantos se detuvo.\"; sleep 1\n",
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
            f"Icon={icon_path('Linux')}\n"
            "Terminal=false\n"
            "Categories=Office;Finance;\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
    return path


def windows_shortcut_script(shortcuts: list[tuple[Path, Path, Path, Path]]) -> str:
    """VBScript that creates Windows .lnk shortcuts (target, icon, workdir).

    Each tuple is ``(lnk, target, icon, workdir)``. Double-clicking the .lnk
    runs the target .vbs but shows the custom icon — the professional look.
    """
    lines = ['Set sh = CreateObject("WScript.Shell")']
    for i, (lnk, target, icon, workdir) in enumerate(shortcuts):
        lines += [
            f'Set s{i} = sh.CreateShortcut("{lnk}")',
            f's{i}.TargetPath = "{target}"',
            f's{i}.IconLocation = "{icon}"',
            f's{i}.WorkingDirectory = "{workdir}"',
            f"s{i}.Save",
        ]
    return "\r\n".join(lines) + "\r\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Instala quantos como app de escritorio.")
    parser.add_argument(
        "--no-install", action="store_true", help="solo escribir el lanzador (no crear el entorno)"
    )
    parser.add_argument("--venv", default=str(default_venv()), help="ruta del entorno virtual")
    args = parser.parse_args(argv)

    venv = Path(args.venv)
    python = venv_python(venv) if args.no_install else ensure_venv(venv)
    if not python.exists():
        print(f"No encuentro el Python del entorno en {python}. Corre sin --no-install primero.")
        return 1

    desktop = desktop_dir()
    system = platform.system()

    if system == "Windows":
        names = _install_windows(desktop, python)
    else:
        launcher = write_launcher(desktop, python, system)
        stopper = write_stop_launcher(desktop, system)
        names = (launcher.name, stopper.name)

    print("\n¡Listo! Se crearon 2 íconos en tu Escritorio:")
    print(f"   ▶  {names[0]}   (abrir la app)")
    print(f"   ■  {names[1]}   (detenerla)")
    print(f"\nEscritorio: {desktop}")
    print("Haz doble clic en el primero para abrir la app en tu navegador.")
    if system == "Darwin":
        print("(La primera vez, si macOS pregunta, permite abrirlo: clic derecho → Abrir.)")
        print("(Para el ícono con logo: clic en el archivo → Obtener información → arrastra")
        print(f" {icon_path('Darwin')} sobre el ícono chico arriba a la izquierda.)")
    return 0


def _install_windows(desktop: Path, python: Path) -> tuple[str, str]:
    """Windows: .vbs launchers in the repo + desktop .lnk shortcuts with the logo.

    Falls back to plain .vbs files on the desktop if shortcut creation fails,
    so the app is always reachable even without the custom icon.
    """
    launchers = REPO / ".launchers"
    launchers.mkdir(exist_ok=True)
    start = write_launcher(launchers, python, "Windows")
    stop = write_stop_launcher(launchers, "Windows")
    icon = icon_path("Windows")
    lnks = (desktop / "quantos.lnk", desktop / "Detener quantos.lnk")
    script = windows_shortcut_script([(lnks[0], start, icon, REPO), (lnks[1], stop, icon, REPO)])
    try:  # pragma: no cover - real Windows shortcut path
        import subprocess
        import tempfile

        helper = Path(tempfile.gettempdir()) / "_quantos_mkshortcut.vbs"
        helper.write_text(script, encoding="utf-8")
        subprocess.check_call(["cscript", "//nologo", str(helper)])
        helper.unlink(missing_ok=True)
        return (lnks[0].name, lnks[1].name)
    except Exception:  # noqa: BLE001 - fall back to plain launchers on the desktop
        s1 = write_launcher(desktop, python, "Windows")
        s2 = write_stop_launcher(desktop, "Windows")
        return (s1.name, s2.name)


if __name__ == "__main__":
    raise SystemExit(main())
