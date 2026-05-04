# rev 15.1.0
# rev anterior: rev 15.0.0
# Changelog:
#   15.1.0 — Bloque OWM extendido: pressure_etiqueta, wind_speed_kmh, wind_gust_kmh,
#            clouds_all. Bloque AQI extendido: aod_etiqueta. Nueva FUENTE 4:
#            Open-Meteo Forecast horario (lluvia a corto plazo, viento, CAPE).
#            Reglas 10-13 añadidas al final del bloque existente sin modificar
#            las reglas 1-9 originales.
#            Anotaciones de tipo migradas a Optional de typing para
#            compatibilidad con Python 3.9 (Raspberry Pi OS).

import time
from typing import Optional

import config
import estado


# ==========================================
#   BLOQUES DE FUENTES
# ==========================================

def _bloque_conagua(cna):
    """
    Genera el bloque de texto de CONAGUA para el prompt.
    Si los datos no están disponibles, retorna la instrucción de omisión.
    """
    if not cna:
        return (
            "FUENTE 1 (CONAGUA): [NO DISPONIBLE] Ignora esta fuente por completo. "
            "No menciones que CONAGUA falló ni que hay datos faltantes."
        )

    hoy    = cna["hoy"]
    manana = cna.get("manana")

    if manana:
        perspectiva = (
            "Cielo {0} con una máxima de {1}°C "
            "y mínima de {2}°C.".format(
                manana["condicion"], manana["temp_max"], manana["temp_min"]
            )
        )
    else:
        perspectiva = "Sin datos para mañana."

    return (
        "FUENTE 1 (CONAGUA - Pronóstico Oficial PRIORITARIO):\n"
        "- Condición del día: {0} | Temp. Max: {1}°C | Temp. Min: {2}°C\n"
        "- Viento: Dirección {3} a {4} km/h con ráfagas de {5} km/h\n"
        "- Precipitación acumulada del día: {6} mm (Probabilidad oficial de CONAGUA: {7}%)\n"
        "- Breve perspectiva para mañana: {8}"
    ).format(
        hoy["condicion"], hoy["temp_max"], hoy["temp_min"],
        hoy["dir_viento"], hoy["viento"], hoy["rafagas"],
        hoy["precipitacion"], hoy["prob_lluvia"],
        perspectiva
    )


def _bloque_owm(owm):
    """
    Genera el bloque de texto de OpenWeatherMap para el prompt.
    Incluye presión (con etiqueta interpretativa), viento actual, ráfagas y nubosidad.
    Si los datos no están disponibles, retorna la instrucción de omisión.
    """
    if not owm:
        return (
            "FUENTE 2 (OpenWeather): [NO DISPONIBLE] Ignora esta fuente por completo. "
            "No menciones que OpenWeather falló ni que hay datos faltantes."
        )

    # Ráfagas: solo se incluye si el dato existe
    linea_rafagas = (
        " con ráfagas de {0} km/h".format(owm["wind_gust_kmh"])
        if owm.get("wind_gust_kmh") is not None
        else ""
    )

    return (
        "FUENTE 2 (OpenWeather - Tiempo Real):\n"
        "- Temp. actual: {0}°C | Sensación térmica: {1}°C\n"
        "- Humedad: {2}% | Condición: {3}\n"
        "- Nubosidad actual: {4}%\n"
        "- Visibilidad: {5} km | Lluvia registrada en la última hora: {6} mm\n"
        "- Viento actual: {7} km/h{8}\n"
        "- Presión atmosférica: {9}\n"
        "- Hora de amanecer: {10} | Hora de atardecer: {11}"
    ).format(
        owm["temp"], owm["feels"],
        owm["humedad"], owm["desc"],
        owm["clouds_all"],
        owm["visibilidad"], owm["lluvia_1h"],
        owm["wind_speed_kmh"], linea_rafagas,
        owm["pressure_etiqueta"],
        owm["amanecer"], owm["atardecer"]
    )


