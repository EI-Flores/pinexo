# Mejoras consideradas para PiNexo

Esta lista expresa posibles siguientes pasos. No establece fechas, garantiza integraciones ni presenta las funciones pendientes como disponibles.

## Base disponible

La versión actual incluye Inicio con iconos, módulo del clima, satélite con cartografía y zoom hasta 10×, ambos temas, caché y servicio opcional. Notificaciones muestra una página «Próximamente». El controlador táctil sigue pendiente de calibración.

## Próximo trabajo en el dispositivo

- **Touch:** comprobar eventos del controlador, orientación y calibración para navegar directamente en el LCD.
- **Uso continuo:** observar estabilidad, fluidez, memoria y descargas en la Raspberry Pi 3 durante sesiones prolongadas.
- **Legibilidad:** ajustar tamaños y contrastes a partir de la prueba física, conservando los temas oscuro y claro.

## Evolución del panel

- **Notificaciones:** elegir una primera fuente útil antes de añadir cuentas, autenticación y avisos reales. El icono actual reserva el espacio, sin conexión externa.
- **Módulos:** definir una interfaz común de apertura, regreso a Inicio y estado, manteniendo separados los datos y las vistas.
- **Configuración:** facilitar ajustes de ciudad, intervalos y preferencias sin editar código.
- **Información adicional:** valorar datos de red u otros indicadores si aportan un uso cotidiano y caben en los recursos del equipo.

## Presentación del proyecto

- Documentar resultados reales y limitaciones después de las pruebas en el LCD.
- Incorporar capturas y una explicación breve de la arquitectura para el portfolio.
- Preparar posteriormente una ficha estática en **GitHub Pages**, con descripción, imágenes y enlace al repositorio. La aplicación Python seguirá ejecutándose en la Raspberry; Pages serviría para presentar el proyecto.
- Mantener las atribuciones de los proveedores junto a la licencia MIT del código.

El criterio para priorizar es la utilidad en una Raspberry Pi 3 y una pantalla de 480×320, sin convertir cada idea en un servicio adicional que mantener.
