# Smart-Ads Retail Optimization (Project Context)

## Descripción del Proyecto
Este es un sistema automatizado para gestionar campañas de Meta Ads (Facebook/Instagram) destinado a retail (específicamente carnicerías). El sistema toma decisiones de presupuesto y estado de las campañas (ACTIVO/PAUSADO) basándose en factores de contexto: clima (OpenMeteo API) y calendario (feriados, fines de semana, quincenas). No incluye gestión de stock.

## Stack Tecnológico
*   **Lenguaje:** Python 3.10+
*   **APIs Externas:** 
    *   `facebook-business` (Meta Marketing API SDK) para modificar ads.
    *   `requests` para consumir OpenMeteo (Clima).
    *   `twilio` (Twilio Sandbox for WhatsApp) para enviar reportes diarios.
*   **Librerías Auxiliares:** `datetime`, `holidays` (para feriados en Argentina), `python-dotenv` (para variables de entorno).

## Estructura del Código
El proyecto sigue un patrón modular. Cuando sugieras código, respeta esta separación de responsabilidades:
*   `context_api.py`: Funciones puras para obtener clima y fechas.
*   `brain.py`: Contiene la lógica de negocio y las reglas condicionales puras. No hace peticiones de red, solo recibe diccionarios y devuelve listas de acciones.
*   `meta_api.py`: Contiene las clases/funciones para interactuar con el SDK de Meta.
*   `whatsapp_bot.py`: Módulo aislado para enviar el resumen del día usando Twilio.
*   `main.py`: El orquestador que importa todos los módulos y ejecuta el flujo secuencial.

## Reglas de Programación y Estilo
1.  **Idioma:** Todo el código (variables, funciones, comentarios) debe estar en **español** para facilitar la lectura del cliente, excepto las palabras clave propias del SDK de Meta (ej. `daily_budget`, `status`, `ACTIVE`, `PAUSED`).
2.  **Manejo de Secretos:** NUNCA hardcodees tokens, IDs de campañas o contraseñas. Usa `os.getenv()` asumiendo la existencia de un archivo `.env`.
3.  **Logs y Manejo de Errores:** Usa el módulo `logging` de Python en lugar de `print()`. Maneja siempre las excepciones de red (ej. si la API del clima no responde, asume que no llueve para no frenar la ejecución).
4.  **Tipado:** Usa Type Hints (`-> list`, `: dict`, etc.) en todas las funciones.
5.  **paradigma:** Usa el paradigma de programacion orientado a objetos.