def _bloque_aqi(aqi):
    """
    Genera el bloque de salud ambiental para el prompt.
    Incluye aerosol_optical_depth con su etiqueta interpretativa cuando aplica.
    Si los datos no están disponibles, retorna un aviso neutral.
    """
    if not aqi:
        return "Datos de calidad del aire y radiación no disponibles."

    # AOD: solo se incluye si la etiqueta no es None
    # (etiqueta es None cuando AOD <= 0.2, no es narrativamente relevante)
    linea_aod = (
        "\n- Opacidad atmosférica: {0}".format(aqi["aod_etiqueta"])
        if aqi.get("aod_etiqueta") is not None
        else ""
    )

    return (
        "- AQI: {0} | PM10: {1} μg/m³ | PM2.5: {2} μg/m³\n"
        "- Índice UV: {3}\n"
        "- Gases: CO: {4} μg/m³ | NO2: {5} μg/m³ | SO2: {6} μg/m³ | Ozono: {7} μg/m³"
        "{8}"
    ).format(
        aqi["aqi"], aqi["pm10"], aqi["pm25"],
        aqi["uv"],
        aqi["co"], aqi["no2"], aqi["so2"], aqi["ozono"],
        linea_aod
    )


def _bloque_forecast(fc):
    """
    Genera el bloque de pronóstico horario a corto plazo para el prompt.
    Solo incluye información cuando los umbrales de relevancia se cumplen:
      - Lluvia: prob_lluvia_max >= 20%
      - Viento: diferencia >= 8 km/h respecto a la hora actual
      - CAPE: >= 300 J/kg Y lluvia relevante simultáneamente
    Si ningún dato supera sus umbrales, retorna la instrucción de omisión total.
    """
    if not fc or (not fc.get("lluvia_relevante") and not fc.get("viento_relevante")):
        return (
            "FUENTE 4 (Open-Meteo Pronóstico a corto plazo): "
            "[SIN EVENTOS RELEVANTES EN LAS PRÓXIMAS HORAS] "
            "No menciones esta fuente ni su ausencia de datos en el reporte."
        )

    lineas = []

    if fc.get("lluvia_relevante"):
        lineas.append(
            "- Probabilidad máxima de lluvia en las próximas 6 horas: {0}% "
            "(pico proyectado alrededor de las {1:02d}:00 horas). "
            "Precipitación total proyectada en la ventana: {2} mm.".format(
                fc["prob_lluvia_max"], fc["hora_pico_lluvia"], fc["prec_total"]
            )
        )

    if fc.get("viento_relevante"):
        lineas.append(
            "- El viento se intensificará en las próximas horas, "
            "alcanzando {0} km/h alrededor de las {1:02d}:00 horas.".format(
                fc["viento_max"], fc["hora_viento_max"]
            )
        )

    if fc.get("cape_relevante"):
        lineas.append(
            "- Energía convectiva disponible (CAPE): {0}. "
            "Pico proyectado alrededor de las {1:02d}:00 horas. "
            "Escala de referencia estándar: Bajo (<300 J/kg), Moderado (300-1000 J/kg), "
            "Alto (1000-2500 J/kg), Muy alto (>2500 J/kg).".format(
                fc["cape_etiqueta"], fc["hora_cape_max"]
            )
        )

    cuerpo = "\n".join(lineas)
    return "FUENTE 4 (Open-Meteo Pronóstico a corto plazo - próximas 6 horas):\n{0}".format(cuerpo)


# ==========================================
#   REGLA DE RESOLUCIÓN DE CONFLICTO DE LLUVIA
# ==========================================

