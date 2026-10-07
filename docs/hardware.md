# Hardware y pantalla de referencia

PiNexo se desarrolla para aprovechar una **Raspberry Pi 3** con una pantalla pequeña como panel personal. La aplicación puede previsualizarse en ventana, pero su interfaz está diseñada para **480×320**.

## Equipo utilizado como referencia

| Elemento | Referencia |
|---|---|
| Equipo | Raspberry Pi 3. |
| Pantalla | LCD GPIO/SPI de 3.5 pulgadas, 480×320. |
| Inscripción de la placa | «3.5inch RPi LCD (A) V3». |
| Controlador gráfico detectado | ili9486. |
| Controlador táctil indicado | XPT2046; reconocido por Linux mediante ads7846. |
| Sistema | Debian 13 Trixie de 64 bits, con kernel y firmware para Raspberry Pi. |
| Escritorio | labwc sobre Wayland. |
| Interacción actual | Ratón y teclado; eventos táctiles preparados, calibración pendiente. |

La inscripción de la placa ayuda a identificarla, pero no garantiza que todos los LCD de apariencia similar compartan el mismo cableado o controlador. PiNexo necesita que el escritorio ya se vea correctamente en la pantalla; no instala un controlador LCD por su cuenta.

El nombre de red de la Raspberry es independiente del nombre **PiNexo**. No hace falta cambiarlo para instalar el proyecto.

## Conexión y alimentación

Coloca la pantalla en el GPIO con el equipo apagado y siguiendo la orientación indicada por su placa. Usa una fuente adecuada para la Raspberry y sus periféricos. La estabilidad de la alimentación afecta tanto a la pantalla como al funcionamiento del equipo.

Si hay otra pantalla conectada, la aplicación busca una única salida de **480×320**. Si no puede identificarla, informa las salidas detectadas. Para una prueba en el escritorio usa **python3 app.py --windowed**; la opción **--display** permite elegir un índice SDL cuando hay varias salidas.

## Configuración LCD de referencia

En el sistema utilizado, el controlador nativo DRM/KMS funcionó con **piscreen**. La configuración de referencia incluye estas líneas en la sección **[all]** de **/boot/firmware/config.txt**:

```ini
dtparam=spi=on
dtoverlay=piscreen,drm,speed=16000000,rotate=0
```

Se mantuvo el controlador **vc4-kms-v3d** del sistema. Esta es una referencia para la pantalla identificada; comprueba el modelo, la documentación de los overlays del sistema y la configuración existente antes de aplicarla. Evita duplicar líneas que ya estén presentes y conserva una copia de config.txt si necesitas modificarlo.

Una vez que el escritorio aparece en el LCD, instalar o actualizar PiNexo no necesita alterar esa configuración ni reiniciar por sí mismo. El escritorio debe estar disponible en la sesión del usuario para que el panel se muestre.

## Estado del touch

Linux reconoce el dispositivo táctil, pero su calibración y correspondencia con la imagen siguen pendientes. La aplicación incluye zonas grandes y eventos de toque; eso no corrige por sí solo la orientación, los ejes o la calibración del controlador.

No se incluye un procedimiento de calibración como si ya estuviera resuelto. El siguiente trabajo será comprobar eventos, orientación y alineación en la pantalla física. Mientras tanto, el panel se utiliza con ratón y teclado, incluyendo escritorio remoto cuando la sesión visible se comparte.

## Comprobación en el equipo

Comprueba primero el escritorio en el LCD. Después prueba Inicio, navegación al clima, ambos temas, reproducción satelital, pausa, zoom y arrastre. Verifica que la hora de captura siga correspondiendo al cuadro seleccionado cuando se solicita un detalle regional.

La vista remota confirma parte de la interfaz, pero la fluidez debe observarse también en el LCD GPIO. El repositorio no afirma compatibilidad universal ni una calibración táctil completada; las pruebas locales de software complementan la comprobación del hardware.

## Referencias

- [Documentación de configuración de Raspberry Pi](https://www.raspberrypi.com/documentation/computers/config_txt.html).
- [Overlays del firmware de Raspberry Pi](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README).
- [labwc](https://labwc.github.io/labwc-config.5.html).
- [Pygame en Debian Trixie](https://packages.debian.org/trixie/python3-pygame).
