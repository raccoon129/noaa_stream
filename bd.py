# rev 15.2.0
# rev anterior: rev 15.1.0
# Changelog:
#   15.2.0 — Corrección: el INSERT principal de reportes_climatologicos ahora recibe
#            un sub-dict plano en lugar del dict completo, evitando el error
#            "Python 'dict' cannot be converted to a MySQL type" que se producía
#            porque mysql.connector intentaba serializar las claves anidadas
#            (conagua, owm, aqi) aunque no estuvieran en el SQL.
#   15.1.0 — guardar_reporte_en_bd adaptado al esquema normalizado por fuente.
#            La tabla madre (reportes_climatologicos) recibe solo metadatos y guion.
#            Los datos meteorológicos se insertan condicionalmente en las tablas
#            hijas datos_conagua, datos_owm y datos_openmeteo (1:0..1).
#            La firma pública de todas las funciones permanece sin cambios.
#   15.0.0 — Extracción de toda la lógica MySQL a módulo independiente.
#            Incluye: conexión, registro de errores, guardado de reportes,
#            resúmenes web y prompts. Sanitización de claves API en errores.

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
    sensibles = [config.OWM_API_KEY, config.GEMINI_API_KEY, config.GROQ_API_KEY]
    resultado = mensaje
    for clave in sensibles:
        if clave and clave in resultado:
            resultado = resultado.replace(clave, "(XXXXX)")
    return resultado


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
                       man_condicion, man_temp_max, man_temp_min
                   ) VALUES (
                       %s,
                       %s, %s, %s, %s, %s,
                       %s, %s, %s,
                       %s, %s, %s
                   )""",
                (
                    nuevo_id,
                    conagua.get("condicion"),    conagua.get("temp_max"),
                    conagua.get("temp_min"),     conagua.get("prob_lluvia"),
                    conagua.get("precipitacion"),conagua.get("viento"),
                    conagua.get("dir_viento"),   conagua.get("rafagas"),
                    conagua.get("man_condicion"),conagua.get("man_temp_max"),
                    conagua.get("man_temp_min"),
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
                       visibilidad, lluvia_1h, amanecer, atardecer
                   ) VALUES (
                       %s,
                       %s, %s, %s, %s,
                       %s, %s, %s, %s
                   )""",
                (
                    nuevo_id,
                    owm.get("temp"),       owm.get("feels"),
                    owm.get("humedad"),    owm.get("desc"),
                    owm.get("visibilidad"),owm.get("lluvia_1h"),
                    owm.get("amanecer"),   owm.get("atardecer"),
                ),
            )
            conexion.commit()
            print(f"[BD] - {estado.ts()} ✅ Datos OWM guardados (reporte_id: {nuevo_id})")

        # ------------------------------------------------------------------
        # 4. datos_openmeteo (solo si la fuente respondió)
        # ------------------------------------------------------------------
        aqi = datos_reporte.get("aqi")
        if aqi is not None:
            cursor.execute(
                """INSERT INTO datos_openmeteo (
                       reporte_id,
                       aqi, pm10, pm25, uv_index,
                       co, no2, so2, ozono
                   ) VALUES (
                       %s,
                       %s, %s, %s, %s,
                       %s, %s, %s, %s
                   )""",
                (
                    nuevo_id,
                    aqi.get("aqi"),   aqi.get("pm10"),
                    aqi.get("pm25"),  aqi.get("uv"),
                    aqi.get("co"),    aqi.get("no2"),
                    aqi.get("so2"),   aqi.get("ozono"),
                ),
            )
            conexion.commit()
            print(f"[BD] - {estado.ts()} ✅ Datos Open-Meteo guardados (reporte_id: {nuevo_id})")

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
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        return None

    try:
        cursor = conexion.cursor()
        sql = """
            INSERT INTO condiciones_especiales (
                timestamp_evento, tipo, subtipo, descripcion, ubicacion, latitud, longitud,
                datos_sassla, datos_ssn, datos_investigacion,
                guion_inmediato, prompt_inmediato, modelo_ia_usado
            ) VALUES (
                %(timestamp_evento)s, %(tipo)s, %(subtipo)s, %(descripcion)s, %(ubicacion)s, %(latitud)s, %(longitud)s,
                %(datos_sassla)s, %(datos_ssn)s, %(datos_investigacion)s,
                %(guion_inmediato)s, %(prompt_inmediato)s, %(modelo_ia_usado)s
            )
        """
        cursor.execute(sql, datos_evento)
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