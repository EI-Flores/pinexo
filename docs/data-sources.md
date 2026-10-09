# Data sources and attribution

PiNexo's code and third-party data are subject to separate terms.
Retain the credits when reusing captures, maps, or provider data.

| Source | Use | Terms and credit |
|---|---|---|
| [Open-Meteo](https://open-meteo.com/en/docs) | Weather conditions, hourly and daily forecasts | [CC BY 4.0 and attribution](https://open-meteo.com/en/licence). Values are rounded and samples are selected for the LCD. |
| [NOAA GeoColor](https://satellitemaps.nesdis.noaa.gov/arcgis/rest/services/ABIGC_Last_24hr/ImageServer) | Image history and regional geographic crops | GeoColor credit: CIRA/NOAA. PiNexo requests image extents and overlays boundaries and names. |
| [Natural Earth](https://www.naturalearthdata.com/) | Mexican states and cities | [Public domain](https://www.naturalearthdata.com/about/terms-of-use/). Natural Earth, Nathaniel Vaughn Kelso, Tom Patterson, and contributors. Features are selected and outlines are simplified. |
| [GeoNames: Xalapa de Enríquez](https://www.geonames.org/3526617/xalapa-de-enriquez.html) | Xalapa coordinates | [CC BY](https://www.geonames.org/export/#terms). Coordinates are unchanged; the name is shortened to Xalapa. |

`map_data.json` includes metadata, source links, and fingerprints of the
files used. Population figures are used to prioritize labels and are not
presented as a current census.

Satellite captures are past observations. Capture time and query time
are different; animating frames does not constitute a forecast.
The panel's rain alerts are calculated from the forecast and do not replace
official alerts.

Provider availability and access terms may change.
Consult their documentation before using the data beyond this personal panel.

Pygame and the dependencies are installed separately and retain their own licenses.
The repository does not include their binaries or redistribute the operating system.