def _regla_lluvia(owm, cna):
    """
    Genera la regla de resolución de conflicto de lluvia según las fuentes disponibles.
    """
    if owm and cna:
        return (
            "2. SOLUCIÓN DE CONFLICTO DE LLUVIA: Si OpenWeather reporta Lluvia en la última hora "
            "({0} mm) mayor a 0, ESTÁ LLOVIENDO AHORA MISMO. Debes informarlo claramente. "
            "Ignora si CONAGUA dice 0% de probabilidad; ese es solo el pronóstico general del día, "
            "pero el estado actual es húmedo o dependiendo de la métrica. Utiliza otro término adecuado "
            "si ambas fuentes marcan 0 lluvia.".format(owm["lluvia_1h"])
        )
    elif owm:
        return (
            "2. LLUVIA ACTUAL: Si OpenWeather reporta lluvia en la última hora ({0} mm) "
            "mayor a 0, está lloviendo en este momento. Infórmalo claramente.".format(owm["lluvia_1h"])
        )
    else:
        return "2. No hay datos de lluvia en tiempo real disponibles en este ciclo."


# ==========================================
#   PUNTO DE ENTRADA PÚBLICO
# ==========================================

def construir_prompt(cna, owm, aqi, forecast=None):
    """
    Ensambla el prompt completo para el modelo de IA a partir de los datos
    recolectados de las cuatro fuentes meteorológicas.

    Parámetros:
        cna      — salida de conagua.obtener_pronostico() o None
        owm      — dict extraído en meteorologo (incluye pressure_etiqueta, viento, etc.) o None
        aqi      — dict extraído en meteorologo (incluye aod_etiqueta) o None
        forecast — dict pre-procesado del forecast horario o None

    Retorna el texto del prompt listo para enviar a Gemini/Groq.
    """
    fecha_exacta = time.strftime("%Y-%m-%d")
    hora_exacta  = time.strftime("%H:%M")

    bloque_cna   = _bloque_conagua(cna)
    bloque_owm   = _bloque_owm(owm)
    bloque_aqi   = _bloque_aqi(aqi)
    bloque_fc    = _bloque_forecast(forecast)
    regla_lluvia = _regla_lluvia(owm, cna)

    prompt = (
        "Eres el sistema automatizado de alerta meteorológica regional. "
        "Escribe un reporte de radio muy detallado para {ciudad} y alrededores. Evita ser redundante en la redacción y personaliza según la hora actual.\n\n"
        "{cna}\n\n"
        "{owm}\n\n"
        "FUENTE 3 (Open-Meteo - Salud Ambiental y Radiación):\n"
        "{aqi}\n\n"
        "{fc}\n\n"
        "REGLAS PARA LA REDACCIÓN (CRÍTICAS):\n"
        "1. Inicia con un saludo formal simple según la hora del día (buenos dias/tardes/noches).\n"
        "{regla_lluvia}\n"
        "3. Menciona la sensación térmica junto a la temperatura actual para darle más valor al reporte. Además Da interpretación del clima actual. \n"
        "4. Menciona la visibilidad solo si crees que es un dato relevante en este momento "
        "(niebla, lluvia, o si es menor a 10km).\n"
        "5. Menciona la hora del amanecer o atardecer si la hora actual de este reporte ({hora}) "
        "está en un rango muy cercano (una hora y media antes o después) al evento. "
        "Si no es relevante en este momento, omítelo por completo para no ser repetitivo. "
        "Además, si está amaneciendo, menciona a que hora será el atardecer hoy y viceversa.\n"
        "6. Dedica un breve párrafo a la calidad del aire basado en la FUENTE 3 dando una "
        "recomendación civil. Usa de referencia la escala de calidad del aire a continuación: "
        "Excelente (0-19), Buena (20-49), Mala (50-99), Poco saludable (100-149), "
        "Muy poco saludable (150-249), Peligrosa (250+). "
        "Menciona a detalle el nivel de partículas PM que proporciona la fuente.\n"
        "7. Tienes acceso a datos de Índice UV y gases en la FUENTE 3. Dedica un breve párrafo "
        "a estos datos. Menciónalos ÚNICAMENTE si representan un riesgo o si son considerados "
        "relevantes. Si los mencionas, hazlo con sus valores y un consejo práctico o recomendación "
        "fácil de entender con una breve explicación. Si estos son bajos o normales (como UV 0 en "
        "la noche, o gases bajos), IGNÓRALOS por completo. Para el caso de índice UV, usa de "
        "referencia la escala a continuación: Bajo (0-2), Moderado (3-5), Alto (6-7), "
        "Muy Alto (8-10), Extremo (11+). Considera la condición climática para hacerlo más preciso.\n"
        "8. Finaliza el reporte ofreciendo la perspectiva de mañana (proporcionada en la Fuente 1). "
        "Al final menciona \"este es un reporte en bucle\".\n"
        "9. NO uses corchetes, ni corchetes angulares, ni marcadores de posición. "
        "Las horas menciónalas como texto para locución "
        "(Ej. \"Veintitrés Horas con Treinta Minutos\"). "
        "Además hay que evitar ser redundantes en toda la redacción.\n"
        "10. Presión atmosférica: NO menciones el valor numérico en hPa. Úsala exclusivamente "
        "como contexto explicativo en una sola oración integrada al párrafo de viento o condiciones "
        "generales. Si la etiqueta de presión de la FUENTE 2 contrasta con la condición actual "
        "(por ejemplo, presión alta pero lluvia activa), señálalo de forma breve e informativa. "
        "Si no hay contraste interesante o la presión es normal sin anomalías, omítela por completo.\n"
        "11. Viento: menciona el viento actual de la FUENTE 2 como el estado en este momento, "
        "incluyendo ráfagas si las hay. Si la FUENTE 4 indica que el viento se intensificará "
        "más de 8 km/h en las próximas horas, añade una oración de tendencia. "
        "Si no hay cambio significativo proyectado, no lo menciones.\n"
        "12. Pronóstico de lluvia a corto plazo (FUENTE 4): inclúyelo ÚNICAMENTE si "
        "lluvia_relevante es True, es decir, si la probabilidad supera el 20% en alguna hora "
        "de la ventana. Si lo incluyes, combínalo con el probprec de CONAGUA para dar una "
        "perspectiva coherente que vaya de lo general (pronóstico del día) a lo específico "
        "(hora a hora). Si la FUENTE 4 indica CAPE relevante junto a la lluvia, menciona que "
        "la precipitación podría presentarse en forma de chubascos cortos e intensos con posible "
        "actividad eléctrica, usando la escala de referencia provista. Nunca menciones el valor "
        "numérico de CAPE ni el término técnico \"CAPE\" en el reporte; "
        "tradúcelo siempre a lenguaje accesible.\n"
        "13. Opacidad atmosférica (FUENTE 3): agrúpala dentro del párrafo de calidad del aire. "
        "Inclúyela ÚNICAMENTE si aod_etiqueta no es None (es decir, AOD > 0.2) Y la hora del "
        "reporte está entre las 06:00 y las 20:00. Descríbela en términos de claridad del cielo "
        "usando la etiqueta proporcionada, nunca como valor numérico ni término técnico. "
        "Si es horario nocturno o el valor es bajo, omítela completamente sin mencionarla.\n\n"
        "Al inicio de la redacción, antes del saludo, coloca exactamente la siguiente "
        "cortinilla institucional:\n"
        "\"Sistema automatizado de monitoreo climatológico preliminar con motivos de estudio; "
        "transmitiendo las 24 horas del día, en la frecuencia de {fm} MegaHertz, con potencia "
        "radiada de {mw} miliwatts. Los datos obtenidos son cortesía del Servicio Meteorológico "
        "Nacional, CONAGUA, en conjunto con OpenWeather y Open-Meteo, procesados mediante "
        "inteligencia artificial generativa.\"\n\n"
        "Menciona que la fecha actual es {fecha} (en formato natural) y que la hora de la "
        "recuperación de los datos es {hora}."
    ).format(
        ciudad=config.CIUDAD,
        cna=bloque_cna,
        owm=bloque_owm,
        aqi=bloque_aqi,
        fc=bloque_fc,
        regla_lluvia=regla_lluvia,
        hora=hora_exacta,
        fm=config.FRECUENCIA_FM,
        mw=config.POTENCIA_MW,
        fecha=fecha_exacta,
    )

    return prompt
