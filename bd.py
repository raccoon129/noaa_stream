# rev 16.5.0
# rev anterior: rev 16.4.0
# Changelog:
#   16.5.0 — INSERT de datos_fase_lunar ampliado con las 8 columnas de migración v19:
#            crepusculo_inicio, crepusculo_fin, mediodia_solar, dia_semana,
#            fase_cercana_nombre, fase_cercana_fecha, fase_cercana_hora,
#            fase_cercana_dias. Todos provienen de la API USNO.
#   16.3.0 — guardar_condicion_especial() generalizado: datos_sassla → datos_fuente_primaria,
#            datos_ssn → datos_fuente_secundaria. Se agrega fuente_alerta (sistema que emitió
#            la alerta: SASSLA, CONAGUA, CENAPRED, etc.) y guion_analisis/prompt_analisis
#            (reporte tardío post-evento). Defaults internos evitan KeyError en llamadores
#            que no incluyan las nuevas claves. Requiere migration_v17.sql en BD.
#   16.2.0 — datos_forecast renombrada a datos_forecast_openmeteo. FK cambia de
#            reportes_climatologicos → datos_openmeteo (openmeteo_id). El forecast
#            solo se persiste si datos_openmeteo fue insertado en el mismo ciclo.
#            Se retiran datos_conagua_horario y flags_ejecucion.
#   16.0.0 — Expande INSERT de datos_owm, datos_conagua, datos_openmeteo con
#            nuevos campos v16. Nuevas inserciones en datos_forecast y flags.
#   15.2.0 — Corrección: sub-dict plano para reportes_climatologicos.
#   15.1.0 — guardar_reporte_en_bd con esquema normalizado por fuente.
#   15.0.0 — Extracción de toda la lógica MySQL a módulo independiente.

import datetime
from typing import Optional

import mysql.connector
from mysql.connector import Error as ErrorMySQL

import config
import estado


# ==========================================
#   SANITIZACIÓN DE ERRORES
# ==========================================

def _sanitizar_error(mensaje: str) -> str:
    """Enmascara valores sensibles conocidos en mensajes de error antes de persistirlos."""
    sensibles = [config.OWM_API_KEY, config.GEMINI_API_KEY, config.OPENROUTER_API_KEY]
    resultado = mensaje
    for clave in sensibles:
        if clave and clave in resultado:
            resultado = resultado.replace(clave, "(XXXXX)")
    return resultado


def _limpiar_hora_bd(hora_str: Optional[str]) -> Optional[str]:
    """Convierte 'N/D' o valores vacíos a None para columnas TIME en MySQL."""
    if not hora_str or hora_str == "N/D":
        return None
    return hora_str


# ==========================================
#   CONEXIÓN
# ==========================================

def obtener_conexion_bd():
    """Abre y retorna una conexión MySQL. Retorna None si falla."""
    try:
        conexion = mysql.connector.connect(**config.BD_CONFIG)
        if conexion.is_connected():
            return conexion
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️  No se pudo conectar a MySQL: {e}")
    return None


# ==========================================
#   AUDITORÍA DE ERRORES DE APIS
# ==========================================

