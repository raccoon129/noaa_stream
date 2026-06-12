# rev 17.0.0
# rev anterior: rev 16.8.0
# Changelog:
#   17.0.0 — OWM: se añade wind_dir_cardinal (traducción de wind_deg en grados a punto
#            cardinal en español, ej. "del noreste"). La traducción se hace en Python
#            antes del prompt para evitar alucinaciones del modelo.
#            Forecast: se añade dew_point_relevante (bool) — True únicamente cuando la
#            hora actual cae en horario nocturno, pre-amanecer o post-amanecer temprano
#            (entre las 20:00 y las 09:00). Controla la inclusión del punto de rocío
#            en la locución para los tramos donde su valor tiene impacto civil real
#            (niebla nocturna, escarcha, bancos de niebla en carreteras al amanecer).
#            Forecast (recolectar): se añade dew_point_critico (bool) — True a
#            CUALQUIER hora cuando temp_owm − dew_point ≤ 2°C (saturación crítica
#            del aire con riesgo inminente de niebla o neblina).
# Changelog:
#   16.8.0 — obtener_fase_lunar() amplía la extracción de la respuesta USNO con:
#            crepusculo_inicio/fin (sundata "Begin/End Civil Twilight"),
#            mediodia_solar (sundata "Upper Transit"), dia_semana (data.day_of_week)
#            y los campos de closestphase: fase_cercana_nombre, fase_cercana_fecha,
#            fase_cercana_hora y fase_cercana_dias (delta entero respecto a hoy;
#            negativo = pasado). Requiere migración v19 en BD.
#   16.6.0 — Se añade estimación de visibilidad de la luna durante el día (visible_de_dia)
#            y hora de tránsito superior (transit_time) en obtener_fase_lunar().
#   16.5.0 — Se migra la fuente de fase lunar de wttr.in a USNO (U.S. Naval Observatory)
#            en la función obtener_fase_lunar() usando la fecha del día actual y
#            el huso horario local (tz=-6). Se actualizan logs y errores de BD.
#   16.4.0 — Nueva fuente FUENTE 5 (wttr.in): fase lunar obtenida en tiempo real
#            vía wttr.in usando las coordenadas de config (LATITUD/LONGITUD).
#            obtener_fase_lunar() retorna moon_phase, moon_illumination,
#            moonrise, moonset y fase_etiqueta (texto en español).
#            Incorporado al dict de recolectar() como clave "lunar".
#   16.3.0 — Umbrales de cape_etiqueta calibrados para el Altiplano (~2108 m).
#            La escala NWS/NOAA estándar (<1000 débil / 1000-2499 moderado /
#            2500-3999 fuerte / ≥4000 extremo) está pensada para nivel del mar.
#            A 2100 m la columna de flotabilidad disponible es más corta, por
#            lo que valores que parecen «bajos» en la escala estándar son ya
#            operativamente significativos (fuente: NWS/NOAA, investigación
#            SciELO Altiplano mexicano, Ventusky). Nueva escala aplicada:
#              500–1499 J/kg  → convección moderada
#              1500–2499 J/kg → convección fuerte
#              ≥2500 J/kg     → convección severa (raro a esta altitud)
#            Umbral de activación sube de 300 → 500 J/kg para eliminar
#            ruido de inestabilidad débil sin señal real de tormenta.
#            Escala de referencia del prompt.py (regla 12) actualizada en
#            consonancia (Bajo <500, Moderado 500-1499, Fuerte 1500-2499,
#            Severo ≥2500).
#   16.2.0 — cape_etiqueta: se retiran los rangos numéricos del texto de la
#            etiqueta (ya aparecen en refs_str y en la regla 12 del prompt,
#            causando triple redundancia). Se mejora la precisión interpretativa:
#            300-1000 J/kg = convección moderada (no «tormentas débiles»);
#            >2500 J/kg añade granizo y actividad tornádica como información
#            civil relevante para la radio.
#   16.1.0 — cape_etiqueta ahora requiere DOBLE condición: cape_max >= 300
#            Y lluvia_relevante = True. Sin señal de lluvia el CAPE no tiene
#            valor narrativo para Huichapan (~2108 m). cape_relevante derivado
#            de cape_etiqueta (no None) en lugar de condición independiente.
#            Docstring de _extraer_forecast actualizado.
#   16.0.0 — OWM extendido: grnd_level, wind_deg, sunrise_ts/sunset_ts (unix),
#            weather_id_etiqueta (alerta de fenómeno severo). Nueva función
#            _etiqueta_weather_id() que mapea códigos OWM a etiquetas de alerta.
#            Nueva función _etiqueta_helada() para isoterma de congelación.
#            Open-Meteo Forecast extendido: dewpoint_2m y freezing_level_height
#            añadidos al request (mismo endpoint, sin petición adicional).
#            _extraer_forecast() procesa y expone dew_point y freezing_level_m.
#   15.1.0 — Nuevos campos OWM: pressure, wind_speed_kmh, wind_gust_kmh, clouds_all,
#            weather_id. AQI extendido: aerosol_optical_depth. Nueva fuente:
#            Open-Meteo Forecast horario (precipitation_probability, precipitation,
#            windspeed_10m, cape). Pre-procesamiento en Python antes del prompt.
#            Anotaciones de tipo migradas a Optional/Tuple de typing
#            para compatibilidad con Python 3.9 (Raspberry Pi OS).

