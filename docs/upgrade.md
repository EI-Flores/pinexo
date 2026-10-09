# Upgrading a dashboard installed before PiNexo

The project started from an installation named `pi-clima`. PiNexo retains
the internal service and cache names to reuse that configuration.
The Raspberry Pi's hostname remains independent of the project.

## Moving from the previous directory to the repository

On the Raspberry Pi, stop the service and close any manually started instance
before changing the program's location:

```bash
systemctl --user stop pi-clima.service
tar -czf "$HOME/pi-clima-backup-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$HOME" pi-clima
git clone https://github.com/EI-Flores/pinexo.git "$HOME/pinexo"
cp "$HOME/pi-clima/config.json" "$HOME/pinexo/config.json"
cd "$HOME/pinexo"
python3 manage.py enable
```

This assumes the previous installation is in `~/pi-clima` and that
`~/pinexo` does not yet exist. If your paths differ, adjust them first.
A missing service means there is no automatic instance to stop;
check any other error before continuing.

`manage.py enable` updates the unit it recognizes as managed by this project
and changes its path to the new `app.py`. It preserves the preferences
and data in `~/.cache/pi-clima`. The previous directory and its backup remain
available if you need to revert. This does not require rebooting the computer
or changing the display driver.

## Subsequent updates

On a clean installation with no local changes to source files:

```bash
systemctl --user stop pi-clima.service
cd ~/pinexo
git pull --ff-only
python3 manage.py enable
```

Do not proceed with the last step if the update fails. `config.json`
is excluded from the repository and is preserved. If you modified the code,
save your changes on a branch or review the diff before updating.

## Returning to the previous program

If you kept the old directory, stop the service and restore its path:

```bash
systemctl --user stop pi-clima.service
cd ~/pi-clima
python3 manage.py enable
```

Use only one installation at a time to avoid opening two dashboard windows.
