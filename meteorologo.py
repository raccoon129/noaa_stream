# rev 15.1.0
# rev anterior: rev 15.0.0
# Changelog:
#   15.1.0 — Nuevos campos OWM: pressure, wind_speed_kmh, wind_gust_kmh, clouds_all,
#            weather_id. AQI extendido: aerosol_optical_depth. Nueva fuente:
#            Open-Meteo Forecast horario (precipitation_probability, precipitation,
#            windspeed_10m, cape). Pre-procesamiento completo del forecast en Python
#            antes de llegar al prompt: solo se extraen valores relevantes de la
#            ventana de las próximas 6 horas desde la hora actual.
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
#   EXTRACCIÓN DE CAMPOS OWM
# ==========================================

def _extraer_owm(datos_owm):
    """
    Normaliza los campos relevantes de la respuesta cruda de OWM
    en un dict de tipos nativos.
    Incluye: pressure, wind_speed_kmh, wind_gust_kmh, clouds_all, weather_id.
    """
    temp        = datos_owm["main"].get("temp")
    feels       = datos_owm["main"].get("feels_like")
    humedad     = datos_owm["main"].get("humidity")
    desc        = datos_owm["weather"][0]["description"]
    visibilidad = (datos_owm.get("visibility", 10000)) / 1000
    pressure    = datos_owm["main"].get("pressure")
    weather_id  = datos_owm["weather"][0].get("id")

    # Viento: OWM entrega m/s, se convierte a km/h
    wind_speed_ms  = datos_owm.get("wind", {}).get("speed", 0)
    wind_gust_ms   = datos_owm.get("wind", {}).get("gust")
    wind_speed_kmh = round(wind_speed_ms * 3.6, 1)
    wind_gust_kmh  = round(wind_gust_ms * 3.6, 1) if wind_gust_ms is not None else None

    # Nubosidad actual en porcentaje
    clouds_all = datos_owm.get("clouds", {}).get("all")

    lluvia_1h = 0
    if "rain" in datos_owm and "1h" in datos_owm["rain"]:
        lluvia_1h = datos_owm["rain"]["1h"]

    amanecer_str  = "N/D"
    atardecer_str = "N/D"
    if "sys" in datos_owm:
        amanecer_str  = datetime.datetime.fromtimestamp(datos_owm["sys"]["sunrise"]).strftime("%H:%M")
        atardecer_str = datetime.datetime.fromtimestamp(datos_owm["sys"]["sunset"]).strftime("%H:%M")

    return {
        "temp":           temp,
        "feels":          feels,
        "humedad":        humedad,
        "desc":           desc,
        "visibilidad":    visibilidad,
        "lluvia_1h":      lluvia_1h,
        "amanecer":       amanecer_str,
        "atardecer":      atardecer_str,
        "pressure":       pressure,
        "wind_speed_kmh": wind_speed_kmh,
        "wind_gust_kmh":  wind_gust_kmh,
        "clouds_all":     clouds_all,
        "weather_id":     weather_id,
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

def _extraer_forecast(datos_fc, hora_actual):
    """
    A partir de la respuesta cruda del forecast horario, extrae y pre-procesa
    únicamente la ventana de las próximas 6 horas desde hora_actual.

    Retorna un dict con:
        prob_lluvia_max   — probabilidad máxima de lluvia en la ventana (%)
        hora_pico_lluvia  — hora (int, 0-23) en que se produce la prob máxima
        prec_total        — precipitación total proyectada en la ventana (mm)
        viento_actual     — velocidad del viento en la hora actual (km/h)
        viento_max        — velocidad máxima proyectada en la ventana (km/h)
        hora_viento_max   — hora (int, 0-23) del viento máximo
        cape_max          — CAPE máximo en la ventana (J/kg)
        hora_cape_max     — hora (int, 0-23) del CAPE máximo
        cape_etiqueta     — etiqueta interpretativa del CAPE, o None si < 300
        lluvia_relevante  — True si prob_lluvia_max >= 20
        viento_relevante  — True si (viento_max - viento_actual) >= 8 km/h
        cape_relevante    — True si cape_max >= 300 Y lluvia_relevante es True
    """
    horario = datos_fc.get("hourly", {})
    tiempos = horario.get("time", [])
    probs   = horario.get("precipitation_probability", [])
    precs   = horario.get("precipitation", [])
    vientos = horario.get("windspeed_10m", [])
    capes   = horario.get("cape", [])

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
    ventana_probs   = probs[indice_actual:fin]
    ventana_precs   = precs[indice_actual:fin]
    ventana_vientos = vientos[indice_actual:fin]
    ventana_capes   = capes[indice_actual:fin]
    ventana_tiempos = tiempos[indice_actual:fin]

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

    # Etiqueta CAPE según escala estándar
    cape_etiqueta = None
    if cape_max >= 300:
        if cape_max < 1000:
            cape_etiqueta = "rango moderado (300-1000 J/kg): tormentas débiles posibles"
        elif cape_max < 2500:
            cape_etiqueta = "rango alto (1000-2500 J/kg): tormentas fuertes probables"
        else:
            cape_etiqueta = "rango muy alto (>2500 J/kg): tormentas severas"

    lluvia_relevante = prob_max >= 20
    viento_relevante = (viento_max - viento_actual) >= 8
    # CAPE solo es narrativamente relevante cuando también hay señal de lluvia
    cape_relevante   = cape_max >= 300 and lluvia_relevante

    return {
        "prob_lluvia_max":  prob_max,
        "hora_pico_lluvia": hora_pico,
        "prec_total":       prec_total,
        "viento_actual":    viento_actual,
        "viento_max":       viento_max,
        "hora_viento_max":  hora_viento,
        "cape_max":         cape_max,
        "hora_cape_max":    hora_cape,
        "cape_etiqueta":    cape_etiqueta,
        "lluvia_relevante": lluvia_relevante,
        "viento_relevante": viento_relevante,
        "cape_relevante":   cape_relevante,
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
        "cape_etiqueta":    None,
        "lluvia_relevante": False,
        "viento_relevante": False,
        "cape_relevante":   False,
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
    Orquesta la recolección de OWM, Open-Meteo AQI y Open-Meteo Forecast.
    Registra en BD los fallos individuales de cada fuente.

    Retorna un dict con:
        owm            — dict extraído de OWM (con pressure_etiqueta), o None
        aqi            — dict extraído de AQI (con aod_etiqueta), o None
        forecast       — dict pre-procesado del forecast horario, o dict vacío
        disponible_owm — bool
        disponible_aqi — bool
        disponible_fc  — bool
    """
    hora_actual = datetime.datetime.now().hour

    datos_owm_raw, error_owm = obtener_clima_owm()
    datos_aqi_raw, error_aqi = obtener_calidad_aire()
    datos_fc_raw,  error_fc  = obtener_forecast_horario()

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

    return {
        "owm":            owm,
        "aqi":            aqi,
        "forecast":       forecast,
        "disponible_owm": disponible_owm,
        "disponible_aqi": disponible_aqi,
        "disponible_fc":  disponible_fc,
    }
