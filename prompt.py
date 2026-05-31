# rev 16.5.0
# rev anterior: rev 16.4.0
# Changelog:
#   16.5.0 — _bloque_owm(): presión fusionada en una sola línea con formato
#            "X hPa | etiqueta" (antes eran dos líneas separadas). 
#            _bloque_aqi(): AOD fusionado en una sola línea con formato
#            "X.XXX | etiqueta" cuando ambos valores están disponibles.
#            Reglas 10 y 13 ajustadas para reflejar el nuevo formato.
#   16.4.0 — _bloque_owm(): expone pressure en hPa como 'Presión (valor de referencia
#            técnica)'. _bloque_forecast(): expone cape_max en J/kg e isoterma 0°C
#            en m s.n.m. como campos de referencia técnica, incluidos en ambas ramas
#            (eventos relevantes y sin eventos). Reglas 10, 12 y 15 actualizadas:
#            el modelo puede usar esos valores para calibrar la narrativa pero nunca
#            los menciona literalmente; los traduce a lenguaje accesible.
#   16.3.0 — _bloque_aqi(): se expone el valor numérico de AOD como campo de
#            referencia técnica ("AOD (valor de referencia técnica)") adyacente a
#            la etiqueta interpretativa. Regla 13 actualizada: el modelo puede usar
#            ese valor para enriquecer su explicación (p. ej. distinguir AOD cercano
#            al umbral de uno marcadamente elevado), pero sigue sin mencionarlo
#            literalmente; debe traducirlo siempre a lenguaje accesible.
#   16.2.0 — _bloque_conagua(): línea de precipitación de HOY suprime prec cuando
#            prob_lluvia=0 (prec sin probabilidad no tiene valor narrativo según
#            documentación del endpoint method=1). Mismo criterio aplicado al bloque
#            de mañana en modo_nocturno. Cabecera de FUENTE 1 aclara "datos del día
#            completo". Regla 12 reescrita: elimina referencia a variable interna
#            lluvia_relevante; añade aclaración de ventanas temporales distintas
#            (CONAGUA=día completo, FUENTE 4=próximas 6h) y jerarquía de precedencia
#            cuando ambas fuentes difieren.
#   16.1.0 — Se retira cna_hora y rocio_relevante: el endpoint method=3 de
#            CONAGUA es demasiado pesado para el hardware. Se elimina
#            _bloque_conagua_horario() del prompt, se retira la regla 14
#            (punto de rocío) y se ajusta la firma de construir_prompt().
#            modo_nocturno se conserva (depende de OWM, no de method=3).
#   16.0.0 — FUENTE 5 (CONAGUA method=3), weather_id alerts, modo_nocturno.
#   15.1.0 — Bloque OWM extendido.

import time
from typing import Optional

import config
import estado


# ==========================================
#   BLOQUES DE FUENTES
# ==========================================

