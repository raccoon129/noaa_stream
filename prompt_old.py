# rev 15.1.1
# rev anterior: rev 15.1.0
# Changelog:
#   15.1.1 — Prompt revertido al original de rev 14.9.2 (noaa_estable.py).
#            Se eliminan las reglas 10-13 y los bloques extendidos de OWM/AQI/Forecast
#            añadidos en rev 15.1.0. El texto del prompt es fiel línea a línea
#            al monolito original. Los datos adicionales (pressure, viento OWM,
#            clouds, forecast, AOD) siguen siendo recolectados por meteorologo.py
#            pero no se incluyen en este prompt.
#   15.1.0 — Bloque OWM extendido, FUENTE 4 Forecast, reglas 10-13.
#   15.0.0 — Módulo nuevo. Centraliza la construcción del prompt.

import time

import config
import estado


# ==========================================
#   BLOQUES DE FUENTES
# ==========================================

def _bloque_conagua(cna):
    """
    Genera el bloque FUENTE 1 (CONAGUA) para el prompt.
    Fiel al original de rev 14.9.2.
    """
    if not cna:
        return (
            "FUENTE 1 (CONAGUA): [NO DISPONIBLE] Ignora esta fuente por completo. "
            "No menciones que CONAGUA falló ni que hay datos faltantes."
        )

    hoy    = cna["hoy"]
    manana = cna.get("manana")

    perspectiva_manana = (
        "Cielo {0} con una máxima de {1}°C y mínima de {2}°C.".format(
            manana["condicion"], manana["temp_max"], manana["temp_min"]
        )
        if manana else "Sin datos para mañana."
    )

    return (
        "\n"
        "            FUENTE 1 (CONAGUA - Pronóstico Oficial PRIORITARIO):\n"
        "            - Condición del día: {0} | Temp. Max: {1}°C | Temp. Min: {2}°C\n"
        "            - Viento: Dirección {3} a {4} km/h con ráfagas de {5} km/h\n"
        "            - Precipitación acumulada del día: {6} mm "
        "(Probabilidad oficial de CONAGUA: {7}%)\n"
        "            - Breve perspectiva para mañana: {8}\n"
        "                "
    ).format(
        hoy["condicion"], hoy["temp_max"], hoy["temp_min"],
        hoy["dir_viento"], hoy["viento"], hoy["rafagas"],
        hoy["precipitacion"], hoy["prob_lluvia"],
        perspectiva_manana
    )


def _bloque_owm(owm):
    """
    Genera el bloque FUENTE 2 (OpenWeather) para el prompt.
    Fiel al original de rev 14.9.2: solo temp, feels, humedad, desc,
    visibilidad, lluvia_1h, amanecer y atardecer.
    """
    if not owm:
        return (
            "\n"
            "            FUENTE 2 (OpenWeather): [NO DISPONIBLE] Ignora esta fuente "
            "por completo. No menciones que OpenWeather falló ni que hay datos faltantes.\n"
            "                "
        )

    return (
        "\n"
        "            FUENTE 2 (OpenWeather - Tiempo Real):\n"
        "            - Temp. actual: {0}°C | Sensación térmica: {1}°C\n"
        "            - Humedad: {2}% | Condición: {3}\n"
        "            - Visibilidad: {4} km | Lluvia registrada en la última hora: {5} mm\n"
        "            - Hora de amanecer: {6} | Hora de atardecer: {7}\n"
        "                "
    ).format(
        owm["temp"], owm["feels"],
        owm["humedad"], owm["desc"],
        owm["visibilidad"], owm["lluvia_1h"],
        owm["amanecer"], owm["atardecer"]
    )


def _bloque_aqi(aqi):
    """
    Genera el bloque FUENTE 3 (Open-Meteo) para el prompt.
    Fiel al original de rev 14.9.2: solo AQI, PM10, PM2.5, UV y gases.
    """
    if not aqi:
        return "Datos de calidad del aire y radiación no disponibles."

    return (
        "\n"
        "                - AQI: {0} | PM10: {1} μg/m³ | PM2.5: {2} μg/m³\n"
        "                - Índice UV: {3}\n"
        "                - Gases: CO: {4} μg/m³ | NO2: {5} μg/m³ | "
        "SO2: {6} μg/m³ | Ozono: {7} μg/m³\n"
        "                "
    ).format(
        aqi["aqi"], aqi["pm10"], aqi["pm25"],
        aqi["uv"],
        aqi["co"], aqi["no2"], aqi["so2"], aqi["ozono"]
    )


# ==========================================
#   REGLA DE RESOLUCIÓN DE CONFLICTO DE LLUVIA
# ==========================================

def _regla_lluvia(owm, cna):
    """
    Genera la regla 2 de resolución de conflicto de lluvia.
    Fiel al original de rev 14.9.2.
    """
    if owm and cna:
        return (
            "2. SOLUCIÓN DE CONFLICTO DE LLUVIA: Si OpenWeather reporta Lluvia en la última hora "
            "({0} mm) mayor a 0, ESTÁ LLOVIENDO AHORA MISMO. Debes informarlo claramente. "
            "Ignora si CONAGUA dice 0% de probabilidad; ese es solo el pronóstico general del día, "
            "pero el estado actual es húmedo o dependiendo de la métrica. Utiliza otro término adecuado "
            "si ambas fuentes marcan 0 lluvia."
        ).format(owm["lluvia_1h"])
    elif owm:
        return (
            "2. LLUVIA ACTUAL: Si OpenWeather reporta lluvia en la última hora ({0} mm) "
            "mayor a 0, está lloviendo en este momento. Infórmalo claramente."
        ).format(owm["lluvia_1h"])
    else:
        return "2. No hay datos de lluvia en tiempo real disponibles en este ciclo."