import datetime
import json
from typing import Optional, Tuple

import requests

import bd
import config
import estado


# ==========================================
#   SANITIZACIÓN DE ERRORES
# ==========================================

def _sanitizar_error(mensaje):
    """Enmascara claves API en mensajes de error antes de exponerlos."""
    return bd._sanitizar_error(mensaje)


# ==========================================
#   RECOLECCIÓN OWM
# ==========================================

def obtener_clima_owm():
    # type: () -> Tuple[Optional[dict], Optional[str]]
    """
    Consulta la API de OpenWeatherMap.
    Retorna (datos_json, None) en éxito o (None, mensaje_error) en fallo.
    """
    url = (
        f"http://api.openweathermap.org/data/2.5/weather"
        f"?q={config.CIUDAD}&appid={config.OWM_API_KEY}&units=metric&lang=es"
    )
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json(), None
        else:
            msg = _sanitizar_error(f"HTTP {res.status_code}: {res.text[:300]}")
            print(f"[ERROR] - {estado.ts()} OWM devolvió código {res.status_code}")
            return None, msg
    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Conexión OWM: {e}")
        return None, msg


# ==========================================
#   RECOLECCIÓN OPEN-METEO AQI
# ==========================================

def obtener_calidad_aire():
    # type: () -> Tuple[Optional[dict], Optional[str]]
    """
    Consulta la API de calidad del aire de Open-Meteo.
    Retorna (datos_json, None) en éxito o (None, mensaje_error) en fallo.
    """
    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={config.LATITUD}&longitude={config.LONGITUD}"
        f"&current=us_aqi,pm10,pm2_5,uv_index,carbon_monoxide,"
        f"nitrogen_dioxide,sulphur_dioxide,ozone,aerosol_optical_depth"
    )
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json(), None
        else:
            msg = _sanitizar_error(f"HTTP {res.status_code}: {res.text[:300]}")
            print(f"[ERROR] - {estado.ts()} Open-Meteo AQI devolvió código {res.status_code}")
            return None, msg
    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Conexión Open-Meteo AQI: {e}")
        return None, msg


# ==========================================
#   RECOLECCIÓN FASE LUNAR (USNO)
# ==========================================

# Mapa de fases lunares en inglés → español con etiqueta narrativa
_FASES_LUNARES = {
    "New Moon":        ("Luna nueva",         "noche sin luna visible — oscuridad total en cielos despejados"),
    "Waxing Crescent": ("Luna creciente",      "creciente iluminada"),
    "First Quarter":   ("Cuarto creciente",    "mitad de la luna iluminada en fase creciente"),
    "Waxing Gibbous":  ("Gibosa creciente",    "más de la mitad iluminada y aumentando"),
    "Full Moon":       ("Luna llena",          "noche con iluminación lunar máxima"),
    "Waning Gibbous":  ("Gibosa menguante",    "más de la mitad iluminada y disminuyendo"),
    "Last Quarter":    ("Cuarto menguante",    "mitad de la luna iluminada en fase menguante"),
    "Waning Crescent": ("Luna menguante",      "creciente residual — poca luz lunar"),
}


