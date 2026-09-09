# Instrucciones del proyecto

- Mantener la separación modular entre `config`, `core` y `services`.
- Escribir el código, variables, funciones y comentarios en español, excepto los nombres propios del SDK de Meta.
- No hardcodear tokens, IDs ni contraseñas; usar variables de entorno mediante `os.getenv()`.
- Usar `logging` en lugar de `print()` y añadir type hints a las funciones.
- Mantener la lógica de negocio pura en `src/core/brain.py`, sin peticiones de red.