def _bloque_conagua(cna, modo_nocturno=False):
    """
    Genera el bloque de texto de CONAGUA para el prompt.
    modo_nocturno=True: la perspectiva de mañana se expande a un bloque completo.
    """
    if not cna:
        return (
            "FUENTE 1 (CONAGUA): [NO DISPONIBLE] Ignora esta fuente por completo. "
            "No menciones que CONAGUA falló ni que hay datos faltantes."
        )

    hoy    = cna["hoy"]
    manana = cna.get("manana")

    # Línea de precipitación de HOY:
    # probprec y prec son acumulados del día completo (no del momento de consulta).
    # Si probprec=0, prec no tiene valor narrativo (es la cantidad condicional si
    # lloviera, pero la probabilidad es nula). Se suprime para evitar confusión.
    if (hoy.get("prob_lluvia") or 0) > 0:
        linea_prec_hoy = (
            "- Probabilidad de precipitación para el día: {0}% "
            "— Acumulado proyectado: {1} mm".format(
                hoy["prob_lluvia"], hoy["precipitacion"]
            )
        )
    else:
        linea_prec_hoy = "- Sin precipitación proyectada para el día (probabilidad: 0%)"

    # Perspectiva de mañana en modo nocturno:
    # Mismo criterio para prec — se suprime cuando prob_lluvia=0.
    if manana and modo_nocturno:
        man_prob   = manana.get("prob_lluvia", 0) or 0
        if man_prob > 0:
            linea_prec_man = (
                "  Probabilidad de lluvia: {0}% — Precipitación proyectada: {1} mm\n".format(
                    man_prob, manana.get("precipitacion", 0)
                )
            )
        else:
            linea_prec_man = "  Sin precipitación proyectada (probabilidad: 0%)\n"

        perspectiva = (
            "PRONÓSTICO COMPLETO PARA MAÑANA (MODO NOCTURNO — EXPANDE ESTE BLOQUE):\n"
            "  Condición: {0} | Temp. Máx: {1}°C | Temp. Mín: {2}°C\n"
            "  Viento: {3} a {4} km/h con ráfagas de {5} km/h\n"
            "{6}"
            "  Instrucción: Dedica un párrafo completo a la perspectiva de mañana, "
            "comparable en detalle al reporte de hoy. "
        ).format(
            manana["condicion"], manana["temp_max"], manana["temp_min"],
            manana.get("dir_viento", "variable"), manana.get("viento", "N/D"),
            manana.get("rafagas", "N/D"),
            linea_prec_man,
        )
    elif manana:
        perspectiva = (
            "Cielo {0} con una máxima de {1}°C y mínima de {2}°C.".format(
                manana["condicion"], manana["temp_max"], manana["temp_min"]
            )
        )
    else:
        perspectiva = "Sin datos para mañana."

    return (
        "FUENTE 1 (CONAGUA/Comisión Nacional del Agua - Pronóstico Oficial PRIORITARIO — datos del día completo):\n"
        "- Condición del día: {0} | Temp. Max: {1}°C | Temp. Min: {2}°C\n"
        "- Viento: Dirección {3} a {4} km/h con ráfagas de {5} km/h\n"
        "{6}\n"
        "- Perspectiva para mañana: {7}"
    ).format(
        hoy["condicion"], hoy["temp_max"], hoy["temp_min"],
        hoy["dir_viento"], hoy["viento"], hoy["rafagas"],
        linea_prec_hoy,
        perspectiva
    )


def _bloque_owm(owm):
    """
    Genera el bloque de texto de OpenWeatherMap para el prompt.
    v16: incluye weather_id_etiqueta como línea de alerta al inicio cuando aplica.
    """
    if not owm:
        return (
            "FUENTE 2 (OpenWeather): [NO DISPONIBLE] Ignora esta fuente por completo. "
            "No menciones que OpenWeather falló ni que hay datos faltantes."
        )

    # Alerta de fenómeno severo: solo si weather_id_etiqueta no es None
    _ALERTAS = {
        "tormenta_electrica": "ALERTA: Se detecta tormenta eléctrica activa sobre la zona.",
        "lluvia_helada":      "ALERTA: Lluvia helada detectada. Riesgo de hielo en carreteras.",
        "nieve":              "ALERTA: Precipitación invernal (nieve/aguanieve) detectada.",
        "niebla":             "AVISO: Neblina o niebla presente. Visibilidad reducida.",
        "tornado":            "ALERTA MÁXIMA: Se detecta actividad de tornado en la región.",
    }
    etiqueta = owm.get("weather_id_etiqueta")
    linea_alerta = (
        "- {0}\n".format(_ALERTAS[etiqueta])
        if etiqueta and etiqueta in _ALERTAS
        else ""
    )

    linea_rafagas = (
        " con ráfagas de {0} km/h".format(owm["wind_gust_kmh"])
        if owm.get("wind_gust_kmh") is not None
        else ""
    )

    # Línea de presión: "1012 hPa | etiqueta" si hay valor numérico, solo etiqueta si no.
    if owm.get("pressure") is not None:
        linea_presion = "- Presión atmosférica: {0} hPa | {1}".format(
            owm["pressure"], owm["pressure_etiqueta"]
        )
    else:
        linea_presion = "- Presión atmosférica: {0}".format(owm["pressure_etiqueta"])

    return (
        "FUENTE 2 (OpenWeather - Tiempo Real):\n"
        "{alerta}"
        "- Temp. actual: {0}°C | Sensación térmica: {1}°C\n"
        "- Humedad: {2}% | Condición: {3}\n"
        "- Nubosidad actual: {4}%\n"
        "- Visibilidad: {5} km | Lluvia registrada en la última hora: {6} mm\n"
        "- Viento actual: {7} km/h{8}\n"
        "{presion}\n"
        "- Hora de amanecer: {9} | Hora de atardecer: {10}"
    ).format(
        owm["temp"], owm["feels"],
        owm["humedad"], owm["desc"],
        owm["clouds_all"],
        owm["visibilidad"], owm["lluvia_1h"],
        owm["wind_speed_kmh"], linea_rafagas,
        owm["amanecer"], owm["atardecer"],
        alerta=linea_alerta,
        presion=linea_presion,
    )