def registrar_error_bd(conexion, fuente: str, mensaje: str, reporte_id=None):
    """Inserta un registro de error en la tabla de auditoría."""
    if not conexion:
        return
    try:
        cursor = conexion.cursor()
        timestamp_rpi = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT INTO errores_recoleccion (fuente, mensaje_error, reporte_id, timestamp_error)
               VALUES (%s, %s, %s, %s)""",
            (fuente, str(mensaje), reporte_id, timestamp_rpi)
        )
        conexion.commit()
        cursor.close()
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️  Error al registrar auditoría: {e}")


# ==========================================
#   GUARDADO DEL REPORTE PRINCIPAL
# ==========================================

def guardar_reporte_en_bd(datos_reporte: dict) -> Optional[int]:
    """
    Inserta el reporte climatológico en el esquema normalizado por fuente.

    Espera un dict con las siguientes claves obligatorias:
        fecha_reporte, hora_reporte, timestamp_completo, ciudad,
        guion_texto, modelo_ia_usado, guion_generado

    Y las siguientes claves opcionales (sub-dicts por fuente):
        conagua — dict con los campos de CONAGUA, o None si no respondió
        owm     — dict con los campos de OWM, o None si no respondió
        aqi     — dict con los campos de Open-Meteo, o None si no respondió

    Flujo:
        1. INSERT en reportes_climatologicos (metadatos + guion) → obtiene reporte_id
        2. Si conagua is not None  → INSERT en datos_conagua
        3. Si owm     is not None  → INSERT en datos_owm
        4. Si aqi     is not None  → INSERT en datos_openmeteo

    Retorna el ID del reporte insertado, o None si falló la inserción principal.
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        print(f"[BD] - {estado.ts()} ⚠️  Reporte NO guardado (sin conexión).")
        return None

    try:
        cursor = conexion.cursor()

        # ------------------------------------------------------------------
        # 1. Tabla madre: solo metadatos y guion
        # Se extrae un sub-dict plano para evitar que mysql.connector intente
        # serializar los valores anidados (conagua/owm/aqi) que son dicts.
        # ------------------------------------------------------------------
        datosPlanos = {
            "fecha_reporte":      datos_reporte["fecha_reporte"],
            "hora_reporte":       datos_reporte["hora_reporte"],
            "timestamp_completo": datos_reporte["timestamp_completo"],
            "ciudad":             datos_reporte["ciudad"],
            "guion_texto":        datos_reporte["guion_texto"],
            "modelo_ia_usado":    datos_reporte["modelo_ia_usado"],
            "guion_generado":     datos_reporte["guion_generado"],
        }
        cursor.execute(
            """INSERT INTO reportes_climatologicos (
                   fecha_reporte, hora_reporte, timestamp_completo, ciudad,
                   guion_texto, modelo_ia_usado, guion_generado
               ) VALUES (
                   %(fecha_reporte)s, %(hora_reporte)s, %(timestamp_completo)s, %(ciudad)s,
                   %(guion_texto)s, %(modelo_ia_usado)s, %(guion_generado)s
               )""",
            datosPlanos,
        )
        conexion.commit()
        nuevo_id = cursor.lastrowid
        print(f"[BD] - {estado.ts()} ✅ Reporte guardado en historial (ID: {nuevo_id})")

        # ------------------------------------------------------------------
        # 2. datos_conagua (solo si la fuente respondió)
        # ------------------------------------------------------------------
        conagua = datos_reporte.get("conagua")
        if conagua is not None:
            cursor.execute(
                """INSERT INTO datos_conagua (
                       reporte_id,
                       condicion, temp_max, temp_min, prob_lluvia, precipitacion,
                       viento, dir_viento, rafagas,
                       cc_pct, dirvieng, dloc,
                       man_condicion, man_temp_max, man_temp_min,
                       man_prob_lluvia, man_precipitacion, man_viento,
                       man_rafagas, man_dir_viento, man_cc
                   ) VALUES (
                       %s,
                       %s, %s, %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s
                   )""",
                (
                    nuevo_id,
                    conagua.get("condicion"),     conagua.get("temp_max"),
                    conagua.get("temp_min"),      conagua.get("prob_lluvia"),
                    conagua.get("precipitacion"), conagua.get("viento"),
                    conagua.get("dir_viento"),    conagua.get("rafagas"),
                    conagua.get("cc"),            conagua.get("dirvieng"),
                    conagua.get("dloc"),
                    conagua.get("man_condicion"), conagua.get("man_temp_max"),
                    conagua.get("man_temp_min"),  conagua.get("man_prob_lluvia"),
                    conagua.get("man_precipitacion"), conagua.get("man_viento"),
                    conagua.get("man_rafagas"),   conagua.get("man_dir_viento"),
                    conagua.get("man_cc"),
                ),
            )
            conexion.commit()
            print(f"[BD] - {estado.ts()} ✅ Datos CONAGUA guardados (reporte_id: {nuevo_id})")

        # ------------------------------------------------------------------
        # 3. datos_owm (solo si la fuente respondió)
        # ------------------------------------------------------------------
        owm = datos_reporte.get("owm")
        if owm is not None:
            cursor.execute(
                """INSERT INTO datos_owm (
                       reporte_id,
                       temp_actual, sensacion, humedad, condicion,
                       visibilidad, lluvia_1h, amanecer, atardecer,
                       presion_hpa, presion_suelo_hpa,
                       viento_kmh, rafagas_kmh, nubosidad_pct, wind_deg,
                       weather_id, weather_id_etiq
                   ) VALUES (
                       %s,
                       %s, %s, %s, %s,
                       %s, %s, %s, %s,
                       %s, %s,
                       %s, %s, %s, %s,
                       %s, %s
                   )""",
                (
                    nuevo_id,
                    owm.get("temp"),          owm.get("feels"),
                    owm.get("humedad"),        owm.get("desc"),
                    owm.get("visibilidad"),    owm.get("lluvia_1h"),
                    owm.get("amanecer"),       owm.get("atardecer"),
                    owm.get("pressure"),       owm.get("grnd_level"),
                    owm.get("wind_speed_kmh"), owm.get("wind_gust_kmh"),
                    owm.get("clouds_all"),     owm.get("wind_deg"),
                    owm.get("weather_id"),     owm.get("weather_id_etiqueta"),
                ),
            )
            conexion.commit()
            print(f"[BD] - {estado.ts()} ✅ Datos OWM guardados (reporte_id: {nuevo_id})")

        # ------------------------------------------------------------------
        # 4. datos_openmeteo (solo si la fuente respondió)
        # ------------------------------------------------------------------
        openmeteo_id = None
        aqi = datos_reporte.get("aqi")
        if aqi is not None:
            cursor.execute(
                """INSERT INTO datos_openmeteo (
                       reporte_id,
                       aqi, pm10, pm25, uv_index,
                       co, no2, so2, ozono, aod, dust
                   ) VALUES (
                       %s,
                       %s, %s, %s, %s,
                       %s, %s, %s, %s, %s, %s
                   )""",
                (
                    nuevo_id,
                    aqi.get("aqi"),   aqi.get("pm10"),
                    aqi.get("pm25"),  aqi.get("uv"),
                    aqi.get("co"),    aqi.get("no2"),
                    aqi.get("so2"),   aqi.get("ozono"),
                    aqi.get("aerosol_optical_depth"),
                    aqi.get("dust"),
                ),
            )
            conexion.commit()
            openmeteo_id = cursor.lastrowid
            print(f"[BD] - {estado.ts()} ✅ Datos Open-Meteo guardados (id: {openmeteo_id}, reporte_id: {nuevo_id})")

        # ------------------------------------------------------------------
        # 5. datos_forecast_openmeteo (subtabla de datos_openmeteo)
        #    Solo se persiste si datos_openmeteo fue insertado en este ciclo.
        # ------------------------------------------------------------------
        fc = datos_reporte.get("forecast")
        if fc is not None and openmeteo_id is not None:
            cursor.execute(
                """INSERT INTO datos_forecast_openmeteo (
                       openmeteo_id,
                       prob_lluvia_max, hora_pico_lluvia, prec_total,
                       viento_actual, viento_max, hora_viento_max,
                       cape_max, hora_cape_max, cape_etiqueta,
                       dew_point, freezing_level_m, helada_etiqueta,
                       shortwave_pico
                   ) VALUES (
                       %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s
                   )""",
                (
                    openmeteo_id,
                    fc.get("prob_lluvia_max"),  fc.get("hora_pico_lluvia"),
                    fc.get("prec_total"),
                    fc.get("viento_actual"),    fc.get("viento_max"),
                    fc.get("hora_viento_max"),
                    fc.get("cape_max"),         fc.get("hora_cape_max"),
                    fc.get("cape_etiqueta"),
                    fc.get("dew_point"),        fc.get("freezing_level_m"),
                    fc.get("helada_etiqueta"),
                    fc.get("shortwave_pico"),
                ),
            )
            conexion.commit()
            print(f"[BD] - {estado.ts()} ✅ Datos Forecast guardados (openmeteo_id: {openmeteo_id})")
        elif fc is not None and openmeteo_id is None:
            print(f"[BD] - {estado.ts()} ⚠️  Forecast omitido: datos_openmeteo no disponible en este ciclo.")

        # ------------------------------------------------------------------
        # 6. datos_fase_lunar (solo si los datos de USNO están disponibles)
        # ------------------------------------------------------------------
        lunar = datos_reporte.get("lunar")
        if lunar is not None:
            cursor.execute(
                """INSERT INTO datos_fase_lunar (
                       reporte_id,
                       fase_nombre, fase_ingles, iluminacion_porcentaje,
                       salida_luna, ocaso_luna, transito_luna,
                       visible_de_dia, fase_etiqueta,
                       crepusculo_inicio, crepusculo_fin, mediodia_solar,
                       dia_semana,
                       fase_cercana_nombre, fase_cercana_fecha,
                       fase_cercana_hora, fase_cercana_dias
                   ) VALUES (
                       %s,
                       %s, %s, %s,
                       %s, %s, %s,
                       %s, %s,
                       %s, %s, %s,
                       %s,
                       %s, %s,
                       %s, %s
                   )""",
                (
                    nuevo_id,
                    lunar.get("fase_nombre"),
                    lunar.get("moon_phase"),
                    int(lunar.get("moon_illumination")) if lunar.get("moon_illumination") and lunar.get("moon_illumination") != "N/D" else None,
                    _limpiar_hora_bd(lunar.get("moonrise")),
                    _limpiar_hora_bd(lunar.get("moonset")),
                    _limpiar_hora_bd(lunar.get("transit_time")),
                    1 if lunar.get("visible_de_dia") else 0,
                    lunar.get("fase_etiqueta"),
                    _limpiar_hora_bd(lunar.get("crepusculo_inicio")),
                    _limpiar_hora_bd(lunar.get("crepusculo_fin")),
                    _limpiar_hora_bd(lunar.get("mediodia_solar")),
                    lunar.get("dia_semana"),
                    lunar.get("fase_cercana_nombre"),
                    lunar.get("fase_cercana_fecha"),
                    _limpiar_hora_bd(lunar.get("fase_cercana_hora")),
                    lunar.get("fase_cercana_dias"),
                ),
            )
            conexion.commit()
            print(f"[BD] - {estado.ts()} ✅ Datos Fase Lunar guardados (reporte_id: {nuevo_id})")

        cursor.close()
        return nuevo_id

    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️  Error al insertar reporte: {e}")
        registrar_error_bd(conexion, "INSERCION", str(e))
        return None
    finally:
        if conexion.is_connected():
            conexion.close()


