# Contribuir a PiNexo

Los cambios deben conservar una interfaz legible en 480×320 y un uso moderado
de memoria, CPU y red en la Raspberry Pi 3.

## Preparar y comprobar un cambio

1. Crea una rama para el cambio y explica el problema que resuelve.
2. Usa `config.json.example` como base de tu configuración local. `config.json`
   queda excluido del repositorio.
3. Instala las dependencias de desarrollo y ejecuta las pruebas sin conexión:

   ```sh
   python -m pip install -r requirements-dev.txt
   python -m unittest discover -s tests -t . -v
   ```

4. Si cambias la interfaz, prueba ambos temas en 480×320, la navegación y el
   regreso a Inicio. Adjunta una captura y distingue la pantalla simulada de
   una prueba en el LCD.
5. Describe en la propuesta qué cambió, cómo lo verificaste y cualquier
   limitación pendiente.

Las pruebas no deben consultar proveedores reales, ejecutar systemd ni leer
la caché personal. Usa fixtures, carpetas temporales y servicios simulados.
Verifica también las respuestas incompletas, las fechas y la conservación de
datos válidos ante fallos.

Los módulos futuros deben permitir volver a Inicio y respetar el tema elegido.
No añadas cuentas, credenciales o integraciones de mensajes como si ya
estuvieran configuradas. Las atribuciones de datos e imágenes deben conservarse.

Al reportar un problema, evita publicar contraseñas, tokens, direcciones de
correo, IP del equipo o archivos personales. Incluye únicamente la salida
necesaria para reproducirlo.
