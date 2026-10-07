![PiNexo](assets/pinexo.svg)

# PiNexo

A personal dashboard for a Raspberry Pi 3 and a **480×320 GPIO display**. A menu with large icons opens the weather module: forecasts, rain probability notices, and satellite images of Mexico with city labels and state boundaries. The dark theme uses blue backgrounds, cyan lines, and amber accents; a light theme is also available.

The goal is to put available hardware to everyday use through a simple interface that can accommodate more modules. The **Notifications** tile is marked as coming soon; account connections and message delivery are still planned. The application interface currently uses Spanish.

![Home screen in dark mode](assets/screenshots/home-dark.png)

## Current features

- Home screen with Weather and Notifications icons.
- Current conditions, hourly temperatures, a Today view, and the next three days.
- Configurable rain probability notice; this is not an official weather alert.
- NOAA GeoColor history with playback, pause, dragging, and **1× to 10×** zoom.
- State boundaries and city labels that depend on zoom, with Xalapa highlighted.
- A regional crop of the same observation when zooming beyond 4× with playback paused.
- Persistent dark/light theme, local cache, and background downloads.
- Optional automatic startup through a user service.

![Weather in dark mode](assets/screenshots/weather-dark.png)
![Satellite view at 10×](assets/screenshots/satellite-10x.png)

## Requirements

The reference setup is a **Raspberry Pi 3** running 64-bit Debian 13 and the **labwc** desktop, with a 3.5-inch GPIO LCD. The application requires **Python 3.10 or later**, **Pygame**, a graphical session, and an Internet connection to refresh data. A windowed preview is also available.

The display must already show the desktop before installing the dashboard. The [hardware guide](docs/hardware.md) describes the reference hardware and configuration. The touchscreen controller **still needs calibration**; mouse and keyboard input are available.

## Installation

On the Raspberry Pi, install Git and the graphics dependency provided by Debian:

```bash
sudo apt update
sudo apt install git python3-pygame
```

Clone the repository and open its directory:

```bash
git clone https://github.com/EI-Flores/pinexo.git
cd pinexo
```

Create the configuration from the example, preserving any existing file:

```bash
test -f config.json || cp config.json.example config.json
```

