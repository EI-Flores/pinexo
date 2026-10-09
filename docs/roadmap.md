# Potential improvements for PiNexo

This list outlines possible next steps. It does not set dates, guarantee integrations, or present pending features as available.

## Available baseline

The current version includes the `Inicio` (Home) screen with icons, a weather module, a satellite view with map overlays and zoom up to 10×, both themes, caching, and an optional service. `Notificaciones` (Notifications) displays a “Próximamente” (Coming soon) page. The touch controller still needs calibration.

## Next steps on the device

- **Touch:** check controller events, orientation, and calibration to navigate directly on the LCD.
- **Continuous use:** observe stability, responsiveness, memory use, and downloads on the Raspberry Pi 3 during extended sessions.
- **Readability:** adjust sizes and contrast based on testing on the physical device, retaining the dark and light themes.

## Dashboard development

- **Notifications:** choose an initial useful source before adding accounts, authentication, and real alerts. The current icon reserves the space and has no external connection.
- **Modules:** define a common interface for opening modules, returning to `Inicio` (Home), and reporting status, keeping data and views separate.
- **Settings:** make it easier to adjust the city, intervals, and preferences without editing code.
- **Additional information:** consider network data or other indicators if they are useful in everyday use and fit within the device's resources.

## Project presentation

- Document actual results and limitations after testing on the LCD.
- Add screenshots and a brief architecture explanation for the portfolio.
- Later, prepare a static project page on **GitHub Pages**, with a description, images, and a link to the repository. The Python application will continue to run on the Raspberry Pi; Pages would present the project.
- Keep provider attributions alongside the code's MIT license.

Prioritize usefulness on a Raspberry Pi 3 and a 480×320 screen, without turning every idea into an additional service to maintain.