# ==========================================
#   PUNTO DE ENTRADA PÚBLICO
# ==========================================

def construir_prompt(cna, owm, aqi, forecast=None):
    """
    Ensambla el prompt para el modelo de IA.
    Fiel línea a línea al prompt original de rev 14.9.2 (noaa_estable.py).

    El parámetro forecast se acepta por compatibilidad con la firma de
    noaa_str.py pero no se usa en este prompt.

    Parámetros:
        cna      — salida de conagua.obtener_pronostico() o None
        owm      — dict extraído en meteorologo o None
        aqi      — dict extraído en meteorologo o None
        forecast — ignorado en esta versión del prompt
    """
    fecha_exacta = time.strftime("%Y-%m-%d")
    hora_exacta  = time.strftime("%H:%M")

    bloque_cna   = _bloque_conagua(cna)
    bloque_owm   = _bloque_owm(owm)
    bloque_aqi   = _bloque_aqi(aqi)
    nota_lluvia  = _regla_lluvia(owm, cna)

    prompt = (
        "\n"
        "            Eres el sistema automatizado de alerta meteorológica regional. "
        "Escribe un reporte de radio muy detallado para {ciudad} y alrededores.\n"
        "\n"
        "            {cna}\n"
        "\n"
        "            {owm}\n"
        "\n"
        "            FUENTE 3 (Open-Meteo - Salud Ambiental y Radiación):\n"
        "            {aqi}\n"
        "\n"
        "            REGLAS PARA LA REDACCIÓN (CRÍTICAS):\n"
        "            1. Inicia con un saludo formal simple según la hora del día "
        "(buenos dias/tardes/noches).\n"
        "            {nota_lluvia}\n"
        "            3. Menciona la sensación térmica junto a la temperatura actual "
        "para darle más valor al reporte.\n"
        "            4. Menciona la visibilidad solo si crees que es un dato relevante "
        "en este momento (niebla, lluvia, o si es menor a 10km).\n"
        "            5. Menciona la hora del amanecer o atardecer si la hora actual de "
        "este reporte ({hora}) está en un rango muy cercano (una hora y media antes o "
        "después) al evento. Si no es relevante en este momento, omítelo por completo "
        "para no ser repetitivo. Además, si está amaneciendo, menciona a que hora será "
        "el atardecer hoy y viceversa. \n"
        "            6. Dedica un breve párrafo a la calidad del aire basado en la "
        "FUENTE 3 dando una recomendación civil. Usa de referencia la escala de calidad "
        "del aire a continuación: Excelente (0-19), Buena (20-49), Mala (50-99), "
        "Poco saludable (100-149), Muy poco saludable (150-249), Peligrosa (250+). "
        "Menciona a detalle el nivel de partículas PM que proporciona la fuente.\n"
        "            7. Tienes acceso a datos de Índice UV y gases en la FUENTE 3. "
        "Dedica un breve párrafo a estos datos. Menciónalos ÚNICAMENTE si representan "
        "un riesgo o si son considerados relevantes. Si los mencionas, hazlo con sus "
        "valores y un consejo práctico o recomendación fácil de entender con una breve "
        "explicación. Si estos son bajos o normales (como UV 0 en la noche, o gases "
        "bajos), IGNÓRALOS por completo. Para el caso de índice UV, usa de referencia "
        "la escala a continuación: Bajo (0-2), Moderado (3-5), Alto (6-7), "
        "Muy Alto (8-10), Extremo (11+). Considera la condición climática para "
        "hacerlo más preciso.\n"
        "            8. Finaliza el reporte ofreciendo la perspectiva de mañana "
        "(proporcionada en la Fuente 1). Al final menciona \"este es un reporte en bucle\".\n"
        "            9. NO uses corchetes, ni corchetes angulares, ni marcadores de "
        "posición. Las horas menciónalas como texto para locución "
        "(Ej. \"Veintitrés Horas con Treinta Minutos\"). "
        "Además hay que evitar ser redundantes en toda la redacción.\n"
        "\n"
        "            Al inicio de la redacción, antes del saludo, coloca exactamente "
        "la siguiente cortinilla institucional:\n"
        "            \"Sistema automatizado de monitoreo climatológico preliminar con "
        "motivos de estudio; transmitiendo las 24 horas del día, en la frecuencia de "
        "{fm} MegaHertz, con potencia radiada de {mw} miliwatts. Los datos obtenidos "
        "son cortesía del Servicio Meteorológico Nacional, CONAGUA, en conjunto con "
        "OpenWeather y Open-Meteo, procesados mediante inteligencia artificial "
        "generativa.\"\n"
        "\n"
        "            Menciona que la fecha actual es {fecha} (en formato natural) "
        "y que la hora de la recuperación de los datos es {hora}.\n"
        "            "
    ).format(
        ciudad=config.CIUDAD,
        cna=bloque_cna,
        owm=bloque_owm,
        aqi=bloque_aqi,
        nota_lluvia=nota_lluvia,
        hora=hora_exacta,
        fm=config.FRECUENCIA_FM,
        mw=config.POTENCIA_MW,
        fecha=fecha_exacta,
    )

    return prompt