# Actualizar el panel instalado antes de PiNexo

El proyecto partió de una instalación llamada `pi-clima`. PiNexo conserva los
nombres internos del servicio y la caché para aprovechar esa configuración.
El nombre de red de la Raspberry sigue siendo independiente del proyecto.

## Pasar de la carpeta anterior al repositorio

En la Raspberry, detén el servicio y cierra cualquier instancia manual antes
de cambiar la ubicación del programa:

```bash
systemctl --user stop pi-clima.service
tar -czf "$HOME/pi-clima-backup-$(date +%Y%m%d-%H%M%S).tar.gz" -C "$HOME" pi-clima
git clone https://github.com/EI-Flores/pinexo.git "$HOME/pinexo"
cp "$HOME/pi-clima/config.json" "$HOME/pinexo/config.json"
cd "$HOME/pinexo"
python3 manage.py enable
```

Esto supone que la instalación anterior está en `~/pi-clima` y que
`~/pinexo` no existe todavía. Si tus rutas son distintas, ajústalas antes.
Una ausencia del servicio significa que no hay nada automático que detener;
revisa cualquier otro error antes de continuar.

`manage.py enable` actualiza la unidad que reconoce como administrada por
este proyecto y cambia su ruta al nuevo `app.py`. Conserva las preferencias
y los datos de `~/.cache/pi-clima`. La carpeta anterior y su copia quedan
disponibles para volver a ella. No requiere reiniciar el equipo ni cambiar
el controlador de la pantalla.

## Actualizaciones siguientes

En una instalación limpia sin cambios locales en archivos de código:

```bash
systemctl --user stop pi-clima.service
cd ~/pinexo
git pull --ff-only
python3 manage.py enable
```

No continúes con el último paso si la actualización falla. `config.json`
está excluido del repositorio y se conserva. Si modificaste código, guarda
tus cambios en una rama o revisa la diferencia antes de actualizar.

## Volver al programa anterior

Si conservaste la carpeta antigua, detén el servicio y reinstala su ruta:

```bash
systemctl --user stop pi-clima.service
cd ~/pi-clima
python3 manage.py enable
```

Usa sólo una de las instalaciones a la vez para evitar dos ventanas del panel.
