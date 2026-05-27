# Configuración del sistema — `config.py`

> [!CAUTION]
> **Este archivo contiene información sensible (API keys, contraseñas, credenciales de base de datos).**
> `config.py` está excluido del repositorio mediante `.gitignore`. **Nunca lo subas a Git.**

Debes crear manualmente el archivo `config.py` en la raíz del proyecto copiando la plantilla de abajo y sustituyendo cada valor según las instrucciones de cada sección.

---

## Plantilla completa

```python
# ==========================================
#   IDENTIFICACIÓN DE LA ESTACIÓN
# ==========================================

CIUDAD               = "CIUDAD, XX"          # Ver sección 1
MUNICIPIO_CONAGUA    = "MUNICIPIO"           # Ver sección 1
CLAVE_ESTADO_CONAGUA = "00"                  # Ver sección 1
LATITUD              = "00.0000"             # Ver sección 1
LONGITUD             = "-00.0000"            # Ver sección 1
FRECUENCIA_FM        = "87.5"               # Ver sección 1
POTENCIA_MW          = "10"                 # Ver sección 1

# ==========================================
#   CREDENCIALES DE APIs METEOROLÓGICAS
# ==========================================

OWM_API_KEY = "TU_API_KEY_OWM"             # Ver sección 2

# ==========================================
#   CREDENCIALES Y MODELOS DE IA
# ==========================================

GEMINI_API_KEY        = "TU_API_KEY_GEMINI" # Ver sección 3
MODELO_GEMINI          = "gemini-3-flash-preview"
MODELO_GEMINI_RESPALDO = "gemini-3.1-flash-lite"

GROQ_API_KEY = "TU_API_KEY_GROQ"           # Ver sección 3
MODELO_GROQ  = "llama-3.3-70b-versatile"

# ==========================================
#   BASE DE DATOS MySQL
# ==========================================

BD_CONFIG = {
    "host":               "TU_HOST_MYSQL",   # Ver sección 4
    "port":               3306,
    "database":           "NOMBRE_BD",
    "user":               "USUARIO_BD",
    "password":           "CONTRASEÑA_BD",
    "charset":            "utf8mb4",
    "connection_timeout": 10,
}

# ==========================================
#   SÍNTESIS DE VOZ (TTS)
# ==========================================

VOZ_TTS     = "es-MX-DaliaNeural"           # Ver sección 5
SAMPLE_RATE = 22050

# ==========================================
#   RUTAS DE ARCHIVOS
# ==========================================

CARPETA_MUSICA    = "pistas_musicales"
CARPETA_HISTORIAL = "historial_guiones"
ARCHIVO_CLIMA     = "clima_actual.wav"
ARCHIVO_TEMP_MP3  = "temp_clima.mp3"
ARCHIVO_TEMP_WAV  = "temp_clima.wav"
ARCHIVO_TEXTO     = "guion.txt"
ARCHIVO_DATOS_WEB = "datos.json"

# ==========================================
#   STREAM DE AUDIO
# ==========================================

# --- Icecast (transmisión a internet) ---
ICECAST_HOST       = "localhost"             # Ver sección 6
ICECAST_PORT       = 8000
ICECAST_MOUNTPOINT = "/stream"
ICECAST_PASSWORD   = "TU_CONTRASEÑA_ICECAST"
ICECAST_USER       = "source"
ICECAST_BITRATE_K  = 16

# --- Auxiliar (salida de audio local por tarjeta USB) ---
AUX_HABILITADO         = False                        # Ver sección 7
AUX_DISPOSITIVO        = "plughw:1,0"
AUX_SAMPLE_RATE_SALIDA = 22050

# ==========================================
#   SCHEDULER DE ACTUALIZACIONES
# ==========================================

HORAS_PROGRAMADAS = [                        # Ver sección 8
    "03:00", "05:00", "06:01", "06:30", "07:00", "07:30", "08:00", "08:30",
    "09:00", "09:30", "10:00", "10:30", "11:00", "11:30", "12:00",
    "12:30", "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
    "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00",
    "19:30", "20:00", "20:30", "21:00", "21:30", "22:00", "22:30",
    "23:00", "23:30", "00:01"
]

# ==========================================
#   CONFIGURACIÓN SÍSMICA
# ==========================================

# --- Telegram (Telethon) ---
TELEGRAM_API_ID   = TU_API_ID               # Ver sección 9
TELEGRAM_API_HASH = "TU_API_HASH"
TELEGRAM_CANAL    = "sassla"

# --- Alerta sonora ---
ARCHIVO_ALERTA_SISMICA  = "alerta_sismica.wav"
ARCHIVO_SILENCIO        = "silencio.wav"
ARCHIVO_SISMO_REPORTE   = "sismo_reporte.wav"
ARCHIVO_SISMO_ESPERA    = "sismo_espera.wav"
ARCHIVO_SISMO_LOCAL     = "ultimo_sismo.json"
REPETICIONES_SISMO_REAL = 15
REPETICIONES_SIMULACRO  = 9
CICLOS_ENRIQUECIMIENTO  = 4

# --- Consultas post-evento ---
SSN_RSS_URL             = "http://www.ssn.unam.mx/rss/ultimos-sismos.xml"

# --- Bounding box México para consultas USGS ---
SISMO_MIN_LAT = 14.0
SISMO_MAX_LAT = 20.0
SISMO_MIN_LON = -106.0
SISMO_MAX_LON = -92.0
SISMO_MIN_MAG = 3.5

# --- Calendario de simulacros ---
ARCHIVO_SIMULACROS = "simulacros.json"
```

