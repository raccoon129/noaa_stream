# rev 15.0.0
# rev anterior: monolito noaa_estable.py rev 14.9.2
# Changelog:
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
    Inserta el reporte climatológico completo en la base de datos.
    Retorna el ID del registro insertado, o None si falló.
    """
    conexion = obtener_conexion_bd()
    if not conexion:
        print(f"[BD] - {estado.ts()} ⚠️  Reporte NO guardado (sin conexión).")
        return None

    try:
        cursor = conexion.cursor()

        sql = """
            INSERT INTO reportes_climatologicos (
                fecha_reporte, hora_reporte, timestamp_completo, ciudad,

                cna_disponible, cna_condicion,
                cna_temp_max, cna_temp_min,
                cna_prob_lluvia, cna_precipitacion,
                cna_viento, cna_dir_viento, cna_rafagas,
                cna_man_condicion, cna_man_temp_max, cna_man_temp_min,

                owm_disponible, owm_temp_actual, owm_sensacion,
                owm_humedad, owm_condicion, owm_visibilidad,
                owm_lluvia_1h, owm_amanecer, owm_atardecer,

                aqm_disponible, aqm_aqi, aqm_pm10, aqm_pm25,
                aqm_uv_index, aqm_co, aqm_no2, aqm_so2, aqm_ozono,

                guion_texto, modelo_ia_usado, guion_generado
            ) VALUES (
                %(fecha_reporte)s, %(hora_reporte)s, %(timestamp_completo)s, %(ciudad)s,

                %(cna_disponible)s, %(cna_condicion)s,
                %(cna_temp_max)s, %(cna_temp_min)s,
                %(cna_prob_lluvia)s, %(cna_precipitacion)s,
                %(cna_viento)s, %(cna_dir_viento)s, %(cna_rafagas)s,
                %(cna_man_condicion)s, %(cna_man_temp_max)s, %(cna_man_temp_min)s,

                %(owm_disponible)s, %(owm_temp_actual)s, %(owm_sensacion)s,
                %(owm_humedad)s, %(owm_condicion)s, %(owm_visibilidad)s,
                %(owm_lluvia_1h)s, %(owm_amanecer)s, %(owm_atardecer)s,

                %(aqm_disponible)s, %(aqm_aqi)s, %(aqm_pm10)s, %(aqm_pm25)s,
                %(aqm_uv_index)s, %(aqm_co)s, %(aqm_no2)s, %(aqm_so2)s, %(aqm_ozono)s,

                %(guion_texto)s, %(modelo_ia_usado)s, %(guion_generado)s
            )
        """

        cursor.execute(sql, datos_reporte)
        conexion.commit()
        nuevo_id = cursor.lastrowid
        cursor.close()
        print(f"[BD] - {estado.ts()} ✅ Reporte guardado en historial (ID: {nuevo_id})")
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
