# Changelog

## Unreleased

- Translate the project's Markdown documentation into English.
- Add contribution guidelines for separate commits by topic.

## Initial PiNexo baseline

The repository starts from the functional v5 dashboard, developed before
this project was organized as a separate repository. This list summarizes that
development; it does not represent tags or releases published on GitHub.

- `Inicio` (Home) menu with large icons for `Clima` (Weather) and `Notificaciones` (Notifications).
- `Notificaciones` (Notifications) reserved as “Próximamente” (Coming soon).
- Dark and light themes, with a persistent preference.
- Current weather, the `Hoy` (Today) view, upcoming days, and a configurable rain alert.
- NOAA satellite history, animation, pause, and panning.
- Zoom up to 10× and regional cropping of the same image when paused.
- State boundaries and city names based on the zoom level.
- Caching, background downloads, and an optional service for automatic startup.
- Documentation for installation, architecture, hardware, and next steps.
- Offline tests for data, mocked services, navigation, and the satellite view.

PiNexo identifies the project. The Raspberry Pi's hostname and the internal
names `pi-clima.service` and `~/.cache/pi-clima` are independent.
