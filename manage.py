#!/usr/bin/env python3
"""Activa, detiene o consulta Pi Clima como servicio del usuario actual."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePath

# La vista previa tampoco debe crear cachés de bytecode al importar módulos.
sys.dont_write_bytecode = True
from data import atomic_write


BASE = Path(__file__).resolve().parent
SERVICE = "pi-clima.service"
MARKER = "# Managed by Pi Clima"


def _quote_argument(value: str) -> str:
    """Escapa un argumento de ExecStart, sin pasar por un intérprete de órdenes."""
    escapes = {
        "\\": "\\\\", '"': '\\"', "%": "%%", "$": "$$",
        "\n": "\\n", "\r": "\\r", "\t": "\\t",
    }
    if "\0" in value:
        raise ValueError("La ruta contiene un carácter nulo")
    return '"' + "".join(escapes.get(char, char) for char in value) + '"'


def render_unit(base: PurePath | str = BASE) -> str:
    """Genera la unidad sin consultar el sistema ni escribir archivos."""
    directory = base if isinstance(base, PurePath) else Path(base)
    script = _quote_argument(str(directory / "app.py"))
    return (
        f"{MARKER}\n"
        "[Unit]\n"
        "Description=Pi Clima: panel meteorológico\n"
        "StartLimitIntervalSec=0\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart=/usr/bin/python3 {script} --service\n"
        "Restart=on-failure\n"
        "RestartSec=15\n"
        "\n"
        "[Install]\n"
        "WantedBy=default.target\n"
    )


def unit_path() -> Path:
    """Ubicación de la unidad privada del usuario."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "systemd" / "user" / SERVICE


def _run(arguments: list[str], capture: bool = False):
    return subprocess.run(
        arguments,
        text=True,
        capture_output=capture,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )


def _owned_contents(path: Path, required: bool = False) -> bytes | None:
    if path.is_symlink():
        raise RuntimeError(f"La unidad es un enlace simbólico; se conserva sin cambios: {path}")
    if not path.exists():
        if required:
            raise RuntimeError("No hay una unidad de Pi Clima instalada por este usuario")
        return None
    if not path.is_file():
        raise RuntimeError(f"La ruta de la unidad no es un archivo: {path}")
    payload = path.read_bytes()
    if MARKER not in payload.decode("utf-8", "replace").splitlines():
        raise RuntimeError(f"Existe una unidad ajena con ese nombre; se conserva sin cambios: {path}")
    return payload


def _guard_loaded_unit(destination: Path) -> None:
    """Comprueba que no se vaya a ocultar ni controlar una unidad ajena."""
    result = _run(
        ["systemctl", "--user", "show", SERVICE, "--property=FragmentPath", "--value"],
        capture=True,
    )
    fragment = (result.stdout or "").strip()
    if result.returncode:
        detail = (result.stderr or "").strip()
        if not fragment and ("could not be found" in detail or "not found" in detail):
            return
        raise RuntimeError(detail or "No se pudo consultar el gestor de servicios del usuario")
    if not fragment:
        return
    loaded = Path(fragment)
    if loaded.resolve() == destination.resolve():
        _owned_contents(destination, required=True)
        return
    payload = loaded.read_bytes()
    if MARKER not in payload.decode("utf-8", "replace").splitlines():
        raise RuntimeError(f"Ya existe una unidad ajena cargada; se conserva sin cambios: {loaded}")


def enable_service(base: PurePath | str = BASE) -> int:
    """Instala únicamente la unidad propia y aplica su configuración."""
    destination = unit_path()
    previous = _owned_contents(destination)
    _guard_loaded_unit(destination)
    if previous is not None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        backup = destination.with_name(destination.name + ".backup-" + stamp)
        suffix = 1
        while backup.exists() or backup.is_symlink():
            backup = destination.with_name(destination.name + ".backup-" + stamp + f"-{suffix}")
            suffix += 1
        atomic_write(backup, previous)
        print(f"Copia de la unidad anterior: {backup}")
    atomic_write(destination, render_unit(base).encode("utf-8"))
    for arguments in (
        ["systemctl", "--user", "daemon-reload"],
        ["systemctl", "--user", "enable", "--now", SERVICE],
        ["systemctl", "--user", "restart", SERVICE],
    ):
        result = _run(arguments)
        if result.returncode:
            print("La unidad está guardada, pero no se pudo completar: " + " ".join(arguments), file=sys.stderr)
            return result.returncode
    result = _run(["systemctl", "--user", "is-active", SERVICE], capture=True)
    state = (result.stdout or "").strip() or "desconocido"
    print(f"Servicio habilitado. Estado actual: {state}.")
    if state == "active" and result.returncode == 0:
        print("Comprueba la imagen en el LCD; el estado del servicio no confirma la salida de la pantalla.")
        return 0
    if state in ("activating", "reloading"):
        print("Está iniciando o reintentando. Si el escritorio aún no está disponible, volverá a intentarlo cada 15 segundos.")
        print("Consulta el resultado con: python3 manage.py status")
        return 0
    if result.stderr:
        print(result.stderr.strip(), file=sys.stderr)
    print("Consulta el diagnóstico con: python3 manage.py logs", file=sys.stderr)
    return result.returncode or 1


def disable_service() -> int:
    """Detiene y deshabilita el servicio; conserva la unidad y sus copias."""
    destination = unit_path()
    _owned_contents(destination, required=True)
    _guard_loaded_unit(destination)
    result = _run(["systemctl", "--user", "disable", "--now", SERVICE])
    if result.returncode == 0:
        print("Servicio detenido y deshabilitado. La unidad queda disponible para volver a activarla.")
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Administrar el inicio automático de Pi Clima")
    parser.add_argument("command", nargs="?", choices=("enable", "disable", "status", "logs"))
    parser.add_argument("--dry-run", action="store_true", help="Mostrar la unidad sin escribir archivos ni ejecutar órdenes")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(render_unit(), end="")
        return 0
    if args.command is None:
        parser.error("elige enable, disable, status o logs; también puedes usar --dry-run")
    if sys.platform != "linux":
        raise RuntimeError("Ejecuta esta orden en la Raspberry Pi; --dry-run también funciona en otros sistemas")
    if os.geteuid() == 0:
        raise RuntimeError("Ejecuta manage.py como tu usuario habitual, sin sudo")
    if args.command == "enable":
        return enable_service()
    if args.command == "disable":
        return disable_service()
    if args.command == "status":
        return _run(["systemctl", "--user", "status", "--no-pager", "--full", SERVICE]).returncode
    return _run(["journalctl", "--user", "--unit=" + SERVICE, "--lines=60", "--no-pager"]).returncode


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Pi Clima: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except KeyboardInterrupt:
        raise SystemExit(130)
