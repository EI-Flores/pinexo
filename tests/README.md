# Offline tests

From the repository root, using Python 3.12:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t . -v
```

The tests use local data and a simulated 480×320 SDL display.
They do not require a Raspberry Pi, desktop session, accounts, GPIO, or a
connection to NOAA. Temporary files are removed when the tests finish.
The tests do not read the user's cache, modify user settings, or run systemd.

To run the tests against another source tree, set `PI_CLIMA_TEST_PROJECT`
to its absolute path. This is usually unnecessary: the application modules
are located at the repository root.

The tests cover caching and provider failures, dates and satellite geometry,
downloads with a bounded queue, rain thresholds, service safeguards,
preferences, the menu, navigation, and rejection of outdated detail responses.