# ==========================================
#   GUARDADO DEL RESUMEN WEB
# ==========================================

def guardar_resumen_en_bd(datos_web: dict, reporte_id: int):
    """
    Guarda un respaldo estructurado y relacionado en BD de los datos expuestos
    en el monitor web (datos.json).
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        return

    try:
        cursor = conexion.cursor()
        sql = """
            INSERT INTO resumen_reporte_clima (
                reporte_id, timestamp_log, temp, condicion, humedad, viento, aqi, pm25, hora_actualizacion
            ) VALUES (
                %(reporte_id)s, %(timestamp_log)s, %(temp)s, %(condicion)s, %(humedad)s, %(viento)s, %(aqi)s, %(pm25)s, %(hora_actualizacion)s
            )
        """
        datos_query = datos_web.copy()
        datos_query['reporte_id']    = reporte_id
        datos_query['timestamp_log'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(sql, datos_query)
        conexion.commit()
        cursor.close()
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️ Error al guardar respaldo del resumen vinculado (JSON): {e}")
    finally:
        if conexion.is_connected():
            conexion.close()


# ==========================================
#   GUARDADO DEL PROMPT DE IA
# ==========================================

def guardar_prompt_en_bd(reporte_id: int, texto_prompt: str):
    """
    Guarda el prompt exacto enviado a Gemini en la tabla prompt_reporte_climatologico.
    Diseñado para ser llamado en hilo secundario para no bloquear el flujo principal.
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        return
    try:
        cursor = conexion.cursor()
        timestamp_rpi = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            """INSERT INTO prompt_reporte_climatologico (reporte_id, prompt_texto, timestamp_prompt)
               VALUES (%s, %s, %s)""",
            (reporte_id, texto_prompt, timestamp_rpi)
        )
        conexion.commit()
        cursor.close()
        print(f"[BD] - {estado.ts()} ✅ Prompt guardado (reporte_id: {reporte_id})")
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️  Error al guardar prompt: {e}")
    finally:
        if conexion.is_connected():
            conexion.close()


