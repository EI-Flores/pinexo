# Pruebas sin conexión

Desde la raíz del repositorio, con Python 3.12:

```sh
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -t . -v
```

Las pruebas usan datos locales y una pantalla SDL simulada de 480×320.
No requieren Raspberry Pi, escritorio, cuentas, GPIO ni conexión a NOAA.
Los archivos temporales se eliminan al terminar; no leen la caché personal
ni modifican la configuración del usuario. No ejecutan systemd.

Para comprobar las pruebas contra un árbol de código externo, puede definirse
`PI_CLIMA_TEST_PROJECT` con su ruta absoluta. Normalmente no hace falta:
los módulos de la aplicación se encuentran en la raíz del repositorio.

Se comprueban cachés y fallos de proveedores, fechas y geometría satelital,
descargas con cola acotada, umbrales de lluvia, protección de servicios,
preferencias, menú, navegación y descarte de detalles antiguos.