Follow [Choose or change a city](#choose-or-change-a-city) before requesting a forecast. The template contains the placeholder label `Configura tu ciudad`, coordinates **0, 0**, and the **UTC** time zone. Replace these values with your chosen location. The example does not contain personal configuration, and `config.json` is excluded from Git.

Check the weather download and start the dashboard:

```bash
python3 app.py --check-weather
python3 app.py
```

Use `python3 app.py --windowed` if you do not have a 480×320 display or want a preview. The `--demo` option displays fictional weather data offline:

```bash
python3 app.py --windowed --demo
```

For automatic startup in your user session, first close any manually started instance and run:

```bash
python3 manage.py enable
```

The service needs the same user's desktop to be available. It does not start a graphical login session itself, and the dashboard does not need administrator privileges.

## Choose or change a city

The dashboard reads `config.json` in the project directory at startup. It does **not** search for a location by city name: the forecast request uses the coordinates and time zone. Update all four fields together when choosing another location:

| Field | Purpose and accepted value |
|---|---|
| `city` | Display label, such as `Berlin, Germany`. Changing this text alone does not change the forecast location. |
| `latitude` | Latitude in decimal degrees, as a JSON number between −90 and 90. South is negative. |
| `longitude` | Longitude in decimal degrees, as a JSON number between −180 and 180. West is negative. |
| `timezone` | IANA time zone identifier, such as `Europe/Berlin`. Use the location's time zone, not an abbreviation such as `CST` or a fixed UTC offset. |

To find these values, use the [Open-Meteo geocoding documentation and location search](https://open-meteo.com/en/docs/geocoding-api). Check the result's country and administrative area to distinguish places with the same name, then copy its `latitude`, `longitude`, and `timezone` fields.

For example, the following four fields select **Berlin, Germany**, using the public example in the geocoding documentation:

```json
{
  "city": "Berlin, Germany",
  "latitude": 52.52437,
  "longitude": 13.41053,
  "timezone": "Europe/Berlin"
}
```

This is a **partial example**. Replace the matching fields in your existing `config.json`; keep the refresh intervals, satellite URL, and other settings. Use a decimal point for coordinates, leave numbers unquoted, and keep valid JSON syntax with no comments or trailing commas.

From the project directory, edit the file:

```bash
nano config.json
```

Save it and check the configuration and forecast download without opening a graphical window:

```bash
python3 app.py --check-weather
```

The output should show the chosen city label, temperature, observation time, and configured time zone. If it reports an error, correct the configuration or connection before restarting the dashboard.

If automatic startup is enabled, apply the change with:

```bash
systemctl --user restart pi-clima.service
```

If you run the dashboard manually, close the existing window and start it again with `python3 app.py` (or `python3 app.py --windowed` for a preview). A Raspberry Pi reboot is not required. Forecast cache entries are matched by coordinates and time zone, so a previous location's forecast is not reused for a different location.

You can also use a separate configuration file for a manual run:

```bash
python3 app.py --config /absolute/path/to/config.json --windowed
```

That option applies only to that invocation; the automatically managed service continues to use the project's `config.json`.

**Current scope:** these settings change the forecast location and the displayed time zone. Satellite coverage and map overlays remain focused on Mexico. The Mexico/Veracruz presets, highlighted Xalapa marker, Home card caption, and demo city label are not yet configurable and require separate code or map changes.

## Usage and maintenance

The controls below refer to the current Spanish interface labels.

| Action | Control |
|---|---|
| Open weather from Home | `Clima` icon or 1 |
| Return to Home | `Inicio` button, H, or Escape |
| Switch theme | `Claro`/`Oscuro` on Home or D |
| Select a weather view | Bottom buttons or 1–5 |
| Play/pause satellite history | Playback button or Space/P |
| Zoom and pan | +/−, mouse wheel, and dragging; arrow keys to pan |
| Mexico / Veracruz preset | `México` / `Veracruz` buttons or M / V |
| Quit | Escape from Home |

Zooming beyond **4×** pauses animation. Once the view settles, the dashboard requests a regional crop; it keeps the available image if a request fails and avoids downloading a complete history for each zoom change. The displayed timestamp still belongs to that observation. **10× does not add street-level detail**: resolution depends on the sensor and product.

The cache and theme preference are stored in `~/.cache/pi-clima` or under `XDG_CACHE_HOME`. The internal service name remains `pi-clima.service` for compatibility. **PiNexo** is the project name; the Raspberry Pi's network hostname is configured separately.

Inspect the service with:

```bash
python3 manage.py status
python3 manage.py logs
```

To disable automatic startup, use `python3 manage.py disable`. Restart the service after changing `config.json`, as described above. Stop the service with `systemctl --user stop pi-clima.service` before starting a manual instance to avoid running two copies.

## Project status and documentation

The application includes local tests for data, caches, and controls, plus views rendered with a simulated display driver. Performance, resource use, and touch input need checking on each Raspberry Pi and display; compatibility with every GPIO LCD has not been verified.

All README files are in English. Supporting guides and the contribution guide are currently in Spanish:

- [Architecture and data flow](docs/architecture.md).
- [Reference hardware and display](docs/hardware.md).
- [Planned improvements](docs/roadmap.md).
- [Data sources and attribution](docs/data-sources.md).
- [Upgrade an existing installation](docs/upgrade.md).
- [Contributing](CONTRIBUTING.md) and [offline tests](tests/README.md).

To check the software in a development environment with Python 3.12:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t . -v
```

GitHub Actions runs these tests with a simulated display. It does not verify physical LCD wiring, drivers, or performance.

## Authorship and data sources

A project by [EI-Flores](https://github.com/EI-Flores). External data retains its own attribution and usage conditions:

- [Open-Meteo](https://open-meteo.com/en/docs): weather forecasts; [license and attribution](https://open-meteo.com/en/licence), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- [NOAA GeoColor](https://satellitemaps.nesdis.noaa.gov/arcgis/rest/services/ABIGC_Last_24hr/ImageServer): satellite imagery; credit CIRA/NOAA.
- [Natural Earth](https://www.naturalearthdata.com/): boundaries and cities, [public domain](https://www.naturalearthdata.com/about/terms-of-use/). Credits and original sources are recorded in `map_data.json`.
- [GeoNames: Xalapa](https://www.geonames.org/3526617/xalapa-de-enriquez.html): coordinates, [CC BY](https://www.geonames.org/export/#terms).

The code is distributed under the [MIT license](LICENSE), with authorship credited to **EI-Flores**. External data and imagery retain their own terms, described in [Data sources and attribution](docs/data-sources.md).

A project page on GitHub Pages is planned for later.