# ==========================================
#   CONDICIONES ESPECIALES (SISMOS, ETC.)
# ==========================================

def guardar_condicion_especial(datos_evento: dict) -> Optional[int]:
    """
    Inserta un nuevo registro en la tabla condiciones_especiales.
    Retorna el ID generado o None si hay error.

    El dict datos_evento debe incluir las siguientes claves:
        timestamp_evento    — str "YYYY-MM-DD HH:MM:SS"
        tipo                — str: "SISMO", "SIMULACRO", "HELADA", "INCENDIO", etc.
        subtipo             — str descriptivo o None
        descripcion         — str resumen humano o None
        ubicacion           — str o None
        latitud             — float o None
        longitud            — float o None
        fuente_alerta       — str: sistema que emitió la alerta (SASSLA, CONAGUA, CENAPRED, etc.) o None
        datos_fuente_primaria  — JSON str: datos crudos de la fuente que emitió la alerta
        datos_fuente_secundaria — JSON str: confirmación de agencia secundaria (SSN, USGS, etc.) o None
        datos_investigacion — JSON str: datos post-evento de fuentes adicionales o None
        guion_inmediato     — str o None
        prompt_inmediato    — str o None
        guion_analisis      — str o None (reporte tardío post-evento)
        prompt_analisis     — str o None
        modelo_ia_usado     — str o None
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        return None

    try:
        cursor = conexion.cursor()
        sql = """
            INSERT INTO condiciones_especiales (
                timestamp_evento, tipo, subtipo, descripcion, ubicacion, latitud, longitud,
                fuente_alerta,
                datos_fuente_primaria, datos_fuente_secundaria, datos_investigacion,
                guion_inmediato, prompt_inmediato,
                guion_analisis, prompt_analisis,
                modelo_ia_usado
            ) VALUES (
                %(timestamp_evento)s, %(tipo)s, %(subtipo)s, %(descripcion)s,
                %(ubicacion)s, %(latitud)s, %(longitud)s,
                %(fuente_alerta)s,
                %(datos_fuente_primaria)s, %(datos_fuente_secundaria)s, %(datos_investigacion)s,
                %(guion_inmediato)s, %(prompt_inmediato)s,
                %(guion_analisis)s, %(prompt_analisis)s,
                %(modelo_ia_usado)s
            )
        """
        # Garantizar claves opcionales con valor por defecto para evitar KeyError
        datos_completo = {
            "fuente_alerta":            None,
            "datos_fuente_primaria":    None,
            "datos_fuente_secundaria":  None,
            "guion_analisis":           None,
            "prompt_analisis":          None,
        }
        datos_completo.update(datos_evento)
        cursor.execute(sql, datos_completo)
        conexion.commit()
        nuevo_id = cursor.lastrowid
        print(f"[BD] - {estado.ts()} ✅ Evento '{datos_evento.get('tipo')}' registrado en BD (ID: {nuevo_id})")
        cursor.close()
        return nuevo_id
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️ Error al registrar condición especial: {e}")
        return None
    finally:
        if conexion.is_connected():
            conexion.close()

def actualizar_condicion_especial(evento_id: int, campos_actualizar: dict):
    """
    Actualiza campos específicos de un registro en condiciones_especiales (ej: guion_analisis, datos_investigacion).
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        return

    try:
        cursor = conexion.cursor()
        
        # Construir el SET clause dinámicamente
        set_clause = ", ".join([f"{key} = %s" for key in campos_actualizar.keys()])
        valores = list(campos_actualizar.values())
        valores.append(evento_id)
        
        sql = f"UPDATE condiciones_especiales SET {set_clause} WHERE id = %s"
        
        cursor.execute(sql, valores)
        conexion.commit()
        print(f"[BD] - {estado.ts()} ✅ Evento especial actualizado en BD (ID: {evento_id})")
        cursor.close()
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️ Error al actualizar condición especial: {e}")
    finally:
        if conexion.is_connected():
            conexion.close()


