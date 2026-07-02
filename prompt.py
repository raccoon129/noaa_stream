# rev 17.3.0
# rev anterior: rev 17.2.0
# Changelog:
#   17.3.0 — Se añade FUENTE 7 (Estaciones solares USNO): _bloque_estaciones()
#            inyecta el evento solar cercano (±VENTANA_EVENTO_SOLAR_DIAS) al prompt.
#            Incluye solsticios, equinoccios, perihelio y afelio con lenguaje de
#            proximidad (hoy/mañana/hace N días). No añade nuevas REGLAS;
#            el bloque es autoexplicativo para el modelo.
#   17.0.0 — _bloque_owm(): se añade la dirección cardinal del viento (wind_dir_cardinal)
#            proveniente de OWM al final de la línea de viento actual, si está disponible.
#            _bloque_forecast(): se añade línea de punto de rocío cuando
#            dew_point_relevante es True (horario nocturno y pre/post-amanecer);
#            se añade línea de saturación crítica cuando dew_point_critico es True
#            (spread temp−rocío ≤2°C, cualquier hora).
#            Regla 11 actualizada: separación explícita de FUENTE 1 (ráfagas proyectadas
#            del día) y FUENTE 2 (velocidad y dirección actual en tiempo real).
#            Regla 17 ampliada con el caso de saturación crítica (dew_point_critico).
#   16.8.0 — Se permite la inclusión del bloque lunar de día si la luna es visible
#            (visible_de_dia). Se expande _bloque_lunar() con transit_time y la bandera
#            visible_de_dia. Se rediseña la Regla 16.
#   16.7.0 — Se actualizan las referencias de FUENTE 5 de wttr.in a USNO.
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