---

## Sección 1 — Identificación de la estación

| Parámetro | Descripción | Ejemplo |
|---|---|---|
| `CIUDAD` | Nombre de la ciudad tal como lo espera **OpenWeatherMap** (ciudad + código ISO del país). | `"Pachuca, MX"` |
| `MUNICIPIO_CONAGUA` | Nombre del municipio **exacto** que usa CONAGUA (sin coma, sin país). | `"Pachuca de Soto"` |
| `CLAVE_ESTADO_CONAGUA` | Clave numérica de dos dígitos del estado en CONAGUA. Consulta la [tabla de claves](https://smn.conagua.gob.mx/es/climatologia/informacion-climatologica/informacion-estadistica-climatologica). | `"13"` (Hidalgo) |
| `LATITUD` / `LONGITUD` | Coordenadas decimales de la estación (usadas por **Open-Meteo AQI**). Puedes obtenerlas en [latlong.net](https://www.latlong.net/). | `"20.1011"` / `"-98.7591"` |
| `FRECUENCIA_FM` | Frecuencia FM en MHz (solo informativa, se usa en el guion de voz). | `"87.5"` |
| `POTENCIA_MW` | Potencia de emisión en mW (solo informativa). | `"10"` |

---

## Sección 2 — API de OpenWeatherMap (OWM)

| Parámetro | Descripción |
|---|---|
| `OWM_API_KEY` | Clave de la API REST de OpenWeatherMap. |

**Cómo obtenerla:**
1. Regístrate en [openweathermap.org](https://openweathermap.org/api).
2. Ve a *My API Keys* y copia la clave predeterminada (o crea una nueva).
3. El plan **gratuito** (*Free*) es suficiente para el sistema; incluye hasta 1 000 llamadas/día.

> [!NOTE]
> Las claves nuevas pueden tardar hasta 10 minutos en activarse.

---

## Sección 3 — IA generativa (Gemini y Groq)

### Google Gemini

| Parámetro | Descripción |
|---|---|
| `GEMINI_API_KEY` | Clave de la API de Google Gemini. |
| `MODELO_GEMINI` | Modelo principal a usar. |
| `MODELO_GEMINI_RESPALDO` | Modelo de respaldo si el principal falla o está saturado. |

**Cómo obtener la clave:**
1. Accede a [Google AI Studio](https://aistudio.google.com/app/apikey).
2. Haz clic en **Create API Key** y copia el valor.

**Modelos disponibles comunes:**

| Modelo | Velocidad | Calidad | Uso recomendado |
|---|---|---|---|
| `gemini-3-flash-preview` | Rápido | Alta | Producción (principal) |
| `gemini-3.1-flash-lite` | Muy rápido | Media | Respaldo / bajo costo |
| `gemini-3.1-pro` | Lento | Muy alta | Pruebas de calidad |

### Groq

| Parámetro | Descripción |
|---|---|
| `GROQ_API_KEY` | Clave de la API de Groq (alternativa de baja latencia). |
| `MODELO_GROQ` | Modelo LLM servido por Groq. |

**Cómo obtener la clave:**
1. Regístrate en [console.groq.com](https://console.groq.com/keys).
2. Crea una API Key y cópiala.

> [!TIP]
> Groq es útil como respaldo si Gemini experimenta latencia alta; ofrece inferencia muy rápida en hardware dedicado.

---

## Sección 4 — Base de datos MySQL

```python
BD_CONFIG = {
    "host":     "hostname o IP del servidor MySQL",
    "port":     3306,               # Puerto estándar; cambia si es diferente
    "database": "nombre_de_la_bd",
    "user":     "usuario_mysql",
    "password": "contraseña_mysql",
    "charset":  "utf8mb4",          # No modificar
    "connection_timeout": 10,       # Segundos antes de abortar la conexión
}
```

> [!IMPORTANT]
> El usuario MySQL debe tener permisos `SELECT`, `INSERT`, `UPDATE`, `DELETE` sobre la base de datos especificada. El esquema de tablas se encuentra en `drift3_26noaa.sql`.

---

## Sección 5 — Síntesis de voz (TTS)

| Parámetro | Descripción |
|---|---|
| `VOZ_TTS` | Nombre de la voz de **edge-tts** que se usará para narrar el guion. |
| `SAMPLE_RATE` | Frecuencia de muestreo del pipeline de audio en Hz. **No modificar** salvo que cambies el pipeline. |

**Voces en español disponibles (edge-tts):**

| Identificador | Variante | Género |
|---|---|---|
| `es-MX-DaliaNeural` | México | Femenino |
| `es-MX-JorgeNeural` | México | Masculino |
| `es-ES-ElviraNeural` | España | Femenino |
| `es-ES-AlvaroNeural` | España | Masculino |
| `es-AR-ElenaNeural` | Argentina | Femenino |

Para ver todas las voces disponibles ejecuta:
```bash
edge-tts --list-voices | grep "^es-"
```

---

## Sección 6 — Stream de audio

| Parámetro | Descripción | Valor típico |
|---|---|---|
| `ICECAST_HOST` | Hostname o IP donde corre Icecast2. | `"localhost"` |
| `ICECAST_PORT` | Puerto TCP de Icecast2. | `8000` |
| `ICECAST_MOUNTPOINT` | Punto de montaje del stream. | `"/stream"` |
| `ICECAST_USER` | Usuario fuente (source). | `"source"` |
| `ICECAST_PASSWORD` | Contraseña del source definida en `icecast.xml`. | *(la que configuraste)* |
| `ICECAST_BITRATE_K` | Bitrate del MP3 en kbps. A menor bitrate, menor carga de CPU. | `16` |

> [!NOTE]
> La contraseña debe coincidir exactamente con `<source-password>` en tu `icecast.xml`. Si Icecast corre en otro equipo, cambia `ICECAST_HOST` a su IP o nombre de host.

---

## Sección 7 — Salida auxiliar por USB (para transmisor FM)

| Parámetro | Descripción |
|---|---|
| `AUX_HABILITADO` | `True` para activar la salida de audio a una tarjeta de sonido USB externa vía ALSA; `False` para desactivarla. |
| `AUX_DISPOSITIVO` | Nombre del dispositivo ALSA de la tarjeta de sonido USB. Formato típico: `"plughw:1,0"`. Verificar con `aplay -l`. |
| `AUX_SAMPLE_RATE_SALIDA` | Frecuencia de muestreo para la rama auxiliar. Se recomienda usar `22050` (mismo que el pipeline) para evitar resampleo. |

> [!NOTE]
> El prefijo `plughw:` permite que ALSA realice conversión automática de formato si la tarjeta no soporta 22050 Hz directamente. Para identificar el dispositivo correcto, ejecutar `aplay -l` y buscar la tarjeta USB.

---

## Sección 8 — Scheduler de actualizaciones

```python
HORAS_PROGRAMADAS = ["HH:MM", "HH:MM", ...]
```

Lista de horarios en formato `"HH:MM"` (24 h) en los que el sistema generará y publicará un nuevo boletín de clima. Puedes agregar o eliminar entradas libremente.

> [!TIP]
> Para evitar sobrecarga de APIs durante horas de madrugada, puedes reducir la frecuencia fuera del horario pico (ej. dejar solo `"03:00"` y `"05:00"` entre la medianoche y las 6 AM).

---

## Sección 9 — Configuración Sísmica

| Parámetro | Descripción |
|---|---|
| `TELEGRAM_API_ID` | Tu API ID de Telegram (entero). Obtener en https://my.telegram.org → API development tools. |
| `TELEGRAM_API_HASH` | Tu API Hash de Telegram (cadena de texto). |
| `TELEGRAM_CANAL` | Canal público a monitorear para alertas sísmicas (ej. `"sassla"`). |
| `REPETICIONES_SISMO_REAL` | Número de repeticiones del sonido de alerta para sismos reales. |
| `REPETICIONES_SIMULACRO` | Número de repeticiones del sonido de alerta para simulacros. |
| `CICLOS_ENRIQUECIMIENTO` | Número de ciclos de reporte en los que se re-consultan las APIs sísmicas para actualizar magnitud/epicentro. |
| Bounding box (`SISMO_*`) | Coordenadas y magnitud mínima para filtrar sismos del USGS que afecten el área de interés. |
| `ARCHIVO_SIMULACROS` | Archivo JSON con las fechas y horas de simulacros programados. |

---

## Verificación rápida

Una vez creado el archivo, ejecuta el siguiente comando para comprobar que Python lo importa sin errores:

```bash
python -c "import config; print('config.py cargado correctamente')"
```

Si ves el mensaje de éxito, el sistema está listo para arrancar.