def obtener_fase_lunar():
    # type: () -> Tuple[Optional[dict], Optional[str]]
    """
    Consulta el Observatorio Naval de EE.UU. (USNO) usando las coordenadas de config
    y la fecha del día actual para obtener datos de astronomía lunar.
    No requiere API key.

    Campos extraídos:
        moon_phase         — nombre en inglés (p.ej. "Full Moon")
        moon_illumination  — iluminación (string numérico, p.ej. "100")
        moonrise           — hora de salida de la luna ("HH:MM")
        moonset            — hora de ocaso de la luna ("HH:MM")
        transit_time       — hora de tránsito superior ("HH:MM")
        visible_de_dia     — bool que estima si es visible durante el día
        fase_nombre        — nombre en español
        fase_etiqueta      — descripción narrativa en español

    Retorna (datos_lunar, None) en éxito o (None, mensaje_error) en fallo.
    """
    def _a_minutos(time_str):
        if not time_str or time_str == "N/D":
            return None
        try:
            parts = time_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        except:
            return None

    tz_mexico = datetime.timezone(datetime.timedelta(hours=-6))
    hoy = datetime.datetime.now(tz_mexico).strftime("%Y-%m-%d")
    url = (
        f"https://aa.usno.navy.mil/api/rstt/oneday"
        f"?date={hoy}&coords={config.LATITUD},{config.LONGITUD}&tz=-6"
    )
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            raw = res.json()
            data_sec = raw.get("properties", {}).get("data", {})
            phase_en = data_sec.get("curphase", "")
            illumination = data_sec.get("fracillum", "N/D")
            if illumination.endswith("%"):
                illumination = illumination[:-1]

            # Encontrar tiempos en sundata
            sunrise          = "N/D"
            sunset           = "N/D"
            crepusculo_inicio = "N/D"
            crepusculo_fin    = "N/D"
            mediodia_solar    = "N/D"
            for item in data_sec.get("sundata", []):
                phen = item.get("phen", "")
                if phen == "Rise":
                    sunrise = item.get("time", "N/D")
                elif phen == "Set":
                    sunset = item.get("time", "N/D")
                elif phen == "Begin Civil Twilight":
                    crepusculo_inicio = item.get("time", "N/D")
                elif phen == "End Civil Twilight":
                    crepusculo_fin = item.get("time", "N/D")
                elif phen == "Upper Transit":
                    mediodia_solar = item.get("time", "N/D")

            # Encontrar tiempos de luna
            moondata = data_sec.get("moondata", [])
            moonrise = "N/D"
            moonset = "N/D"
            transit = "N/D"
            for item in moondata:
                phen = item.get("phen", "")
                if phen == "Rise":
                    moonrise = item.get("time", "N/D")
                elif phen == "Set":
                    moonset = item.get("time", "N/D")
                elif phen == "Upper Transit":
                    transit = item.get("time", "N/D")

            # Estimar si es visible de día
            visible_de_dia = False
            try:
                pct = int(illumination)
                if 10 <= pct <= 90 and phase_en not in ["New Moon", "Full Moon"]:
                    sol_rise_min = _a_minutos(sunrise)
                    sol_set_min = _a_minutos(sunset)
                    luna_rise_min = _a_minutos(moonrise)
                    luna_set_min = _a_minutos(moonset)
                    
                    if sol_rise_min and sol_set_min:
                        horas_coincidencia = 0
                        for m in range(sol_rise_min, sol_set_min, 60):
                            luna_arriba = False
                            if luna_rise_min and luna_set_min:
                                if luna_rise_min <= luna_set_min:
                                    luna_arriba = (luna_rise_min <= m <= luna_set_min)
                                else:
                                    luna_arriba = (m >= luna_rise_min or m <= luna_set_min)
                            elif luna_rise_min:
                                luna_arriba = (m >= luna_rise_min)
                            elif luna_set_min:
                                luna_arriba = (m <= luna_set_min)
                            
                            if luna_arriba:
                                horas_coincidencia += 1
                        
                        if horas_coincidencia >= 2:
                            visible_de_dia = True
            except:
                pass

            nombre, etiqueta = _FASES_LUNARES.get(
                phase_en,
                (phase_en or "Fase desconocida", "información no disponible")
            )

            # Fase lunar más cercana (USNO closestphase)
            dia_semana = data_sec.get("day_of_week", "N/D")
            cp = data_sec.get("closestphase", {})
            fase_cercana_ingles = cp.get("phase", "") or ""
            fase_cercana_nombre = (
                _FASES_LUNARES.get(fase_cercana_ingles, (fase_cercana_ingles, ""))[0]
                if fase_cercana_ingles else None
            )
            fase_cercana_hora_str = cp.get("time")
            fase_cercana_fecha    = None
            fase_cercana_dias     = None
            if cp.get("day") and cp.get("month") and cp.get("year"):
                try:
                    import datetime as _dt
                    fecha_fase       = _dt.date(cp["year"], cp["month"], cp["day"])
                    fecha_hoy_local  = datetime.datetime.now(tz_mexico).date()
                    fase_cercana_dias  = (fecha_fase - fecha_hoy_local).days
                    fase_cercana_fecha = fecha_fase.strftime("%Y-%m-%d")
                except Exception:
                    pass

            return {
                "moon_phase":           phase_en,
                "moon_illumination":    illumination,
                "moonrise":             moonrise,
                "moonset":              moonset,
                "transit_time":         transit,
                "visible_de_dia":       visible_de_dia,
                "fase_nombre":          nombre,
                "fase_etiqueta":        etiqueta,
                "crepusculo_inicio":    crepusculo_inicio,
                "crepusculo_fin":       crepusculo_fin,
                "mediodia_solar":       mediodia_solar,
                "dia_semana":           dia_semana,
                "fase_cercana_ingles":  fase_cercana_ingles or None,
                "fase_cercana_nombre":  fase_cercana_nombre,
                "fase_cercana_fecha":   fase_cercana_fecha,
                "fase_cercana_hora":    fase_cercana_hora_str,
                "fase_cercana_dias":    fase_cercana_dias,
            }, None
        else:
            msg = _sanitizar_error(f"HTTP {res.status_code}: {res.text[:200]}")
            print(f"[ERROR] - {estado.ts()} USNO (lunar) devolvió código {res.status_code}")
            return None, msg
    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Conexión USNO (lunar): {e}")
        return None, msg


# ==========================================
#   RECOLECCIÓN OPEN-METEO FORECAST HORARIO
# ==========================================

