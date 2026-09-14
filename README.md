# SmartAds Retail Optimization

Sistema automatizado para gestionar campañas de **Meta Ads** (Facebook/Instagram) en retail (específicamente carnicerías). El sistema pausa o activa los *conjuntos de anuncios* (AdSets) automáticamente según el contexto del momento:

- **Clima** (código meteorológico, temperatura máxima y probabilidad de lluvia) de [Open-Meteo](https://open-meteo.com/).
- **Calendario** (fines de semana y quincena/fin de mes).
- **Horarios y días** configurables por anuncio mediante reglas editables por Telegram.

No incluye gestión de stock ni control del presupuesto.

---

## Stack Tecnológico

| Tecnología | Uso |
| --- | --- |
| **Python** 3.10+ | Lenguaje principal |
| [facebook-business](https://pypi.org/project/facebook-business/) | SDK oficial de Meta Marketing API (consultar y cambiar estado de AdSets) |
| [requests](https://pypi.org/project/requests/) | Cliente HTTP para consumir Open-Meteo |
| [python-telegram-bot](https://docs.python-telegram-bot.org/) v20+ (`[job-queue]`) | Bot de Telegram, comandos y tareas programadas |
| [holidays](https://pypi.org/project/holidays/) | Feriados de Argentina |
| [python-dotenv](https://pypi.org/project/python-dotenv/) | Variables de entorno desde `.env` |

---

## Estructura del Proyecto

```
SmartAdsRetailOptimization/
├── main.py                          # Orquestador: arranca jobs (cada 30 min + reportes) y el bot
├── requirements.txt                 # Dependencias
├── .env.example                     # Plantilla de configuración (crear un .env a partir de ella)
├── AGENTS.md                        # Contexto para asistentes de IA
├── src/
│   ├── config/
│   │   ├── settings.py              # Dataclass Configuracion + validaciones (lee el .env)
│   │   ├── reglas_negocio.py        # Persistencia JSON de las reglas de cada anuncio
│   │   ├── reglas_conjuntos.json    # Reglas activas (runtime, no versionado)
│   │   └── reglas_conjuntos.ejemplo.json  # Regla de ejemplo para empezar
│   ├── core/
│   │   └── brain.py                 # MotorDecisiones: lógica pura, sin red ni persistencia
│   └── services/
│       ├── context_api.py           # GestorContexto: clima Open-Meteo + calendario
│       ├── meta_api.py              # GestorMetaAds: operaciones sobre AdSets (simulado/real)
│       └── telegram_bot.py          # BotTelegram: comandos, reportes, alertas, /adsinfo
└── tests/
    └── test_sistema.py              # Suite de pruebas (23 tests)
```

---

## Configuración (`.env`)

Copia `.env.example` como `.env` y completá los valores:

```bash
cp .env.example .env
```

| Variable | Descripción | Default |
| --- | --- | --- |
| `META_ACCESS_TOKEN` | Token de acceso de la API de Meta Ads | *(vacío)* |
| `META_ACCOUNT_ID` | ID de la cuenta publicitaria (se acepta con o sin prefijo `act_`) | *(vacío)* |
| `META_CAMPAIGN_ID` | ID de la campaña que administra el bot | *(vacío)* |
| `MODO_SIMULACION` | `true`: no toca Meta (dry-run); `false`: modo real | `true` |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram | *(vacío)* |
| `TELEGRAM_CHAT_ID` | IDs de chats autorizados, **separados por coma** (ej: `123,456`) | *(vacío)* |
| `ENVIAR_TELEGRAM` | `true` habilita envío de reportes/alertas por Telegram | `false` |
| `LATITUD` | Latitud de la zona del negocio (Open-Meteo) | `0` |
| `LONGITUD` | Longitud de la zona del negocio (Open-Meteo) | `0` |
| `OPEN_METEO_URL` | Endpoint de Open-Meteo | `https://api.open-meteo.com/v1/forecast` |
| `TIMEOUT_RED` | Timeout (segundos) de la llamada HTTP al clima | `10` |

> **Seguridad:** nunca subas el `.env` real al repositorio. Solo el bot reenvía mensajes del chat autorizado; si falta el token, el bot arranca pero no envía reportes.

---

## Cómo Funciona

### Ciclo de ejecución

`main.py` arranca un `OrquestadorAsincrono` que registra **3 tareas** en su cola:

| Tarea | Cuándo | Qué hace |
| --- | --- | --- |
| `evaluar_anuncios` | Cada **30 min** | Lee clima + consulta AdSets de Meta → decide y aplica ACTIVAR/PAUSAR si hace falta. Actualiza el cache de `/adsinfo`. |
| `reporte_6` | Todos los días **06:00** | Envía el reporte diario por Telegram (clima + anuncios activos + sin configurar). |
| `reporte_15` | Todos los días **15:00** | Reenvía el reporte diario por Telegram. |

Si Open-Meteo no responde, el sistema **no interrumpe la ejecución**: asume clima "no disponible" (sin temperatura) y deja los anuncios sin modificar. Si Meta falla, se omite el ciclo y se envía una **alerta** por Telegram.

### Motor de decisiones (`brain.py`)

Para cada AdSet con una regla configurada y activa, el motor calcula el *estado deseado*:

```
estado_deseado = ACTIVO si TODAS las condiciones coinciden
```

1. **Horario**: hora actual dentro de `[hora_activacion, hora_desactivacion]` (admite rangos que cruzan medianoche).
2. **Día**: el día de la semana (L, MA, MI, J, V, S, D) está habilitado.
3. **Temperatura**: `temperatura_minima <= temperatura actual <= temperatura_maxima`.
4. **Lluvia**: `lluvia_minima <= probabilidad de lluvia <= lluvia_maxima`.

Solo genera una acción cuando el **estado deseado difiere del estado actual** en Meta. Los anuncios **sin regla** o con regla `activo: false` **nunca se modifican**.

---

## Comandos de Telegram

Con el bot corriendo y `ENVIAR_TELEGRAM=true`, enviá estos comandos desde un **chat autorizado** (`TELEGRAM_CHAT_ID`):

| Comando | Descripción |
| --- | --- |
| `/comandos` | Lista los comandos disponibles. |
| `/ads` | Lista los AdSets de la campaña con su estado en Meta y si están configurados. |
| `/adsconfig [nombre_anuncio]` | Devuelve la plantilla rellenada con la configuración guardada del anuncio, lista para editar. |
| `/adsinfo` | Reporte bajo demanda con la **última lectura** en memoria (sin consultar Meta): clima, temperatura, lluvia, anuncios activos y sin configurar. Si aún no hay datos, indica en cuántos minutos será la próxima lectura. |

### Editar una regla desde Telegram

1. Enviá `/adsconfig ASADO` para recibir la plantilla.
2. Rellená los campos entre corchetes y devolvés el texto modificado al chat.
3. Para **desactivar** el anuncio sin perder la regla, poné un punto (`.`) en `Desactivar anuncio: [.]`, y devolvés el texto.
4. Para **deshabilitar** un día de la semana, poné un punto (`.`) dentro de sus corchetes (ej: `J[.]`).

> Cualquier mensaje proveniente de un chat **no autorizado** se ignora (responde "Acceso denegado." y registra el intento), sin procesar plantillas, persistir configuraciones ni tocar Meta.

---

## Formato de Reglas (JSON)

Las reglas viven en `src/config/reglas_conjuntos.json` (se crea vacío si no existe) bajo la clave `conjuntos`. Ejemplo de `reglas_conjuntos.ejemplo.json`:

```json
{
  "conjuntos": {
    "asado": {
      "activo": true,
      "hora_activacion": "6:00",
      "hora_desactivacion": "19:00",
      "temperatura_minima": 0.0,
      "temperatura_maxima": 50.0,
      "lluvia_minima": 0.0,
      "lluvia_maxima": 60.0,
      "dias": {
        "L": true,
        "MA": true,
        "MI": true,
        "J": false,
        "V": false,
        "S": false,
        "D": false
      }
    }
  }
}
```

| Campo | Descripción |
| --- | --- |
| `activo` | `true` habilita la evaluación del anuncio; `false` lo deja pausado sin borrar la regla. |
| `hora_activacion` / `hora_desactivacion` | Ventana horaria (formato 24 hs, `HH:MM`). |
| `temperatura_minima` / `temperatura_maxima` | Rango de temperatura de activación (°C). |
| `lluvia_minima` / `lluvia_maxima` | Rango de probabilidad de lluvia (%). |
| `dias` | `L MA MI J V S D`; `true` habilita el día. Un anuncio con todos los días vacíos queda siempre pausado. |

La coincidencia por nombre no distingue mayúsculas ni espacios: `ASADO`, `asado` y `Asado` refieren a la misma regla.

---

## Modo Simulación vs. Modo Real

| Aspecto | `MODO_SIMULACION=true` | `MODO_SIMULACION=false` |
| --- | --- | --- |
| AdSets consultados | Conjuntos simulados creados a partir de las reglas (`id=simulado-<nombre>`) | Reales, de la campaña `META_CAMPAIGN_ID` |
| Cambios de estado | **No** llama a Meta (solo registra `DRY-RUN` en log) y refleja el estado en memoria | Pausa/activa el AdSet real vía la API de Meta |
| Credenciales Meta | No requeridas | Requeridas (`META_ACCESS_TOKEN`, `META_ACCOUNT_ID`, `META_CAMPAIGN_ID`) |
| Riesgo | Ninguno | Modifica campañas reales |

> **Recomendación:** empezá en modo simulación, validá que los logs y reportes sean correctos y recién entonces activá el modo real.

---

## Instalación y Ejecución

```bash
# 1. Crear y activar el entorno virtual
python -m venv .venv

# 2. Instalar dependencias
.venv\Scripts\pip install -r requirements.txt     # Windows
source .venv/bin/pip install -r requirements.txt  # Linux/macOS

# 3. Configurar variables de entorno
cp .env.example .env                              # luego editá .env

# 4. Opcional: partir de una regla de ejemplo
cp src\config\reglas_conjuntos.ejemplo.json src\config\reglas_conjuntos.json

# 5. Ejecutar el orquestador (bot + tareas programadas)
.venv\Scripts\python main.py                      # Windows
source .venv/bin/python main.py                   # Linux/macOS
```

---

## Tests

```powershell
# Windows (PowerShell)
$env:PYTHONDONTWRITEBYTECODE=1
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

```bash
# Linux/macOS
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -v
```