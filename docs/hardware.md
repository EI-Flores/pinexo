# Reference hardware and display

PiNexo is designed to put a **Raspberry Pi 3** with a small display to use as a personal dashboard. The application can be previewed in a window, but its interface is designed for **480×320**.

## Reference setup

| Component | Reference |
|---|---|
| Computer | Raspberry Pi 3. |
| Display | 3.5-inch GPIO/SPI LCD, 480×320. |
| Board marking | “3.5inch RPi LCD (A) V3”. |
| Detected display driver | ili9486. |
| Listed touch controller | XPT2046; recognized by Linux through ads7846. |
| Operating system | 64-bit Debian 13 Trixie, with a Raspberry Pi kernel and firmware. |
| Desktop | labwc on Wayland. |
| Current input | Mouse and keyboard; touch events supported, calibration pending. |

The board marking helps identify the display, but does not guarantee that all similar-looking LCDs share the same wiring or controller. PiNexo requires the desktop to already display correctly on the screen; it does not install an LCD driver itself.

The Raspberry Pi's hostname is independent of the **PiNexo** project name. Installing the project does not require changing it.

## Connection and power

Connect the display to the GPIO header with the computer powered off, following the orientation indicated on the board. Use a suitable power supply for the Raspberry Pi and its peripherals. Power stability affects both the display and the computer's operation.

If another display is connected, the application looks for a single **480×320** output. If it cannot identify one, it reports the detected outputs. For a desktop preview, use **python3 app.py --windowed**; the **--display** option lets you choose an SDL display index when there are multiple outputs.

## Reference LCD configuration

On the reference system, the native DRM/KMS driver worked with **piscreen**. The reference configuration includes these lines in the **[all]** section of **/boot/firmware/config.txt**:

```ini
dtparam=spi=on
dtoverlay=piscreen,drm,speed=16000000,rotate=0
```

The system's **vc4-kms-v3d** driver was retained. This configuration is a reference for the identified display; check the model, the system's overlay documentation, and the existing configuration before applying it. Avoid duplicating lines that are already present, and keep a copy of config.txt if you need to modify it.

Once the desktop appears on the LCD, installing or updating PiNexo does not itself require changing that configuration or rebooting. The desktop must be available in the user's session for the dashboard to appear.

## Touch status

Linux recognizes the touch device, but calibration and alignment with the image are still pending. The application includes large targets and touch events; these do not themselves correct the controller's orientation, axes, or calibration.

A completed calibration procedure is not provided. The next step is to check events, orientation, and alignment on the physical display. In the meantime, the dashboard is used with a mouse and keyboard, including through remote desktop when the visible session is shared.

The [five-point touch diagnostic](touch-calibration.md) measures alignment and can propose a correction for review. It does not apply settings or establish that the physical touchscreen is calibrated.

## Checking the physical setup

First, check the desktop on the LCD. Then test **Inicio**, navigation to the weather module, both themes, satellite playback, pause, zoom, and dragging. Verify that the observation timestamp still corresponds to the selected frame when regional detail is requested.

The remote view confirms part of the interface, but smoothness must also be checked on the GPIO LCD. The repository does not claim universal compatibility or completed touch calibration; local software tests complement hardware checks.

## References

- [Raspberry Pi configuration documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html).
- [Raspberry Pi firmware overlays](https://github.com/raspberrypi/firmware/blob/master/boot/overlays/README).
- [labwc](https://labwc.github.io/labwc-config.5.html).
- [Pygame in Debian Trixie](https://packages.debian.org/trixie/python3-pygame).