def obtener_forecast_horario():
    # type: () -> Tuple[Optional[dict], Optional[str]]
    """
    Consulta el endpoint de pronóstico horario de Open-Meteo.
    Solicita precipitation_probability, precipitation, windspeed_10m y cape
    para hoy y mañana en zona horaria local.
    Retorna (datos_json, None) en éxito o (None, mensaje_error) en fallo.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={config.LATITUD}&longitude={config.LONGITUD}"
        f"&hourly=precipitation_probability,precipitation,windspeed_10m,cape"
        f",dewpoint_2m,freezing_level_height"
        f"&forecast_days=2"
        f"&timezone=America%2FMexico_City"
    )
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            return res.json(), None
        else:
            msg = _sanitizar_error(f"HTTP {res.status_code}: {res.text[:300]}")
            print(f"[ERROR] - {estado.ts()} Open-Meteo Forecast devolvió código {res.status_code}")
            return None, msg
    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Conexión Open-Meteo Forecast: {e}")
        return None, msg


# ==========================================
#   TRADUCCIÓN DE DIRECCIÓN DE VIENTO
# ==========================================

_CARDINALES = [
    (  0.0,  22.5, "del norte"),
    ( 22.5,  67.5, "del noreste"),
    ( 67.5, 112.5, "del este"),
    (112.5, 157.5, "del sureste"),
    (157.5, 202.5, "del sur"),
    (202.5, 247.5, "del suroeste"),
    (247.5, 292.5, "del oeste"),
    (292.5, 337.5, "del noroeste"),
    (337.5, 360.0, "del norte"),
]


def _grados_a_cardinal(deg):
    """Convierte wind_deg (0-360) a un texto cardinal en español.
    Retorna None si el valor no es un número válido."""
    if deg is None:
        return None
    try:
        deg = float(deg) % 360
    except (TypeError, ValueError):
        return None
    for lo, hi, label in _CARDINALES:
        if lo <= deg < hi:
            return label
    return "del norte"  # 360 exacto


# ==========================================
#   EXTRACCIÓN DE CAMPOS OWM
# ==========================================

def _etiqueta_weather_id(weather_id):
    """
    Mapea el código numérico weather[0].id de OWM a una etiqueta de alerta.
    Retorna None cuando no hay fenómeno especial que reportar.
    Solo cubre rangos con valor narrativo real para Huichapan.
    """
    if weather_id is None:
        return None
    if 200 <= weather_id <= 232:
        return "tormenta_electrica"
    if weather_id == 511:
        return "lluvia_helada"
    if 600 <= weather_id <= 622:
        return "nieve"
    if weather_id == 701:   # neblina
        return "niebla"
    if weather_id == 741:   # niebla densa
        return "niebla"
    if weather_id == 781:
        return "tornado"
    return None


def _extraer_owm(datos_owm):
    """
    Normaliza los campos relevantes de la respuesta cruda de OWM.
    v16: añade grnd_level, wind_deg, sunrise_ts/sunset_ts (unix) y
         weather_id_etiqueta (etiqueta de alerta de fenómeno severo).
    v17: añade wind_dir_cardinal (punto cardinal en español derivado de wind_deg).
    """
    temp        = datos_owm["main"].get("temp")
    feels       = datos_owm["main"].get("feels_like")
    humedad     = datos_owm["main"].get("humidity")
    desc        = datos_owm["weather"][0]["description"]
    visibilidad = (datos_owm.get("visibility", 10000)) / 1000
    pressure    = datos_owm["main"].get("pressure")
    grnd_level  = datos_owm["main"].get("grnd_level")   # presión al nivel del suelo (hPa)
    weather_id  = datos_owm["weather"][0].get("id")

    # Viento: OWM entrega m/s, se convierte a km/h
    wind_speed_ms   = datos_owm.get("wind", {}).get("speed", 0)
    wind_gust_ms    = datos_owm.get("wind", {}).get("gust")
    wind_deg        = datos_owm.get("wind", {}).get("deg")  # dirección en grados
    wind_speed_kmh  = round(wind_speed_ms * 3.6, 1)
    wind_gust_kmh   = round(wind_gust_ms * 3.6, 1) if wind_gust_ms is not None else None
    wind_dir_cardinal = _grados_a_cardinal(wind_deg)   # punto cardinal en español

    # Nubosidad actual en porcentaje
    clouds_all = datos_owm.get("clouds", {}).get("all")

    lluvia_1h = 0
    if "rain" in datos_owm and "1h" in datos_owm["rain"]:
        lluvia_1h = datos_owm["rain"]["1h"]

    amanecer_str  = "N/D"
    atardecer_str = "N/D"
    sunrise_ts    = None   # unix timestamp para cálculo de modo_nocturno
    sunset_ts     = None
    if "sys" in datos_owm:
        sunrise_ts    = datos_owm["sys"]["sunrise"]
        sunset_ts     = datos_owm["sys"]["sunset"]
        amanecer_str  = datetime.datetime.fromtimestamp(sunrise_ts).strftime("%H:%M")
        atardecer_str = datetime.datetime.fromtimestamp(sunset_ts).strftime("%H:%M")

    return {
        "temp":              temp,
        "feels":             feels,
        "humedad":           humedad,
        "desc":              desc,
        "visibilidad":       visibilidad,
        "lluvia_1h":         lluvia_1h,
        "amanecer":          amanecer_str,
        "atardecer":         atardecer_str,
        "sunrise_ts":        sunrise_ts,
        "sunset_ts":         sunset_ts,
        "pressure":          pressure,
        "grnd_level":        grnd_level,
        "wind_speed_kmh":    wind_speed_kmh,
        "wind_gust_kmh":     wind_gust_kmh,
        "wind_deg":          wind_deg,
        "wind_dir_cardinal": wind_dir_cardinal,
        "clouds_all":        clouds_all,
        "weather_id":        weather_id,
        "weather_id_etiqueta": _etiqueta_weather_id(weather_id),
    }


# ==========================================
#   ETIQUETA INTERPRETATIVA DE PRESIÓN
# ==========================================

def _etiqueta_presion(pressure):
    """
    Convierte el valor de presión en hPa a una etiqueta interpretativa
    que la IA usará para contextualizar las condiciones sin exponer el número.
    """
    if pressure is None:
        return "presión no disponible"
    if pressure < 1000:
        return "presión baja, asociada a inestabilidad atmosférica y mayor probabilidad de lluvia o viento"
    if pressure <= 1015:
        return "presión normal, condiciones atmosféricas sin anomalías significativas"
    return "presión alta, asociada a estabilidad atmosférica y tendencia a cielos despejados"


# ==========================================
#   EXTRACCIÓN DE CAMPOS OPEN-METEO AQI
# ==========================================

def _extraer_aqi(datos_aqi):
    """
    Normaliza los campos de calidad del aire de la respuesta cruda de Open-Meteo.
    Incluye aerosol_optical_depth.
    """
    cur = datos_aqi.get("current", {})
    return {
        "aqi":                   cur.get("us_aqi"),
        "pm10":                  cur.get("pm10"),
        "pm25":                  cur.get("pm2_5"),
        "uv":                    cur.get("uv_index"),
        "co":                    cur.get("carbon_monoxide"),
        "no2":                   cur.get("nitrogen_dioxide"),
        "so2":                   cur.get("sulphur_dioxide"),
        "ozono":                 cur.get("ozone"),
        "aerosol_optical_depth": cur.get("aerosol_optical_depth"),
    }


# ==========================================
#   ETIQUETA INTERPRETATIVA DE AOD
# ==========================================

def _etiqueta_aod(aod):
    """
    Convierte el valor de AOD a una etiqueta de claridad del cielo.
    Retorna None si el valor no supera el umbral narrativo (0.2),
    indicando a prompt.py que debe omitirse.
    """
    if aod is None or aod <= 0.2:
        return None
    if aod <= 0.4:
        return "opacidad atmosférica moderada, con ligera reducción de la nitidez del horizonte"
    if aod <= 0.6:
        return "opacidad atmosférica notable, cielo visualmente velado"
    return "opacidad atmosférica elevada, cielo con carga significativa de partículas finas"


# ==========================================
#   EXTRACCIÓN Y PRE-PROCESAMIENTO DEL FORECAST
# ==========================================

def _etiqueta_helada(freezing_level_m, altitud_estacion_m=None):
    """
    Evalúa si la isoterma de 0°C se aproxima a la altitud de la estación.
    Retorna una etiqueta de alerta o None si no hay riesgo.
    Usa config.ALTITUD_M como referencia; configurable vía el parámetro
    altitud_estacion_m para pruebas o despliegues en otro lugar.
    """
    if altitud_estacion_m is None:
        altitud_estacion_m = config.ALTITUD_M
    if freezing_level_m is None:
        return None
    margen = freezing_level_m - altitud_estacion_m
    if margen <= 0:
        return "helada_severa"        # isoterma por debajo de la estación
    if margen <= 300:
        return "riesgo_helada"        # isoterma a 300 m sobre la estación
    if margen <= 700:
        return "isoterma_cercana"     # watch, sin alerta inmediata
    return None


# Ventana horaria en que el punto de rocío es civil y narrativamente relevante:
# noche, pre-amanecer y primera hora post-amanecer.
_HORAS_ROCIO_RELEVANTE = set(range(20, 24)) | set(range(0, 10))  # 20:00-09:59


def _extraer_forecast(datos_fc, hora_actual):
    """
    A partir de la respuesta cruda del forecast horario, extrae y pre-procesa
    únicamente la ventana de las próximas 6 horas desde hora_actual.

    v16: añade dew_point (°C, promedio de la ventana) y freezing_level_m
         (mínimo de la ventana) con su etiqueta de alerta de helada.

    Retorna un dict con:
        prob_lluvia_max   — probabilidad máxima de lluvia en la ventana (%)
        hora_pico_lluvia  — hora (int, 0-23) en que se produce la prob máxima
        prec_total        — precipitación total proyectada en la ventana (mm)
        viento_actual     — velocidad del viento en la hora actual (km/h)
        viento_max        — velocidad máxima proyectada en la ventana (km/h)
        hora_viento_max   — hora (int, 0-23) del viento máximo
        cape_max          — CAPE máximo en la ventana (J/kg)
        hora_cape_max     — hora (int, 0-23) del CAPE máximo
        cape_etiqueta     — etiqueta interpretativa del CAPE calibrada para el Valle del Mezquital
                            None si cape_max < 500 o si
                            lluvia_relevante es False.
                            Escala usada (ajustada por altitud, fuente NWS/NOAA + SciELO MX):
                              500–1499 J/kg  → convección moderada
                              1500–2499 J/kg → convección fuerte
                              ≥2500 J/kg     → convección severa
        lluvia_relevante  — True si prob_lluvia_max >= 20
        viento_relevante  — True si (viento_max - viento_actual) >= 8 km/h
        cape_relevante    — True si cape_etiqueta no es None (cape_max >= 500 Y lluvia_relevante)
        dew_point         — punto de rocío promedio en la ventana (°C), o None
        freezing_level_m  — isoterma 0°C mínima en la ventana (m), o None
        helada_etiqueta   — etiqueta de alerta de helada, o None
    """
    horario  = datos_fc.get("hourly", {})
    tiempos  = horario.get("time", [])
    probs    = horario.get("precipitation_probability", [])
    precs    = horario.get("precipitation", [])
    vientos  = horario.get("windspeed_10m", [])
    capes    = horario.get("cape", [])
    dewpts   = horario.get("dewpoint_2m", [])
    freezing = horario.get("freezing_level_height", [])

    # Identificar el índice de la hora actual en la serie
    fecha_hoy     = datetime.datetime.now().strftime("%Y-%m-%d")
    hora_str      = "{0}T{1:02d}:00".format(fecha_hoy, hora_actual)
    indice_actual = None
    for i, t in enumerate(tiempos):
        if t == hora_str:
            indice_actual = i
            break

    # Fallback: buscar el primer timestamp del día actual
    if indice_actual is None:
        for i, t in enumerate(tiempos):
            if t.startswith(fecha_hoy):
                indice_actual = i
                break

    if indice_actual is None:
        return _forecast_vacio()

    # Ventana: hora actual + 5 horas siguientes (6 puntos máximo)
    fin = min(indice_actual + 6, len(tiempos))
    ventana_probs    = probs[indice_actual:fin]
    ventana_precs    = precs[indice_actual:fin]
    ventana_vientos  = vientos[indice_actual:fin]
    ventana_capes    = capes[indice_actual:fin]
    ventana_tiempos  = tiempos[indice_actual:fin]
    ventana_dewpts   = dewpts[indice_actual:fin]   if dewpts   else []
    ventana_freezing = freezing[indice_actual:fin] if freezing else []

    if not ventana_probs:
        return _forecast_vacio()

    # --- Lluvia ---
    prob_max     = max(ventana_probs)
    idx_prob_max = ventana_probs.index(prob_max)
    hora_pico    = int(ventana_tiempos[idx_prob_max][11:13])
    prec_total   = round(sum(ventana_precs), 2)

    # --- Viento ---
    viento_actual = round(ventana_vientos[0], 1) if ventana_vientos else 0.0
    viento_max    = round(max(ventana_vientos), 1) if ventana_vientos else 0.0
    idx_viento    = ventana_vientos.index(max(ventana_vientos)) if ventana_vientos else 0
    hora_viento   = int(ventana_tiempos[idx_viento][11:13])

    # --- CAPE ---
    cape_max  = max(ventana_capes) if ventana_capes else 0
    idx_cape  = ventana_capes.index(cape_max) if ventana_capes else 0
    hora_cape = int(ventana_tiempos[idx_cape][11:13])

    lluvia_relevante = prob_max >= 20
    viento_relevante = (viento_max - viento_actual) >= 8

    # ---- Etiqueta CAPE calibrada por altitud (config.ALTITUD_M) ----
    # La escala NWS/NOAA estándar está diseñada para nivel del mar. A la
    # altitud de la estación (config.ALTITUD_M m s.n.m.) la columna de
    # flotabilidad disponible es más corta, por lo que valores que parecen
    # «bajos» en la escala estándar son ya operativamente significativos.
    # Fuentes: NWS/NOAA (weather.gov/lmk/indices), investigación convección
    # Altiplano mexicano (SciELO / Ventusky 300-1000=débil, 1000-2000=moderado).
    # Escala ajustada para config.ALTITUD_M >= ~2000 m:
    #   < 500 J/kg     → inestabilidad débil, no narrativo
    #   500-1499 J/kg  → convección moderada (tormenta posible)
    #   1500-2499 J/kg → convección fuerte (tormenta probable con granizo)
    #   ≥ 2500 J/kg    → convección severa (raro a esta altitud)
    # Sin señal de lluvia, el CAPE no tiene valor narrativo (rev 16.1.0).
    cape_etiqueta = None
    if cape_max >= 500 and lluvia_relevante:
        if cape_max < 1500:
            # Convección moderada: inestabilidad suficiente para chubascos con
            # actividad eléctrica aislada. A 2100 m, 500-1499 J/kg equivale
            # operativamente al rango «débil-moderado» de nivel del mar.
            cape_etiqueta = "convección moderada — posibles chubascos con actividad eléctrica aislada"
        elif cape_max < 2500:
            # Convección fuerte: updrafts capaces de producir granizo y vientos
            # racheados. Equivale a «moderado-fuerte» en escala estándar.
            cape_etiqueta = "convección fuerte — tormentas probables con granizo y vientos racheados"
        else:
            # Convección severa: raro a 2100 m, pero posible con irrupción de
            # humedad tropical. Riesgo de granizo grande o actividad tornádica.
            cape_etiqueta = "convección severa — riesgo de tormentas violentas, granizo intenso o actividad tornádica"

    # CAPE narrativamente relevante: magnitud >= 500 J/kg Y lluvia presentes
    cape_relevante = cape_etiqueta is not None

    # --- Punto de rocío (promedio de la ventana) ---
    dew_point = round(sum(ventana_dewpts) / len(ventana_dewpts), 1) if ventana_dewpts else None

    # --- Relevancia del punto de rocío para locución ---
    # Solo se inyecta al prompt en horario nocturno, pre-amanecer y post-amanecer temprano
    # (entre las 20:00 y las 09:59), que es cuando tiene mayor impacto civil:
    # formación de niebla, escarcha en carreteras y cultivos, bancos de niebla.
    dew_point_relevante = (hora_actual in _HORAS_ROCIO_RELEVANTE) and (dew_point is not None)

    # --- Isoterma de congelación (valor mínimo = más cercano a la superficie) ---
    freezing_level_m = min(ventana_freezing) if ventana_freezing else None
    helada_etiqueta  = _etiqueta_helada(freezing_level_m)

    return {
        "prob_lluvia_max":  prob_max,
        "hora_pico_lluvia": hora_pico,
        "prec_total":       prec_total,
        "viento_actual":    viento_actual,
        "viento_max":       viento_max,
        "hora_viento_max":  hora_viento,
        "cape_max":         cape_max,
        "hora_cape_max":    hora_cape,
        "cape_etiqueta":      cape_etiqueta,
        "lluvia_relevante":   lluvia_relevante,
        "viento_relevante":   viento_relevante,
        "cape_relevante":     cape_relevante,
        "dew_point":          dew_point,
        "dew_point_relevante": dew_point_relevante,
        "freezing_level_m":   freezing_level_m,
        "helada_etiqueta":    helada_etiqueta,
    }


def _forecast_vacio():
    """Retorna un dict de forecast con todos los campos neutros."""
    return {
        "prob_lluvia_max":  0,
        "hora_pico_lluvia": 0,
        "prec_total":       0.0,
        "viento_actual":    0.0,
        "viento_max":       0.0,
        "hora_viento_max":  0,
        "cape_max":         0,
        "hora_cape_max":    0,
        "cape_etiqueta":      None,
        "lluvia_relevante":   False,
        "viento_relevante":   False,
        "cape_relevante":     False,
        "dew_point":          None,
        "dew_point_relevante": False,
        "dew_point_critico":  False,
        "freezing_level_m":   None,
        "helada_etiqueta":    None,
    }


# ==========================================
#   CONSTRUCCIÓN DEL JSON DEL MONITOR WEB
# ==========================================

def construir_datos_web(owm, cna_hoy, aqi, hora_exacta):
    """
    Construye el dict datos_web que se persiste en datos.json para el monitor
    en vivo. Aplica respaldos de CONAGUA cuando OWM no está disponible.
    """
    # Temperatura: OWM preferido; respaldo = promedio tmax/tmin de CONAGUA
    if owm and owm.get("temp") is not None:
        web_temp = owm["temp"]
    elif cna_hoy:
        tmax = cna_hoy.get("temp_max")
        tmin = cna_hoy.get("temp_min")
        if tmax is not None and tmin is not None:
            web_temp = round((tmax + tmin) / 2, 1)
        elif tmax is not None:
            web_temp = tmax
        elif tmin is not None:
            web_temp = tmin
        else:
            web_temp = None
    else:
        web_temp = None

    # Condición: OWM preferido; respaldo = desciel CONAGUA
    if owm and owm.get("desc"):
        web_condicion = str(owm["desc"]).capitalize()
    elif cna_hoy and cna_hoy.get("condicion"):
        web_condicion = str(cna_hoy["condicion"]).capitalize()
    else:
        web_condicion = "N/D"

    # Humedad solo en OWM
    web_humedad = owm["humedad"] if owm else None

    # Viento de CONAGUA
    viento_val = cna_hoy.get("viento") if cna_hoy else None

    # AQI de Open-Meteo
    aqi_val  = aqi.get("aqi")  if aqi else None
    pm25_val = aqi.get("pm25") if aqi else None

    return {
        "temp":               web_temp,
        "condicion":          web_condicion,
        "humedad":            web_humedad,
        "viento":             str(viento_val) if viento_val is not None else "N/D",
        "aqi":                aqi_val  if aqi_val  is not None else "N/D",
        "pm25":               pm25_val if pm25_val is not None else "N/D",
        "hora_actualizacion": hora_exacta,
    }


# ==========================================
#   VOLCADO DEL JSON DEL MONITOR WEB
# ==========================================

def volcar_datos_json(datos_web):
    """Escribe datos_web en el archivo JSON del monitor. Ignora errores de I/O."""
    try:
        with open(config.ARCHIVO_DATOS_WEB, "w", encoding="utf-8") as f:
            json.dump(datos_web, f)
    except Exception as e:
        print(f"[ERROR] - {estado.ts()} No se pudo escribir {config.ARCHIVO_DATOS_WEB}: {e}")


# ==========================================
#   RECOLECCIÓN COMPLETA (punto de entrada)
# ==========================================

def recolectar(conexion_auditoria):
    """
    Orquesta la recolección de OWM, Open-Meteo AQI, Open-Meteo Forecast
    y la fase lunar (USNO).
    Registra en BD los fallos individuales de cada fuente.

    Retorna un dict con:
        owm            — dict extraído de OWM (con pressure_etiqueta), o None
        aqi            — dict extraído de AQI (con aod_etiqueta), o None
        forecast       — dict pre-procesado del forecast horario, o dict vacío
        lunar          — dict de fase lunar (fase_nombre, fase_etiqueta, etc.), o None
        disponible_owm — bool
        disponible_aqi — bool
        disponible_fc  — bool
        disponible_lunar — bool
    """
    hora_actual = datetime.datetime.now().hour

    datos_owm_raw, error_owm   = obtener_clima_owm()
    datos_aqi_raw, error_aqi   = obtener_calidad_aire()
    datos_fc_raw,  error_fc    = obtener_forecast_horario()
    datos_lunar,   error_lunar = obtener_fase_lunar()

    # --- OWM ---
    if datos_owm_raw:
        owm = _extraer_owm(datos_owm_raw)
        owm["pressure_etiqueta"] = _etiqueta_presion(owm.get("pressure"))
        disponible_owm = True
    else:
        owm = None
        disponible_owm = False
        print(f"[SISTEMA] - {estado.ts()} ⚠️  OWM no disponible. Se omitirá del guion actual.")
        bd.registrar_error_bd(conexion_auditoria, "OWM", error_owm or "Sin respuesta.")

    # --- Open-Meteo AQI ---
    if datos_aqi_raw and "current" in datos_aqi_raw:
        aqi = _extraer_aqi(datos_aqi_raw)
        aqi["aod_etiqueta"] = _etiqueta_aod(aqi.get("aerosol_optical_depth"))
        disponible_aqi = True
    else:
        aqi = None
        disponible_aqi = False
        print(f"[SISTEMA] - {estado.ts()} ⚠️  Open-Meteo AQI no disponible. Se omitirá del guion actual.")
        bd.registrar_error_bd(conexion_auditoria, "OPEN_METEO", error_aqi or "Sin respuesta.")

    # --- Open-Meteo Forecast ---
    if datos_fc_raw and "hourly" in datos_fc_raw:
        forecast = _extraer_forecast(datos_fc_raw, hora_actual)
        disponible_fc = True
    else:
        forecast = _forecast_vacio()
        disponible_fc = False
        print(f"[SISTEMA] - {estado.ts()} ⚠️  Open-Meteo Forecast no disponible. Se omitirá del guion actual.")
        bd.registrar_error_bd(conexion_auditoria, "OPEN_METEO_FC", error_fc or "Sin respuesta.")

    # --- Flag de saturación crítica (spread temp − rocío ≤ 2°C) ---
    # Se calcula aquí porque requiere datos de dos fuentes distintas:
    # la temperatura en tiempo real de OWM y el punto de rocío del forecast.
    # Si cualquiera de los dos no está disponible, la flag queda en False.
    dew = forecast.get("dew_point")
    temp_owm = owm.get("temp") if owm else None
    if dew is not None and temp_owm is not None:
        forecast["dew_point_critico"] = (temp_owm - dew) <= 2.0
    else:
        forecast["dew_point_critico"] = False

    # --- Fase lunar (USNO) ---
    if datos_lunar:
        lunar = datos_lunar
        disponible_lunar = True
    else:
        lunar = None
        disponible_lunar = False
        print(f"[SISTEMA] - {estado.ts()} ⚠️  USNO (lunar) no disponible. Se omitirá del guion actual.")
        bd.registrar_error_bd(conexion_auditoria, "USNO_LUNAR", error_lunar or "Sin respuesta.")

    return {
        "owm":             owm,
        "aqi":             aqi,
        "forecast":        forecast,
        "lunar":           lunar,
        "disponible_owm":  disponible_owm,
        "disponible_aqi":  disponible_aqi,
        "disponible_fc":   disponible_fc,
        "disponible_lunar": disponible_lunar,
    }