def guardar_historial_condicion_especial(evento_id: int, datos_historial: dict) -> Optional[int]:
    """
    Inserta un nuevo registro de actualización/enriquecimiento en historial_condiciones_especiales.
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        return None

    try:
        cursor = conexion.cursor()
        sql = """
            INSERT INTO historial_condiciones_especiales (
                condicion_especial_id, subtipo, descripcion, ubicacion, latitud, longitud,
                datos_fuente_primaria, datos_fuente_secundaria, datos_investigacion,
                guion_analisis, prompt_analisis, modelo_ia_usado
            ) VALUES (
                %(condicion_especial_id)s, %(subtipo)s, %(descripcion)s, %(ubicacion)s, %(latitud)s, %(longitud)s,
                %(datos_fuente_primaria)s, %(datos_fuente_secundaria)s, %(datos_investigacion)s,
                %(guion_analisis)s, %(prompt_analisis)s, %(modelo_ia_usado)s
            )
        """
        # Valores por defecto para evitar KeyErrors
        datos_completo = {
            "condicion_especial_id":   evento_id,
            "subtipo":                 None,
            "descripcion":             None,
            "ubicacion":               None,
            "latitud":                 None,
            "longitud":                None,
            "datos_fuente_primaria":   None,
            "datos_fuente_secundaria": None,
            "datos_investigacion":     None,
            "guion_analisis":          None,
            "prompt_analisis":         None,
            "modelo_ia_usado":         None,
        }
        datos_completo.update(datos_historial)
        cursor.execute(sql, datos_completo)
        conexion.commit()
        nuevo_id = cursor.lastrowid
        print(f"[BD] - {estado.ts()} ✅ Registro de historial de condición especial guardado (ID: {nuevo_id}, Evento Madre: {evento_id})")
        cursor.close()
        return nuevo_id
    except ErrorMySQL as e:
        print(f"[BD] - {estado.ts()} ⚠️ Error al registrar historial de condición especial: {e}")
        return None
    finally:
        if conexion.is_connected():
            conexion.close()