# Measuring touchscreen alignment

The standalone `tools/touch_calibration.py` tool helps diagnose inaccurate touch targets on the reference **480×320 GPIO LCD**. It displays five cyan crosses, shows the position received from the desktop in orange, and records a contact at each target. It does not download weather data, install drivers, edit configuration, or reload the desktop.

The tool can estimate an affine correction for orientation, scale, and offset. Its result is a **proposal for review**, not proof that the touchscreen is calibrated. Physical response time and reliability must still be tested on the Raspberry Pi.

## Before measuring

- Use the physical LCD and stylus. Remote mouse clicks cannot calibrate the sensor.
- The LCD must already display the labwc desktop correctly.
- The saved `~/.config/labwc/rc.xml` must contain one explicit `ADS7846 Touchscreen` libinput profile with a six-value `calibrationMatrix`, and one touch entry mapping that device to the LCD output.
- The saved configuration must already have been reloaded by labwc. Reading the file does not reveal the running compositor's actual calibration.
- Use the LCD at its normal output transform and scale 1, with a 480×320 fullscreen window. The tool refuses ambiguous display selection.
- Use Python 3.10 or later with Debian's `python3-pygame` package, which PiNexo already requires.

The current orientation candidate for the reference device is `0 1 0 -1 0 1`, based on captured raw corner coordinates. It is not a universal setting for other GPIO displays, and it does not by itself measure edge scale or offsets.

## Run the measurement

Close manually launched dashboard instances. If automatic startup is enabled, stop the existing user service:

```bash
systemctl --user stop pi-clima.service
```

From the repository directory, run:

```bash
python3 tools/touch_calibration.py --output "$HOME/pinexo-touch-report.json"
```

The script is standalone and can also be copied to another directory without copying the rest of PiNexo. Run it as the desktop user, without `sudo`. When launched through SSH, it attempts to locate a unique labwc session belonging to that user; if this is ambiguous, run it from a terminal in the LCD's desktop.

Touch each cyan cross in the order displayed: **center, top-left, top-right, bottom-right, bottom-left**. Hold the stylus still for approximately one second, then lift it before the next target. The orange marker and displayed coordinates show where the application receives the contact. A short or unstable contact is rejected and the same target remains active. Press Escape to cancel.

After a complete run, inspect the report:

```bash
cat "$HOME/pinexo-touch-report.json"
```

Restore an automatically started dashboard after the tool exits, including after cancellation:

```bash
systemctl --user start pi-clima.service
```

The optional `--config /absolute/path/rc.xml` argument selects another saved configuration. `--windowed` is for software previews only and never produces an LCD calibration proposal.

## Interpret the report

The report records the saved matrix, five observed and requested positions, contact stability, and errors in pixels. Stable measurements with a suitable affine fit can produce `status: proposed` and a `proposed_labwc_value`. Insufficient, unstable, or inconsistent measurements produce `status: invalid` with reasons.

`active_matrix_verified` and `applied` remain false. The proposed matrix composes the measured screen correction with the matrix in the saved file. It depends on that saved matrix actually being active and on the display and input assumptions above. Do not copy the result blindly into a different device or output setup.

The fitted error describes these five measurements; it does not predict future accuracy or prove that intermittent input loss is resolved. Keep a configuration backup, review the proposal, and test center, edges, button activation, releases, and persistence after any subsequent configuration change.

## References

- [labwc touch mapping and calibration](https://labwc.github.io/labwc-config.5.html#entry_libinput_device_calibrationmatrix).
- [libinput absolute-coordinate calibration](https://wayland.freedesktop.org/libinput/doc/latest/absolute-axes.html#calibration-of-absolute-devices).