def _bloque_aqi(aqi):
    """
    Genera el bloque de salud ambiental para el prompt.
    Incluye aerosol_optical_depth con su etiqueta interpretativa cuando aplica.
    Si los datos no están disponibles, retorna un aviso neutral.
    """
    if not aqi:
        return "Datos de calidad del aire y radiación no disponibles."

    # AOD: línea combinada "valor | etiqueta" cuando hay etiqueta (AOD > 0.2).
    # Si hay valor pero no etiqueta, se expone solo el valor técnico.
    # Si no hay dato, línea vacía.
    aod_valor = aqi.get("aerosol_optical_depth")
    aod_etiqueta = aqi.get("aod_etiqueta")
    if aod_etiqueta is not None and aod_valor is not None:
        linea_aod = "\n- Opacidad atmosférica: {0:.3f} | {1}".format(aod_valor, aod_etiqueta)
    elif aod_etiqueta is not None:
        linea_aod = "\n- Opacidad atmosférica: {0}".format(aod_etiqueta)
    elif aod_valor is not None:
        linea_aod = "\n- AOD (valor técnico): {0:.3f}".format(aod_valor)
    else:
        linea_aod = ""

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
    Genera el bloque de pronóstico horario a corto plazo.
    v16: añade líneas de helada y punto de rocío cuando son relevantes.
    """
    # Valores de referencia técnica (siempre incluidos cuando hay datos)
    refs = []
    if fc:
        if fc.get("cape_max"):
            refs.append(
                "- CAPE (valor técnico): {0} J/kg".format(fc["cape_max"])
            )
        if fc.get("freezing_level_m") is not None:
            refs.append(
                "- Isoterma (valor técnico): {0:.0f} m s.n.m.".format(
                    fc["freezing_level_m"]
                )
            )
    refs_str = ("\n" + "\n".join(refs)) if refs else ""

    if not fc or (not fc.get("lluvia_relevante") and not fc.get("viento_relevante")
                  and not fc.get("helada_etiqueta")):
        return (
            "FUENTE 4 (Open-Meteo Pronóstico a corto plazo): "
            "[SIN EVENTOS RELEVANTES EN LAS PRÓXIMAS HORAS] "
            "No menciones esta fuente ni su ausencia de datos en el reporte."
            + refs_str
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
            "Escala para la altitud (~{2} m s.n.m.): "
            "Bajo (<500 J/kg), Moderado (500-1499 J/kg), "
            "Fuerte (1500-2499 J/kg), Severo (\u22652500 J/kg).".format(
                fc["cape_etiqueta"], fc["hora_cape_max"], config.ALTITUD_M
            )
        )

    _HELADA_MSG = {
        "helada_severa":   "ALERTA DE HELADA SEVERA: La isoterma de 0°C ha descendido por debajo de la altitud de la localidad. Riesgo crítico de hielo en superficies, cultivos y vías.",
        "riesgo_helada":   "RIESGO DE HELADA: La isoterma de 0°C está muy próxima a la altitud de Huichapan. Posible formación de escarcha en zonas altas y cultivos.",
        "isoterma_cercana": "WATCH DE HELADA: La temperatura de congelación se aproxima. Monitorear condiciones en zonas elevadas.",
    }
    helada = fc.get("helada_etiqueta")
    if helada and helada in _HELADA_MSG:
        lineas.append("- {0}".format(_HELADA_MSG[helada]))

    cuerpo = "\n".join(lineas)
    return "FUENTE 4 (Open-Meteo Pronóstico a corto plazo - próximas 6 horas):\n{0}{1}".format(cuerpo, refs_str)



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
#   BLOQUE SÍSMICO (INYECTADO)
# ==========================================

def _bloque_sismo(contexto_sismo: Optional[dict]) -> str:
    """
    Genera el bloque de contexto sísmico para inyectarlo en el reporte del clima.
    Incluye datos enriquecidos de USGS/EMSC/IRIS si están disponibles.
    """
    if not contexto_sismo:
        return ""

    magnitud = contexto_sismo.get("ssn_magnitud")
    epicentro = contexto_sismo.get("epicentro", "territorio mexicano")

    if magnitud:
        mag_str = f"magnitud preliminar {magnitud}"
    else:
        mag_str = "intensidad detectada"

    # Datos enriquecidos de APIs internacionales
    extras = []
    if contexto_sismo.get("usgs_magnitud"):
        extras.append(f"USGS reporta magnitud {contexto_sismo['usgs_magnitud']}")
    if contexto_sismo.get("emsc_magnitud"):
        extras.append(f"EMSC reporta magnitud {contexto_sismo['emsc_magnitud']}")
    if contexto_sismo.get("usgs_tsunami") == 1:
        extras.append("USGS ha emitido alerta de tsunami")
    if contexto_sismo.get("replicas_detectadas"):
        extras.append(f"Se han detectado {contexto_sismo['replicas_detectadas']} réplicas")

    extras_str = ""
    if extras:
        extras_str = (
            "\nDatos internacionales disponibles: " + ". ".join(extras) + ".\n"
            "Incluye estos datos en tu mención del sismo de forma natural y accesible.\n"
        )

    return (
        f"CONTEXTO SÍSMICO RECIENTE (CRÍTICO - INYECTAR AL INICIO DEL REPORTE, DESPUÉS DE LA HORA Y FECHA):\n"
        f"Ha ocurrido un sismo recientemente de {mag_str} con epicentro en {epicentro}.\n"
        f"{extras_str}"
        "Regla especial: Inicia tu reporte meteorológico informando brevemente sobre este evento. "
        "Usa una frase como: 'Antes de iniciar con las condiciones meteorológicas, informamos que un sismo de "
        f"{mag_str} fue registrado recientemente con epicentro en {epicentro}...'. "
        "Añade que 'El reporte detallado con información de agencias sismológicas internacionales "
        "estará disponible en la próxima actualización de esta frecuencia'. "
        "Tras esta breve mención, continúa fluidamente con el reporte del clima habitual.\n"
    )


# ==========================================
#   PUNTO DE ENTRADA PÚBLICO
# ==========================================

def construir_prompt(cna, owm, aqi, forecast=None, contexto_sismo=None,
                     modo_nocturno=False):
    """
    Ensambla el prompt completo para el modelo de IA.
    v16.1: se retiran cna_hora y rocio_relevante (method=3 suspendido).

    Parámetros:
        cna            — salida de conagua.obtener_pronostico() o None
        owm            — dict de OWM (incluye pressure_etiqueta, weather_id_etiqueta) o None
        aqi            — dict de AQI (incluye aod_etiqueta) o None
        forecast       — dict pre-procesado del forecast horario o None
        contexto_sismo — dict con datos del sismo reciente o None
        modo_nocturno  — True si hora_actual >= sunset → perspectiva de mañana ampliada

    Retorna el texto del prompt listo para enviar a Gemini/Groq.
    """
    fecha_exacta = time.strftime("%Y-%m-%d")
    hora_exacta  = time.strftime("%H:%M")

    bloque_cna   = _bloque_conagua(cna, modo_nocturno=modo_nocturno)
    bloque_owm   = _bloque_owm(owm)
    bloque_aqi   = _bloque_aqi(aqi)
    bloque_fc    = _bloque_forecast(forecast)
    regla_lluvia = _regla_lluvia(owm, cna)
    bloque_sis   = _bloque_sismo(contexto_sismo)

    prompt = (
        "Eres el sistema automatizado de alerta meteorológica regional. "
        "Escribe un reporte de radio (NO mencionar palabras como 'radioescuchas' o similares) muy detallado para {ciudad} y alrededores. Evita ser redundante en la redacción y personaliza según la hora actual.\n\n"
        "{bloque_sis}"
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
        "(niebla, lluvia, o si es menor a 10km. NO mencionar si es de 10km ya que es el rango máximo).\n"
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
        "10. Presión atmosférica: la FUENTE 2 la presenta como 'valor hPa | etiqueta'. "
        "Usa el valor numérico como contexto interno para calibrar la narrativa; "
        "menciónalo solo si es relevante para el contexto. Describe la presión en una sola "
        "oración integrada al párrafo de viento o condiciones generales usando la etiqueta. "
        "Si la etiqueta contrasta con la condición actual "
        "(por ejemplo, presión alta pero lluvia activa), señálalo de forma breve e informativa. "
        "Si no hay contraste interesante o la presión es normal sin anomalías, omítela por completo.\n"
        "11. Viento: menciona el viento actual de la FUENTE 2 como el estado en este momento, "
        "incluyendo ráfagas si las hay. Si la FUENTE 4 indica que el viento se intensificará "
        "más de 8 km/h en las próximas horas, añade una oración de tendencia. "
        "Si no hay cambio significativo proyectado, no lo menciones.\n"
        "12. Pronóstico de lluvia a corto plazo (FUENTE 4): inclúyelo ÚNICAMENTE si "
        "la FUENTE 4 contiene datos de probabilidad de lluvia (probabilidad > 20% en la ventana). "
        "Si la FUENTE 4 indica [SIN EVENTOS RELEVANTES], no menciones lluvia proyectada. "
        "Cuando sí la incluyas, ten en cuenta que CONAGUA (FUENTE 1) reporta probabilidad "
        "acumulada del DÍA COMPLETO, mientras que la FUENTE 4 reporta las PRÓXIMAS 6 HORAS. "
        "Son ventanas temporales distintas. "
        "Si CONAGUA indica 0% para el día pero la FUENTE 4 muestra alta probabilidad en la "
        "ventana nocturna, la FUENTE 4 tiene precedencia narrativa por ser más granular y reciente: "
        "explica que aunque el pronóstico general del día fue de baja probabilidad, las condiciones "
        "de la tarde o noche han cambiado. "
        "Si la FUENTE 4 indica energía convectiva disponible junto a la lluvia, menciona que "
        "la precipitación podría presentarse en forma de chubascos cortos e intensos con posible "
        "actividad eléctrica, usando la escala de referencia provista. El campo 'CAPE (valor técnico)' "
        "de la FUENTE 4 contiene el valor real en J/kg; úsalo como contexto interno para precisar la intensidad de la "
        "convección en tu narrativa, no lo menciones literalmente ni uses el término técnico 'CAPE' salvo que sea relevante para el contexto; "
        "tradúcelo siempre a lenguaje accesible.\n"
        "13. Opacidad atmosférica (FUENTE 3): agrúpala dentro del párrafo de calidad del aire. "
        "La FUENTE 3 la presenta como 'valor | etiqueta'. "
        "Inclúyela ÚNICAMENTE si la etiqueta está presente (AOD > 0.2) Y la hora del "
        "reporte está entre las 06:00 y las 20:00. Descríbela en términos de claridad del cielo "
        "usando la etiqueta. Usa el valor numérico como contexto adicional para enriquecer la "
        "explicación (por ejemplo, precisar si está cerca del umbral o es marcadamente elevado), "
        "traduciéndolo siempre a lenguaje accesible. "
        "Si es horario nocturno o el valor es bajo, omítela completamente sin mencionarla.\n"
        "14. Perspectiva de mañana — Modo Nocturno: si la FUENTE 1 indica MODO NOCTURNO, "
        "dedica un párrafo completo y detallado al pronóstico de mañana. Describe la "
        "evolución esperada de temperatura, condiciones y viento. No te limites a una sola "
        "oración: el bloque de mañana debe ser comparable en extensión al de hoy.\n"
        "15. Alertas de fenómenos severos (FUENTE 2 y FUENTE 4): si cualquiera de estas fuentes "
        "contiene una línea de ALERTA o AVISO, menciónala con prioridad narrativa inmediatamente "
        "después del saludo y antes de las condiciones generales. Usa lenguaje claro y directo "
        "sin tecnicismos. La alerta de helada de la FUENTE 4 es especialmente crítica para "
        "cultivos y carreteras. El campo 'Isoterma (valor técnico)' de la "
        "FUENTE 4 contiene la altitud real de la isoterma de congelación en metros s.n.m.; "
        "úsalo para enriquecer la narrativa de helada (p. ej. señalar qué tan próxima está la "
        "isoterma a la altitud de la localidad ~{altitud_m} m s.n.m.). Mencionalo siempre en lenguaje accesible.\n\n"

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
        bloque_sis=bloque_sis,
        cna=bloque_cna,
        owm=bloque_owm,
        aqi=bloque_aqi,
        fc=bloque_fc,
        regla_lluvia=regla_lluvia,
        hora=hora_exacta,
        fm=config.FRECUENCIA_FM,
        mw=config.POTENCIA_MW,
        fecha=fecha_exacta,
        altitud_m=config.ALTITUD_M,
    )

    return prompt