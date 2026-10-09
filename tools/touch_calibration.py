#!/usr/bin/env python3
"""Standalone LCD touch diagnostic; never edits or reloads labwc configuration.

pygame is imported only by the graphical collector. The fitting and report
functions use the standard library and can be tested without a graphical session.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

WIDTH, HEIGHT = 480, 320
DEVICE = "ADS7846 Touchscreen"
TARGETS = ((240, 160), (40, 40), (439, 40), (439, 279), (40, 279))
TARGET_NAMES = ("Centro", "Arriba izquierda", "Arriba derecha", "Abajo derecha", "Abajo izquierda")


class CalibrationError(ValueError):
    """Measurements or configuration do not support a reliable affine proposal."""


def transform(matrix, point):
    a, b, c, d, e, f = matrix
    x, y = point
    return a * x + b * y + c, d * x + e * y + f


def compose(after, before):
    """Compose two libinput 2x3 affine matrices: after(before(point))."""
    a, b, c, d, e, f = after
    g, h, i, j, k, l = before
    return (a * g + b * j, a * h + b * k, a * i + b * l + c,
            d * g + e * j, d * h + e * k, d * i + e * l + f)


def inverse3(matrix):
    """Invert a small matrix with partial pivoting, rejecting rank deficiency."""
    rows = [list(row) + [float(i == j) for j in range(3)] for i, row in enumerate(matrix)]
    scale = max(abs(value) for row in matrix for value in row)
    if not scale or not math.isfinite(scale):
        raise CalibrationError("Los puntos no permiten calcular una matriz estable.")
    for column in range(3):
        pivot = max(range(column, 3), key=lambda i: abs(rows[i][column]))
        if abs(rows[pivot][column]) < scale * 1e-10:
            raise CalibrationError("Los puntos están alineados o demasiado próximos.")
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value / divisor for value in rows[column]]
        for index in range(3):
            if index != column:
                factor = rows[index][column]
                rows[index] = [left - factor * right for left, right in zip(rows[index], rows[column])]
    return [row[3:] for row in rows]


def fit_affine(observed, targets):
    """Fit normalized observed->target coordinates; return matrix and condition."""
    if len(observed) != len(targets) or len(observed) < 5:
        raise CalibrationError("Se necesitan los cinco puntos, en el orden indicado.")
    if any(len(point) != 2 or not all(math.isfinite(float(v)) for v in point)
           for point in (*observed, *targets)):
        raise CalibrationError("Las coordenadas deben ser pares de números finitos.")
    design = [[float(x), float(y), 1.0] for x, y in observed]
    normal = [[sum(row[i] * row[j] for row in design) for j in range(3)] for i in range(3)]
    inverse = inverse3(normal)
    norm = lambda values: max(sum(abs(v) for v in row) for row in values)
    condition = norm(normal) * norm(inverse)
    if condition > 1000:
        raise CalibrationError("Los puntos están demasiado próximos para un ajuste fiable.")
    coefficients = []
    for axis in range(2):
        rhs = [sum(row[i] * point[axis] for row, point in zip(design, targets)) for i in range(3)]
        coefficients.extend(sum(value * other for value, other in zip(row, rhs)) for row in inverse)
    return tuple(coefficients), condition


def summarize_contact(samples, duration):
    """Use only in-contact events, removing settling/release tails and outliers."""
    if not math.isfinite(duration) or duration < 0.35 or duration > 2.5:
        raise CalibrationError("Mantén el lápiz entre 0.5 y 1 segundo y luego levántalo.")
    if len(samples) < 3:
        raise CalibrationError("Llegaron pocas muestras. Mantén el lápiz con presión suave.")
    if any(len(sample) != 3 or not all(math.isfinite(float(v)) for v in sample) for sample in samples):
        raise CalibrationError("Se recibieron muestras inválidas.")
    settled = [sample for sample in samples if 0.08 <= sample[0] <= duration - 0.06]
    usable = settled if len(settled) >= 3 else samples
    middle = (statistics.median(sample[1] for sample in usable),
              statistics.median(sample[2] for sample in usable))
    distances = [math.dist(sample[1:], middle) for sample in usable]
    mad = statistics.median(distances)
    cutoff = max(4.0, 3 * mad)
    kept = [sample for sample, distance in zip(usable, distances) if distance <= cutoff]
    if len(kept) < 3:
        raise CalibrationError("Las muestras no son estables. Repite sin arrastrar el lápiz.")
    position = (statistics.median(sample[1] for sample in kept),
                statistics.median(sample[2] for sample in kept))
    radii = sorted(math.dist(sample[1:], position) for sample in usable)
    p90 = radii[min(len(radii) - 1, math.ceil(0.9 * len(radii)) - 1)]
    if p90 > 8:
        raise CalibrationError("El contacto se movió demasiado. Repite apoyando el lápiz en la cruz.")
    return {"observed_pixels": list(position), "duration_seconds": duration,
            "event_samples": len(samples), "settled_samples": len(usable),
            "retained_samples": len(kept), "p90_radius_pixels": p90}


def read_configuration(path):
    """Read an explicit device profile, independent of the XML namespace."""
    raw = path.read_bytes()
    root = ET.fromstring(raw)
    name = lambda element: element.tag.rsplit("}", 1)[-1]
    profiles = [device for section in root if name(section) == "libinput"
                for device in section if name(device) == "device" and device.get("category") == DEVICE]
    if len(profiles) != 1:
        raise CalibrationError("El archivo debe contener un único perfil libinput para ADS7846 Touchscreen.")
    entries = [entry for entry in profiles[0] if name(entry) == "calibrationMatrix"]
    if len(entries) != 1:
        raise CalibrationError("El perfil ADS7846 debe contener una única calibrationMatrix.")
    try:
        matrix = tuple(float(value) for value in (entries[0].text or "").split())
    except ValueError as exc:
        raise CalibrationError("La calibrationMatrix guardada no es válida.") from exc
    if len(matrix) != 6 or not all(math.isfinite(value) for value in matrix):
        raise CalibrationError("La calibrationMatrix necesita seis números finitos.")
    if abs(matrix[0] * matrix[4] - matrix[1] * matrix[3]) < 1e-8:
        raise CalibrationError("La calibrationMatrix guardada es singular.")
    touches = [entry for entry in root if name(entry) == "touch" and entry.get("deviceName") == DEVICE]
    if len(touches) != 1 or not touches[0].get("mapToOutput"):
        raise CalibrationError("Falta una asignación única del ADS7846 a la salida LCD.")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
            "matrix": list(matrix), "map_to_output": touches[0].get("mapToOutput"),
            "mouse_emulation": touches[0].get("mouseEmulation")}


def build_report(contacts, configuration, input_source, windowed=False):
    """Return measurements and a conditional proposal; never an applied setting."""
    report = {"tool": "PiNexo touch diagnostic", "version": 1,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "status": "invalid", "active_matrix_verified": False,
              "applied": False, "configuration": configuration,
              "screen_pixels": [WIDTH, HEIGHT], "coordinate_divisors": [WIDTH, HEIGHT],
              "windowed": windowed, "input_source": input_source, "points": [],
              "sampling": {"method": "median of in-contact input events; settled interval and radial outlier filter",
                           "minimum_contact_seconds": 0.35, "minimum_event_samples": 3,
                           "maximum_p90_radius_pixels": 8},
              "assumptions": ["The saved matrix was already reloaded by the running labwc session.",
                              "The physical LCD output has normal transform and scale 1.",
                              "All five contacts came from the physical ADS7846, with no remote mouse input.",
                              "The fullscreen SDL window was presented on the mapped 480x320 LCD.",
                              "No other labwc profile or udev matrix overrides the saved device profile."],
              "note": "This is a proposal for review and a later physical test; no configuration was changed."}
    for index, contact in enumerate(contacts):
        target = TARGETS[index] if index < len(TARGETS) else None
        report["points"].append(dict(contact, target_pixels=list(target) if target else None,
                                     target_name=TARGET_NAMES[index] if index < 5 else "Extra"))
    reasons = []
    try:
        if len(contacts) != 5:
            raise CalibrationError("Se necesitan exactamente cinco contactos válidos.")
        observed_pixels = [contact["observed_pixels"] for contact in contacts]
        if any(not (0 <= x < WIDTH and 0 <= y < HEIGHT) for x, y in observed_pixels):
            raise CalibrationError("Algún punto quedó fuera del área visible del LCD.")
        observed = [(x / WIDTH, y / HEIGHT) for x, y in observed_pixels]
        targets = [(x / WIDTH, y / HEIGHT) for x, y in TARGETS]
        correction, condition = fit_affine(observed, targets)
        errors = []
        before_errors = []
        for point, raw, target in zip(report["points"], observed, TARGETS):
            fitted = transform(correction, raw)
            fitted_pixels = [fitted[0] * WIDTH, fitted[1] * HEIGHT]
            error = math.dist(fitted_pixels, target)
            before = math.dist(point["observed_pixels"], target)
            point.update(predicted_pixels=fitted_pixels, residual_pixels=error, original_error_pixels=before)
            errors.append(error)
            before_errors.append(before)
        rms = lambda values: math.sqrt(sum(value * value for value in values) / len(values))
        report.update(fit_condition=condition, original_rms_error_pixels=rms(before_errors),
                      fitted_rms_error_pixels=rms(errors), maximum_residual_pixels=max(errors))
        if max(errors) > 10 or rms(errors) > 10:
            reasons.append("El ajuste deja más de 10 píxeles de error; repite los puntos.")
        determinant = correction[0] * correction[4] - correction[1] * correction[3]
        gains = (math.hypot(correction[0], correction[1]), math.hypot(correction[3], correction[4]))
        if not 0.25 <= abs(determinant) <= 4 or any(not 0.5 <= gain <= 2.5 for gain in gains):
            reasons.append("El ajuste exige una escala fuera del intervalo estable previsto.")
        if any(contact.get("event_samples", 0) < 3 or contact.get("p90_radius_pixels", math.inf) > 8
               or not 0.35 <= contact.get("duration_seconds", 0) <= 2.5 for contact in contacts):
            reasons.append("Hay contactos con pocas muestras, duración inválida o movimiento excesivo.")
        if windowed:
            reasons.append("La ventana de prueba no permite proponer una matriz para el LCD completo.")
        if not reasons:
            proposed = compose(correction, configuration["matrix"])
            if not all(math.isfinite(value) and abs(value) <= 4 for value in proposed):
                reasons.append("La matriz compuesta contiene valores fuera del intervalo estable previsto.")
            else:
                report.update(status="proposed", correction_matrix=list(correction),
                              proposed_matrix=list(proposed),
                              proposed_labwc_value=" ".join(f"{value:.8f}" for value in proposed))
    except (CalibrationError, KeyError, TypeError, ValueError) as exc:
        reasons.append(str(exc))
    report["reasons"] = reasons
    return report


def graphical_environment():
    """Reuse a unique same-user labwc socket without guessing a display name."""
    if os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"):
        return
    if not Path("/proc").is_dir() or not hasattr(os, "getuid"):
        return
    candidates = []
    for process in Path("/proc").iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid != os.getuid() or (process / "comm").read_text().strip() != "labwc":
                continue
            environment = dict(part.split("=", 1) for part in (process / "environ").read_bytes()
                               .decode("utf-8", "replace").split("\0") if "=" in part)
            runtime = environment.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
            socket = environment.get("WAYLAND_DISPLAY")
            if not socket:
                sockets = [path.name for path in Path(runtime).glob("wayland-*") if path.is_socket()]
                if len(sockets) == 1:
                    socket = sockets[0]
            if socket and (Path(socket) if socket.startswith("/") else Path(runtime) / socket).is_socket():
                environment.update(WAYLAND_DISPLAY=socket, XDG_RUNTIME_DIR=runtime)
                candidates.append(environment)
        except (OSError, ValueError):
            continue
    if len(candidates) != 1:
        raise CalibrationError("No hay una sesión labwc única. Ejecuta la prueba desde una terminal del escritorio LCD.")
    for key in ("WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DISPLAY", "XDG_SESSION_TYPE"):
        if candidates[0].get(key):
            os.environ[key] = candidates[0][key]


def collect_contacts(windowed=False):
    """Show five targets and collect one event stream, excluding hover positions."""
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    # A forwarded SSH display may point at another computer. Use the Pi session.
    if not windowed:
        for key in ("WAYLAND_DISPLAY", "DISPLAY", "SDL_VIDEODRIVER"):
            os.environ.pop(key, None)
    if os.environ.get("SDL_VIDEODRIVER") != "dummy":
        graphical_environment()
        if os.environ.get("WAYLAND_DISPLAY"):
            os.environ.setdefault("SDL_VIDEODRIVER", "wayland")
    try:
        import pygame
    except ImportError as exc:
        raise CalibrationError("Falta pygame. Instala python3-pygame en la Raspberry Pi.") from exc
    contacts = []
    source = None
    active = None
    latest = None
    message = "Apoya 0.5–1 s en cada cruz; luego levanta."
    try:
        pygame.display.init()
        pygame.font.init()
        desktops = pygame.display.get_desktop_sizes()
        suitable = [i for i, size in enumerate(desktops) if tuple(size) == (WIDTH, HEIGHT)]
        if not windowed and len(suitable) != 1:
            raise CalibrationError(f"No se encontró un LCD único de 480×320: {desktops}")
        index = suitable[0] if not windowed else 0
        screen = pygame.display.set_mode((WIDTH, HEIGHT), 0 if windowed else pygame.FULLSCREEN, display=index)
        if screen.get_size() != (WIDTH, HEIGHT):
            raise CalibrationError(f"La sesión cambió el tamaño de la prueba: {screen.get_size()}")
        pygame.display.set_caption("PiNexo · Diagnóstico táctil")
        pygame.mouse.set_visible(True)
        font = pygame.font.Font(None, 22)
        small = pygame.font.Font(None, 19)
        clock = pygame.time.Clock()
        dirty, last_draw = True, 0.0
        while len(contacts) < 5:
            for event in pygame.event.get():
                now = time.monotonic()
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    raise CalibrationError("Prueba cancelada; no se cambió la configuración.")
                if event.type == pygame.WINDOWEXPOSED:
                    dirty = True
                mouse = event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION)
                finger = event.type in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION)
                if not mouse and not finger:
                    continue
                kind = "mouse" if mouse else "finger"
                # SDL may generate a second mouse stream from native touch.
                if mouse and getattr(event, "touch", False):
                    continue
                down = (mouse and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1) or event.type == pygame.FINGERDOWN
                up = (mouse and event.type == pygame.MOUSEBUTTONUP and event.button == 1) or event.type == pygame.FINGERUP
                if source is None and down:
                    source = kind
                if source != kind:
                    continue
                position = event.pos if mouse else (event.x * WIDTH, event.y * HEIGHT)
                dirty = dirty or position != latest or down or up
                latest = position
                identity = "mouse" if mouse else event.finger_id
                if down and active is None:
                    active = {"identity": identity, "started": now, "samples": [(0.0, *position)]}
                    message = "Mantén el lápiz quieto y luego levántalo."
                elif active is not None and active["identity"] == identity:
                    duration = now - active["started"]
                    if up:
                        try:
                            contacts.append(summarize_contact(active["samples"], duration))
                            message = "Contacto registrado. Toca la siguiente cruz."
                        except CalibrationError as exc:
                            message = str(exc)
                        active = None
                    elif event.type in (pygame.MOUSEMOTION, pygame.FINGERMOTION):
                        active["samples"].append((duration, *position))
            if len(contacts) == 5:
                break
            # Poll input quickly; leave a stationary SPI display alone and cap
            # marker refreshes so drawing does not monopolize its small bus.
            clock.tick(60)
            if not dirty or time.monotonic() - last_draw < 0.05:
                continue
            screen.fill((5, 12, 18))
            target = TARGETS[len(contacts)]
            pygame.draw.line(screen, (55, 228, 235), (target[0] - 13, target[1]), (target[0] + 13, target[1]), 2)
            pygame.draw.line(screen, (55, 228, 235), (target[0], target[1] - 13), (target[0], target[1] + 13), 2)
            pygame.draw.circle(screen, (55, 228, 235), target, 17, 1)
            if latest:
                pygame.draw.circle(screen, (255, 167, 53), (round(latest[0]), round(latest[1])), 5, 2)
            title = font.render(f"{len(contacts) + 1}/5 · {TARGET_NAMES[len(contacts)]}", True, (220, 240, 245))
            screen.blit(title, title.get_rect(center=(240, 84)))
            coords = "Sin contacto" if latest is None else f"Recibido: x={latest[0]:.1f}, y={latest[1]:.1f}"
            text = small.render(coords, True, (255, 181, 75))
            screen.blit(text, text.get_rect(center=(240, 108)))
            # Messages are intentionally short enough for the physical 480px LCD.
            words, lines, line = message.split(), [], ""
            for word in words:
                candidate = f"{line} {word}".strip()
                if small.size(candidate)[0] > 440:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
            for index, line in enumerate(lines):
                label = small.render(line, True, (220, 240, 245))
                screen.blit(label, label.get_rect(center=(240, 211 + 21 * index)))
            footer = small.render("Solo lápiz físico · Esc: salir · Sin cambios", True, (135, 158, 170))
            screen.blit(footer, footer.get_rect(center=(240, 308)))
            pygame.display.flip()
            dirty, last_draw = False, time.monotonic()
    except pygame.error as exc:
        raise CalibrationError(f"No se pudo abrir la prueba en la sesión gráfica: {exc}") from exc
    finally:
        pygame.quit()
    return contacts, source


def main():
    parser = argparse.ArgumentParser(description="Medir el táctil LCD de PiNexo sin modificar su configuración.")
    parser.add_argument("--config", type=Path, default=Path.home() / ".config/labwc/rc.xml",
                        help="Archivo labwc que contiene la matriz ADS7846 ya recargada")
    parser.add_argument("--output", type=Path, help="Guardar el informe JSON en esta ruta; si se omite, usar stdout")
    parser.add_argument("--windowed", action="store_true", help="Vista previa para probar la herramienta; no propone calibración")
    args = parser.parse_args()
    try:
        configuration = read_configuration(args.config)
        print("Prueba local: toca las cinco cruces con el lápiz físico. No uses el ratón remoto.", file=sys.stderr)
        contacts, source = collect_contacts(args.windowed)
        if hashlib.sha256(args.config.read_bytes()).hexdigest() != configuration["sha256"]:
            raise CalibrationError("La configuración cambió durante la prueba. Repite con una configuración estable.")
        report = build_report(contacts, configuration, source, args.windowed)
        output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(output, encoding="utf-8")
            print(f"Informe guardado: {args.output}", file=sys.stderr)
        else:
            sys.stdout.write(output)
        print("La propuesta requiere revisión y prueba física; no se aplicó ningún cambio.", file=sys.stderr)
        return 0 if report["status"] == "proposed" or args.windowed else 2
    except (CalibrationError, OSError, ET.ParseError) as exc:
        print(f"No se completó la prueba: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Prueba cancelada; no se cambió la configuración.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
