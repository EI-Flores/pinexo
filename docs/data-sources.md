# Fuentes de datos y atribuciones

El código de PiNexo y los datos de terceros tienen condiciones independientes.
Conserva los créditos al reutilizar capturas, cartografía o datos de proveedores.

| Fuente | Uso | Condiciones y crédito |
|---|---|---|
| [Open-Meteo](https://open-meteo.com/en/docs) | Condiciones, pronóstico horario y diario | [CC BY 4.0 y atribución](https://open-meteo.com/en/licence). Se redondean cifras y seleccionan muestras para el LCD. |
| [NOAA GeoColor](https://satellitemaps.nesdis.noaa.gov/arcgis/rest/services/ABIGC_Last_24hr/ImageServer) | Historial de imágenes y recortes regionales geográficos | Crédito GeoColor: CIRA/NOAA. PiNexo solicita encuadres y superpone límites y nombres. |
| [Natural Earth](https://www.naturalearthdata.com/) | Estados de México y ciudades | [Dominio público](https://www.naturalearthdata.com/about/terms-of-use/). Natural Earth, Nathaniel Vaughn Kelso, Tom Patterson y colaboradores. Se seleccionan entidades y simplifican contornos. |
| [GeoNames: Xalapa de Enríquez](https://www.geonames.org/3526617/xalapa-de-enriquez.html) | Coordenadas de Xalapa | [CC BY](https://www.geonames.org/export/#terms). Coordenadas sin cambios; nombre abreviado a Xalapa. |

`map_data.json` incorpora metadatos, enlaces de origen y huellas de los
archivos usados. Las poblaciones se utilizan para priorizar etiquetas y no se
presentan como un censo actual.

Las capturas del satélite son observaciones pasadas. La hora de captura y la
hora de consulta son distintas; animar cuadros no constituye un pronóstico.
Los avisos de lluvia del panel se calculan con el pronóstico y no sustituyen
avisos oficiales.

La disponibilidad y condiciones de acceso de los proveedores pueden cambiar.
Consulta sus documentos antes de un uso que exceda este panel personal.

Pygame y las dependencias se instalan aparte y conservan sus propias licencias.
El repositorio no incorpora sus binarios ni redistribuye el sistema operativo.
