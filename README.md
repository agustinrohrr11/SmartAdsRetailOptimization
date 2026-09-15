# Smart Ads Retail Optimization

Sistema automatizado para gestionar campañas de Meta Ads (Facebook/Instagram) en retail. Toma decisiones de presupuesto y estado de las campañas (ACTIVO/PAUSADO) según el clima (Open-Meteo) y el calendario (feriados, fines de semana, quincenas).

## Setup

1. Clonar el repositorio y entrar al proyecto:

   ```bash
   git clone <url-del-repositorio>
   cd SmartAdsRetailOptimization
   ```

2. Crear y activar el entorno virtual (Python 3.10+):

   ```bash
   python -m venv .venv
   # Windows (PowerShell)
   .venv\Scripts\Activate.ps1
   # Linux/macOS
   source .venv/bin/activate
   ```

3. Instalar las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Configurar las variables de entorno:

   ```bash
   cp .env.example .env
   ```

   Editar `.env` con los datos reales:

   | Variable             | Descripción                                       |
   | -------------------- | ------------------------------------------------- |
   | `META_ACCESS_TOKEN`  | Token de acceso de Meta Marketing API             |
   | `META_ACCOUNT_ID`    | ID de la cuenta publicitaria (con o sin `act_`)    |
   | `META_CAMPAIGN_ID`   | ID de la campaña a administrar                    |
   | `LATITUD` / `LONGITUD` | Coordenadas de la sucursal para el clima        |
   | `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram                         |
   | `TELEGRAM_CHAT_ID`   | ID(s) de chat autorizado(s), separados por coma   |
   | `MODO_SIMULACION`    | `true` = no toca Meta (simula acciones)           |
   | `ENVIAR_TELEGRAM`    | `true` para enviar reportes por Telegram          |

5. Ejecutar el sistema:

   ```bash
   python main.py
   ```

## Uso rápido

- El bot evalúa las reglas cada 30 minutos y manda reportes diarios a las 06:00 y 15:00.
- Comandos de Telegram: `/comandos`, `/ads`, `/adsconfig <nombre>`, `/adsinfo`, `/medir`.
- Para probar sin tocar Meta de verdad, usar `MODO_SIMULACION="true"`.
- Ejecutar los tests:

  ```bash
  python -m unittest discover -s tests -v
  ```

## Estructura

```
main.py                    Orquestador del flujo
src/services/context_api   Clima y fechas
src/services/meta_api      Integración con Meta Ads SDK
src/services/telegram_bot  Bot y reportes de Telegram
src/core/brain             Lógica de negocio y reglas
src/config                 Configuración y reglas JSON
```