import datetime
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

    # Dirección cardinal: añadir solo si está disponible. La traducción ya viene
    # hecha en Python (“del noreste”, “del sur”, etc.) para evitar alucinaciones.
    linea_dir = (
        ", proveniente {0}".format(owm["wind_dir_cardinal"])
        if owm.get("wind_dir_cardinal")
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
        "- Viento actual: {7} km/h{8}{dir}\n"
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
        dir=linea_dir,
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

    # Polvo en suspensión: solo si el valor es > 0 y representa una fraccion
    # no trivial del PM10 (> 10%). Si PM10 no está disponible, se expone solo
    # el valor absoluto de polvo.
    dust_val = aqi.get("dust")
    pm10_val = aqi.get("pm10")
    if dust_val is not None and dust_val > 0:
        if pm10_val and pm10_val > 0:
            pct_dust = round((dust_val / pm10_val) * 100, 1)
            linea_dust = "\n- Polvo en suspensión: {0:.1f} μg/m³ ({1}% del material particulado PM10)".format(
                dust_val, pct_dust
            )
        else:
            linea_dust = "\n- Polvo en suspensión: {0:.1f} μg/m³".format(dust_val)
    else:
        linea_dust = ""

    return (
        "- AQI: {0} | PM10: {1} μg/m³ | PM2.5: {2} μg/m³\n"
        "- Índice UV: {3}\n"
        "- Gases: CO: {4} μg/m³ | NO2: {5} μg/m³ | SO2: {6} μg/m³ | Ozono: {7} μg/m³"
        "{8}"
        "{9}"
    ).format(
        aqi["aqi"], aqi["pm10"], aqi["pm25"],
        aqi["uv"],
        aqi["co"], aqi["no2"], aqi["so2"], aqi["ozono"],
        linea_aod,
        linea_dust,
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
    if fc.get("helada_etiqueta") and fc["helada_etiqueta"] in _HELADA_MSG:
        lineas.append("- {0}".format(_HELADA_MSG[fc["helada_etiqueta"]]))

    # Punto de rocío: solo cuando la bandera dew_point_relevante es True
    # (horario nocturno o pre/post-amanecer temprano, 20:00-09:59).
    # Se presenta como dato de referencia técnica para que la IA lo interprete
    # en términos de riesgo de niebla o escarcha, sin mencionar el término científico.
    if fc.get("dew_point_relevante") and fc.get("dew_point") is not None:
        lineas.append(
            "- Punto de rocío (referencia técnica nocturna): {0}°C".format(fc["dew_point"])
        )

    # Saturación crítica: spread temp−rocío ≤2°C detectado a CUALQUIER hora.
    # Se inyecta con su propia etiqueta para que la Regla 17 la identifique y priorice.
    # Solo se añade si no está ya cubierta por dew_point_relevante (evitar duplicado).
    if fc.get("dew_point_critico") and fc.get("dew_point") is not None:
        if not fc.get("dew_point_relevante"):   # nocturno ya la expone; evitar repetir
            lineas.append(
                "- Punto de rocío (referencia técnica — saturación crítica): {0}°C".format(fc["dew_point"])
            )

    # Radiación solar: solo si hay un pico real (> 0 W/m²).
    # Solo se envía al prompt para enriquecer contexto de días con sol intenso.
    if fc.get("shortwave_pico") is not None:
        lineas.append(
            "- Radiación solar máxima proyectada próximas 24h: {0} W/m²".format(
                fc["shortwave_pico"]
            )
        )

    cuerpo = "\n".join(lineas)
    return "FUENTE 4 (Open-Meteo Pronóstico a corto plazo - próximas 6 horas):\n{0}{1}".format(cuerpo, refs_str)



# ==========================================
#   BLOQUE DE FASE LUNAR
# ==========================================

def _bloque_lunar(lunar):
    """
    Genera el bloque de fase lunar para el prompt.
    v16.9: incluye crepúsculo civil, mediodía solar y fase lunar más cercana
           (esta última solo si está en rango [-1, 3] días respecto a hoy).
    Se llama en modo nocturno, o de día si la luna es visible a la luz del sol.
    Si no hay datos, retorna un aviso neutro que instruye a omitirla.
    """
    if not lunar:
        return (
            "FUENTE 5 (USNO/Observatorio Naval de los Estados Unidos - Fase Lunar): [NO DISPONIBLE] "
            "Omite cualquier mención de la fase lunar en este reporte."
        )
    visible_dia_txt = "SÍ (es visible a plena luz del día)" if lunar.get("visible_de_dia") else "NO"

    # Línea condicional de fase cercana: solo si es narrativamente relevante [-1, 3] días
    dias = lunar.get("fase_cercana_dias")
    linea_fase_cercana = ""
    if dias is not None and -1 <= dias <= 3:
        nombre_fc = lunar.get("fase_cercana_nombre", "")
        hora_fc   = lunar.get("fase_cercana_hora", "N/D") or "N/D"
        if dias == -1:
            cuando = "ayer"
        elif dias == 0:
            cuando = "hoy"
        elif dias == 1:
            cuando = "mañana"
        elif dias == 2:
            cuando = "pasado mañana"
        else:
            cuando = "en {0} días".format(dias)
        linea_fase_cercana = (
            "\n- Próxima fase lunar destacada: {0} ocurre {1} a las {2}".format(
                nombre_fc, cuando, hora_fc
            )
        )

    return (
        "FUENTE 5 (USNO/Observatorio Naval de los Estados Unidos - Fase Lunar):\n"
        "- Fase lunar: {0} ({1}%)\n"
        "- Salida de la luna: {2} | Ocaso de la luna: {3}\n"
        "- Tránsito más alto (cenit): {4}\n"
        "- ¿Visible de día hoy?: {5}\n"
        "- Descripción de la fase: {6}\n"
        "- Crepúsculo civil: inicio {7} | fin {8}\n"
        "- Mediodía solar: {9}"
        "{10}"
    ).format(
        lunar["fase_nombre"],
        lunar["moon_illumination"],
        lunar["moonrise"],
        lunar["moonset"],
        lunar.get("transit_time", "N/D"),
        visible_dia_txt,
        lunar["fase_etiqueta"],
        lunar.get("crepusculo_inicio", "N/D"),
        lunar.get("crepusculo_fin", "N/D"),
        lunar.get("mediodia_solar", "N/D"),
        linea_fase_cercana,
    )


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
    Incluye TODOS los datos del evento: magnitud, epicentro, profundidad, hora,
    intensidades locales (SASSLA) y confirmaciones de agencias internacionales.
    """
    if not contexto_sismo:
        return ""

    magnitud  = contexto_sismo.get("ssn_magnitud")
    epicentro = contexto_sismo.get("epicentro", "territorio mexicano")
    prof      = contexto_sismo.get("ssn_profundidad_km")
    hora_ev   = contexto_sismo.get("hora_evento_sassla")

    if magnitud:
        mag_str = f"magnitud preliminar {magnitud}"
    else:
        mag_str = "intensidad detectada"

    prof_str = f" a una profundidad de {prof} km" if prof is not None else ""
    hora_str = f" ocurrido aproximadamente a las {hora_ev.split(' ')[1][:5]} hora local" if hora_ev else ""

    # Intensidades de SASSLA: solo relevantes cuando aún no hay confirmación internacional.
    # Una vez que EMSC/GFZ/USGS confirman el evento, son datos desfasados.
    hay_confirmacion_internacional = any([
        contexto_sismo.get("usgs_magnitud"),
        contexto_sismo.get("emsc_magnitud"),
        contexto_sismo.get("gfz_magnitud"),
    ])
    intensidades_str = ""
    if not hay_confirmacion_internacional:
        sassla_dict = contexto_sismo.get("intensidades_sassla", {})
        if sassla_dict:
            from sismo_regex import CIUDADES_SASSLA
            lineas_int = []
            for ciudad_abr, nivel in sassla_dict.items():
                nombre = CIUDADES_SASSLA.get(ciudad_abr, ciudad_abr)
                lineas_int.append(f"{nombre}: {nivel}")
            intensidades_str = (
                "Intensidades preliminares por región registradas por SASSLA (cortesía) "
                "(información del disparador de alerta, aún sin confirmación internacional):\n  "
                + "\n  ".join(lineas_int) + "\n"
            )
        else:
            # Retrocompatibilidad con campos planos
            lineas_int = []
            if contexto_sismo.get("intensidad_cdmx"):
                lineas_int.append(f"Ciudad de México: {contexto_sismo['intensidad_cdmx']}")
            if contexto_sismo.get("intensidad_tol"):
                lineas_int.append(f"Toluca: {contexto_sismo['intensidad_tol']}")
            if lineas_int:
                intensidades_str = (
                    "Intensidades registradas por SASSLA: "
                    + ", ".join(lineas_int) + ".\n"
                )

    # Datos enriquecidos de APIs internacionales — con descripción de la fuente para contexto del modelo
    extras = []
    if contexto_sismo.get("usgs_magnitud"):
        extras.append(
            f"USGS (Servicio Geológico de los Estados Unidos, principal agencia geofísica de referencia mundial) "
            f"reporta magnitud {contexto_sismo['usgs_magnitud']}"
        )
    if contexto_sismo.get("emsc_magnitud"):
        extras.append(
            f"EMSC (Centro Sismológico Euro-Mediterráneo, red de monitoreo sismológico en tiempo real de Europa) "
            f"reporta magnitud {contexto_sismo['emsc_magnitud']}"
        )
    if contexto_sismo.get("gfz_magnitud"):
        extras.append(
            f"GFZ Potsdam (Centro Alemán de Investigación en Geociencias, observatorio sismológico global de Alemania) "
            f"reporta magnitud {contexto_sismo['gfz_magnitud']}"
        )
    if contexto_sismo.get("usgs_tsunami") == 1:
        extras.append("USGS (Servicio Geológico de los Estados Unidos) ha emitido alerta de tsunami")
    if contexto_sismo.get("replicas_detectadas"):
        extras.append(
            f"El SSN (Servicio Sismológico Nacional de México) ha registrado "
            f"{contexto_sismo['replicas_detectadas']} réplicas posteriores al evento principal"
        )

    if extras:
        extras_str = (
            "\nConfirmación de agencias sismológicas internacionales (secundarias):\n- "
            + "\n- ".join(extras) + "\n"
            "Incluye estos datos en la mención del sismo de forma natural y accesible, "
            "mencionando de qué agencia proviene cada dato. "
            "El dato prioritario y oficial es siempre el del SSN; las demás agencias son confirmaciones internacionales.\n"

        )
        nota_actualizacion = ""
    else:
        extras_str = ""
        nota_actualizacion = (
            "Añade que 'El reporte detallado con información de agencias sismológicas "
            "internacionales estará disponible en la próxima actualización'. "
        )

    return (
        f"CONTEXTO SÍSMICO RECIENTE (CRÍTICO - INYECTAR AL INICIO DEL REPORTE, DESPUÉS DE LA HORA Y FECHA):\n"
        f"Fuente primaria: SSN (Servicio Sismológico Nacional de México — autoridad oficial mexicana en sismología).\n"
        f"Ha ocurrido un sismo{hora_str} de {mag_str} con epicentro en {epicentro}{prof_str}.\n"
        f"{intensidades_str}"
        f"{extras_str}"
        "Regla especial: Inicia el reporte meteorológico informando brevemente sobre este evento. "
        "Genera un párrafo introductorio sobre el evento y posteriormente la explicación precisa con los datos conjunto a una interpretación objetiva: "
        f"'{mag_str} fue registrado{hora_str} con epicentro en {epicentro}{prof_str}...'. "
        f"{nota_actualizacion}"
        "Tras esta breve mención, continúa fluidamente con el reporte del clima habitual.\n"
    )


# ==========================================
#   BLOQUE FUENTE 6: SISMO SSN HIDALGO
# ==========================================

def _bloque_ssn_hgo(eventos_ssn: list) -> str:
    """
    Genera el bloque de texto de actividad sísmica en Hidalgo para el prompt.
    Recibe la lista de grupos activos obtenida por ssn_rss.obtener_eventos_para_reporte().
    Retorna cadena vacía si no hay eventos para este slot.
    """
    if not eventos_ssn:
        return ""

    lineas = []
    for evento in eventos_ssn:
        grupo = evento.get("grupo", [])
        # Ordenar por magnitud descendente para presentar el más fuerte primero
        sismos_ordenados = sorted(grupo, key=lambda x: -x["magnitud"])
        for s in sismos_ordenados:
            lineas.append(
                "- M {mag}  {fecha}  {hora} (hora centro)\n"
                "  {ubicacion}\n"
                "  Lat: {lat}°  Long: {lon}°  Prof: {prof} km".format(
                    mag=s["magnitud"],
                    fecha=s["fecha_str"],
                    hora=s["hora_str"],
                    ubicacion=s["ubicacion"],
                    lat=s["latitud"]   if s["latitud"]   is not None else "N/D",
                    lon=s["longitud"]  if s["longitud"]  is not None else "N/D",
                    prof=s["profundidad_km"] if s["profundidad_km"] is not None else "N/D",
                )
            )

    if not lineas:
        return ""

    cuerpo = "\n".join(lineas)
    return (
        "FUENTE 6 (SSN/Servicio Sismológico Nacional — Actividad sísmica local):\n"
        "Se han registrado los siguientes sismos en el estado de Hidalgo:\n"
        f"{cuerpo}\n"
    )


# ==========================================
#   BLOQUE FUENTE 7: ESTACIÓN SOLAR (USNO)
# ==========================================

def _bloque_estaciones(evento_solar) -> str:
    """
    Genera el bloque FUENTE 7 para el prompt cuando existe un evento solar
    (solsticio, equinoccio, perihelio o afelio) dentro de la ventana de
    ±VENTANA_EVENTO_SOLAR_DIAS días respecto a hoy.

    El bloque es autoexplicativo: le indica al modelo qué es el evento y
    cómo referenciarlo sin necesidad de una Regla adicional en REGLAS.
    Retorna cadena vacía si no hay evento activo.
    """
    if not evento_solar:
        return ""

    nombre   = evento_solar.get("nombre_es", evento_solar.get("phenom", ""))
    hora     = evento_solar.get("hora_local", "N/D")
    signif   = evento_solar.get("significado", "")
    delta    = evento_solar.get("dias_al_evento", 0)

    # Fecha en formato natural
    try:
        fd = evento_solar["fecha_dt"]
        _MESES = ["enero","febrero","marzo","abril","mayo","junio",
                  "julio","agosto","septiembre","octubre","noviembre","diciembre"]
        fecha_natural = "{} de {} de {}".format(fd.day, _MESES[fd.month - 1], fd.year)
    except Exception:
        fecha_natural = str(evento_solar.get("fecha_dt", ""))

    # Lenguaje de proximidad
    if delta == 0:
        cuando = "HOY"
        instruccion = (
            f"Este evento ocurre HOY a las {hora} (hora centro). "
            "Ménciona esto de forma natural e informativa en el reporte, "
            "integrado al contexto astronómico o como dato notable del día."
        )
    elif delta == 1:
        cuando = "mañana"
        instruccion = "Menéciona que mañana ocurrirá este evento."
    elif delta == -1:
        cuando = "ayer"
        instruccion = "Puedes mencionar brevemente que ayer tuvo lugar este evento."
    elif delta > 0:
        cuando = f"en {delta} días"
        instruccion = f"Menéciona que en {delta} días ocurrirá este evento."
    else:
        cuando = f"hace {abs(delta)} días"
        instruccion = f"Puedes mencionar brevemente que hace {abs(delta)} días tuvo lugar."

    lineas = [
        f"FUENTE 7 (USNO — Evento solar/astronómico):",
        f"- Evento: {nombre}",
        f"- Fecha: {fecha_natural}",
        f"- Hora (hora centro, UTC-6): {hora}",
        f"- Referencia temporal: {cuando}",
    ]
    if signif:
        lineas.append(f"- Significado: {signif}")
    lineas.append(f"- Instrucción: {instruccion}")

    return "\n".join(lineas) + "\n\n"

def construir_prompt(cna, owm, aqi, forecast=None, contexto_sismo=None,
                     modo_nocturno=False, lunar=None, eventos_ssn=None,
                     evento_solar=None):
    """
    Ensambla el prompt completo para el modelo de IA.
    v17.3: añade evento_solar (dict del evento solar cercano de USNO o None).
    v17.2: añade eventos_ssn (list de grupos de sismos HGO activos).
    v17.1: fecha pre-generada en Python en español natural.
    v16.1: se retiran cna_hora y rocio_relevante (method=3 suspendido).

    Parámetros:
        cna            — salida de conagua.obtener_pronostico() o None
        owm            — dict de OWM o None
        aqi            — dict de AQI o None
        forecast       — dict del forecast horario o None
        contexto_sismo — dict con datos del sismo reciente (alerta SASSLA) o None
        modo_nocturno  — True si hora_actual >= sunset
        lunar          — dict de fase lunar de USNO o None
        eventos_ssn    — list de grupos de sismos HGO activos (ssn_rss) o None/[]
        evento_solar   — dict del evento solar cercano (meteorologo) o None

    Retorna el texto del prompt listo para enviar a Gemini/Groq.
    """
    # Fecha en formato natural en español, pre-computada en Python para evitar que el
    # modelo infiera el día de la semana y cometa errores en fechas lejanas a su corte.
    _DIAS_ES   = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    _MESES_ES  = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
    ]
    _ahora      = datetime.datetime.now()
    _dia_semana = _DIAS_ES[_ahora.weekday()]
    _mes        = _MESES_ES[_ahora.month - 1]
    fecha_exacta = "{dia_sem} {dia} de {mes} de {anio}".format(
        dia_sem=_dia_semana,
        dia=_ahora.day,
        mes=_mes,
        anio=_ahora.year,
    )
    hora_exacta  = time.strftime("%H:%M")

    bloque_cna   = _bloque_conagua(cna, modo_nocturno=modo_nocturno)
    bloque_owm   = _bloque_owm(owm)
    bloque_aqi   = _bloque_aqi(aqi)
    bloque_fc    = _bloque_forecast(forecast)
    regla_lluvia = _regla_lluvia(owm, cna)
    bloque_sis   = _bloque_sismo(contexto_sismo)
    bloque_ssn   = _bloque_ssn_hgo(eventos_ssn or [])
    bloque_est   = _bloque_estaciones(evento_solar)

    # La fase lunar se incluye en el prompt en modo nocturno o si es visible de día
    luna_visible_dia = lunar.get("visible_de_dia", False) if lunar else False
    if modo_nocturno or luna_visible_dia:
        bloque_lunar_txt = "\n" + _bloque_lunar(lunar) + "\n"
    else:
        bloque_lunar_txt = ""

    prompt = (
        "Eres el sistema automatizado de alerta meteorológica regional. "
        "Escribe un reporte de radio (NO mencionar palabras como 'radioescuchas' o similares) muy detallado para {ciudad} y alrededores. Evita ser redundante en la redacción y personaliza según la hora actual.\n\n"
        "{bloque_sis}"
        "{ssn}"
        "{cna}\n\n"
        "{owm}\n\n"
        "FUENTE 3 (Open-Meteo - Salud Ambiental y Radiación):\n"
        "{aqi}\n\n"
        "{fc}\n"
        "{lunar}"
        "{estaciones}"
        "REGLAS PARA LA REDACCIÓN (CRÍTICAS):\n"
        "1. Inicia con un saludo formal simple según la hora del día (buenos dias/tardes/noches).\n"
        "{regla_lluvia}\n"
        "3. Menciona la sensación térmica junto a la temperatura actual para darle más valor al reporte. Además Da interpretación del clima actual (Ejemplo: Noche muy fría, día caluroso, día/noche lluvioso, etc). \n"
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
        "11. Viento: combina ambas fuentes para dar un cuadro completo sin redundar.\n"
        "  • Velocidad y dirección en este momento: usa FUENTE 2. Menciona la velocidad y"
        " la dirección cardinal ('del noreste', 'del sur', etc.). Usa la dirección para"
        " enriquecer el contexto (ej. vientos del norte indican masa de aire frío;"
        " del este/noreste pueden traer humedad del Golfo).\n"
        "  • Ráfagas proyectadas del día: usa FUENTE 1 (CONAGUA). Si las ráfagas del día"
        " son notablemente superiores al viento actual de la FUENTE 2, menciona que se"
        " esperan ráfagas de hasta X km/h durante el día.\n"
        "  • Tendencia a corto plazo: si la FUENTE 4 indica que el viento se intensificará"
        " más de 8 km/h en las próximas horas, añade una oración de tendencia."
        " Si no hay cambio significativo proyectado, no lo menciones.\n"
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

        "16. Fase lunar y astronomía solar (FUENTE 5): Si la FUENTE 5 está disponible, incorpórala de forma natural:\n"
        "   - FASE LUNAR DE NOCHE: Menciona la fase lunar integrada a las condiciones nocturnas, "
        "considerando la nubosidad actual de la FUENTE 2. Describe cómo la iluminación lunar afecta "
        "la luminosidad de la noche o se ve limitada por las nubes. Incluye la hora de salida o de ocaso de la luna.\n"
        "   - FASE LUNAR DE DÍA (Solo si '¿Visible de día hoy?' es SÍ): Menciona que la luna es visible "
        "en el cielo diurno, describiendo su fase y cómo la nubosidad la afecta. Si no es visible en lo absoluto debido a la gran nubosidad, OMITE la mención de esta parte por completo."
        "Si es de día y marca '¿Visible de día hoy?: NO', NO menciones la luna en absoluto.\n"
        "   - CREPÚSCULO CIVIL AL AMANECER: Si la hora del reporte está entre el 'Crepúsculo civil inicio' "
        "y la hora de salida del sol (FUENTE 2 amanecer), menciona que la luz del día ya comienza a asomar "
        "aunque el sol todavía no ha salido. Es el momento ideal para quienes madrugan. "
        "Usa la hora exacta de inicio del crepúsculo para darle precisión al dato.\n"
        "   - CREPÚSCULO CIVIL AL ANOCHECER: Si la hora del reporte está entre la puesta del sol (FUENTE 2 atardecer) "
        "y el 'Crepúsculo civil fin', menciona que aún hay luz natural residual en el cielo "
        "aunque el sol ya se ocultó. Útil para quienes regresan a casa o todavía realizan actividades en el exterior.\n"
        "   - MEDIODÍA SOLAR: Si la hora del reporte está entre las 11:30 y las 13:30, "
        "menciona que el sol está en o cerca de su punto más alto del día (hora exacta del mediodía solar de la FUENTE 5). "
        "Es el momento de mayor radiación UV y sombras más cortas. Incorpóralo al párrafo de condiciones actuales "
        "o de calidad del aire, no como dato aislado.\n"
        "   - FASE LUNAR CERCANA: Si la FUENTE 5 incluye la línea 'Próxima fase lunar destacada', "
        "menciónala de forma breve y natural al final del bloque lunar. "
        "Usa el lenguaje de proximidad (hoy, mañana, pasado mañana, ayer) que ya indica la fuente. "
        "No la menciones si la línea no está presente en la FUENTE 5.\n\n"

        "17. Punto de rocío (FUENTE 4): si la FUENTE 4 contiene una línea de punto de rocío,"
        " úsala para enriquecer el reporte con una advertencia práctica."
        " No menciones el término técnico 'punto de rocío' (salvo que sea realmente necesario) "
        "ni su valor numérico en grados: tradúcelo siempre a lenguaje accesible.\n"
        "   CASO A — Saturación crítica (línea dice 'saturación crítica'):"
        " PRIORIDAD MÁXIMA, válido a cualquier hora. El aire está prácticamente saturado."
        " Avisa que existe riesgo inminente de formación de niebla o neblina, especialmente"
        " en carreteras, barrancas y zonas bajas. Recomienda precauciones."
        " Incorpóralo antes del párrafo de condiciones generales si es relevante para la hora.\n"
        "   CASO B — Referencia nocturna (línea dice 'referencia técnica nocturna'):\n"
        "     b1) Si el valor implica una diferencia pequeña respecto a la temperatura actual"
        " (≤2°C según FUENTE 2): avisa sobre formación probable de niebla nocturna o neblina"
        " en carreteras y zonas bajas. Recomienda precaución al conducir en la madrugada.\n"
        "     b2) Si el valor de la línea es menor a 0°C: advierte sobre riesgo de escarcha"
        " en cultivos, superficies y carreteras. Intégralo al bloque de helada si ya existe.\n"
        "     b3) En cualquier otro caso nocturno: mención breve de humedad ambiental elevada"
        " (ej. 'la humedad nocturna se mantendrá alta').\n"
        "   Si la FUENTE 4 no contiene ninguna línea de punto de rocío,"
        " NO menciones rocio, humedad nocturna ni valores numéricos de saturación.\n\n"

        "18. Actividad sísmica local (FUENTE 6 — SSN): si la FUENTE 6 está disponible, "
        "significa que el SSN registró un sismo en el estado de Hidalgo "
        "que es relevante. Menciónalo de forma INFORMATIVA al inicio del reporte"
        "Usa los datos que aparecen en la FUENTE 6: magnitud, hora (en formato natural), ubicación referencial y "
        "profundidad en kilómetros. Debe extenderse la información disponible sin generar ambigüedad.\n\n"

        "19. Polvo en suspensión (FUENTE 3): si la FUENTE 3 incluye la línea ‘Polvo en suspensión’, "
        "inclúyelo al final del párrafo de calidad del aire. Mencionalo en lenguaje accesible, describe si hay polvo o partículas en el aire que puedan afectar la visibilidad o irritar "
        "vías respiratorias. El porcentaje indica qué fracción del PM10 total se debe a polvo mineral o sahariano. Hay que hacer su mención de forma objetiva con respaldo de la información disponible y las condiciones climáticas: "
        "si supera el 30%, dále énfasis (ej. 'una parte importante de las partículas en el aire hoy corresponde a polvo'). "
        "Si el porcentaje es bajo (≤15%), basta una mención breve sin alarmar. "
        "Si la línea no está presente en la FUENTE 3, NO menciones polvo en absoluto.\n\n"

        "20. Radiación solar (FUENTE 4): si la FUENTE 4 incluye la línea ‘Radiación solar máxima proyectada’, "
        "méncionala en el contexto del clima del día, no de forma aislada. "
        "Tráducela a lenguaje cotidiano: NO uses el término técnico 'shortwave radiation' ni el valor en W/m². "
        "En cambio, usa la siguiente escala orientativa para comunicar la intensidad solar del día y complementa según las condiciones climáticas actuales: "
        "Baja (<200 W/m²): cielo cubierto, sol sin presencia real. "
        "Moderada (200-500 W/m²): sol presente con intervalos nublados. "
        "Alta (500-800 W/m²): día soleado con buena insolación. "
        "Muy alta (>800 W/m²): sol intenso, condiciones de máxima insolación. "
        "Incorpórala al final del párrafo de condiciones generales o de UV cuando sea relevante diurno. "
        "Si la hora del reporte es nocturno, OMITE esta línea.\n\n"

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
        ssn=bloque_ssn,
        estaciones=bloque_est,
        cna=bloque_cna,
        owm=bloque_owm,
        aqi=bloque_aqi,
        fc=bloque_fc,
        lunar=bloque_lunar_txt,
        regla_lluvia=regla_lluvia,
        hora=hora_exacta,
        fm=config.FRECUENCIA_FM,
        mw=config.POTENCIA_MW,
        fecha=fecha_exacta,
        altitud_m=config.ALTITUD_M,
    )

    return prompt