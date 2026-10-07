# Historial de cambios

## Base inicial de PiNexo

El repositorio parte del panel funcional v5, desarrollado antes de organizar
este proyecto como repositorio independiente. Esta lista resume esa evolución;
no representa etiquetas o releases publicados en GitHub.

- Menú Inicio con iconos grandes para Clima y Notificaciones.
- Notificaciones reservado como «Próximamente».
- Tema oscuro y tema claro, con preferencia persistente.
- Clima actual, vista Hoy, próximos días y aviso configurable de lluvia.
- Historial satelital NOAA, animación, pausa y movimiento del encuadre.
- Zoom hasta 10× y recorte regional de la misma captura al pausar.
- Límites de estados y nombres de ciudades según el zoom.
- Caché, descarga en segundo plano y servicio opcional de inicio automático.
- Documentación de instalación, arquitectura, hardware y siguientes pasos.
- Pruebas offline de datos, servicios simulados, navegación y satélite.

PiNexo identifica el proyecto. El hostname de la Raspberry y los nombres
internos `pi-clima.service` y `~/.cache/pi-clima` son independientes.
