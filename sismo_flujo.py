# sismo_flujo.py — Orquestación del flujo sísmico (alerta + enriquecimiento)
# rev 15.3.1
# rev anterior: rev 15.3.0
# Changelog:
#   15.3.1 — Llamadas a bd.guardar_condicion_especial() actualizadas: datos_sassla →
#            datos_fuente_primaria, datos_ssn → datos_fuente_secundaria; se agrega
#            fuente_alerta="SASSLA". usgs_tsunami incluido en datos_investigacion
#            (faltaba en el INSERT del sismo real). Requiere migration_v17.sql en BD.

import datetime
import json
import os
import subprocess
import time

import bd
import config
import estado
import ia
from sismo_apis import (consultar_ssn_xml, consultar_usgs, consultar_emsc,
                         consultar_gfz, buscar_replicas_ssn)

from sismo_prompts import construir_prompt_sismo_inmediato
from sismo_utils import generar_audio_espera, guardar_datos_locales


def _sintetizar_sismo(texto_guion):
    """
    Sintetiza el guion sísmico directamente a ARCHIVO_SISMO_REPORTE.
    NO toca clima_actual.wav para proteger el reporte meteorológico en curso.
    """
    try:
        with open("_sismo_guion.txt", "w", encoding="utf-8") as f:
            f.write(texto_guion)

        cmd_tts = (
            f"edge-tts --voice {config.VOZ_TTS} "
            f"-f _sismo_guion.txt "
            f"--write-media _sismo_tmp.mp3"
        )
        subprocess.run(cmd_tts, shell=True, stderr=subprocess.DEVNULL)

        if not os.path.exists("_sismo_tmp.mp3"):
            print(f"[SISMO] - {estado.ts()} ❌ edge-tts no generó el MP3 del sismo.")
            return False

        cmd_sox = (
            f"sox '_sismo_tmp.mp3' "
            f"-t wav -r {config.SAMPLE_RATE} -c 1 "
            f"'{config.ARCHIVO_SISMO_REPORTE}'"
        )
        subprocess.run(cmd_sox, shell=True, stderr=subprocess.DEVNULL)

        # Limpieza
        for tmp in ["_sismo_guion.txt", "_sismo_tmp.mp3"]:
            if os.path.exists(tmp):
                os.remove(tmp)

        return os.path.exists(config.ARCHIVO_SISMO_REPORTE)

    except Exception as e:
        print(f"[SISMO] - {estado.ts()} ❌ Error en síntesis sísmica: {e}")
        return False


# ==========================================
#   HELPERS DE FALLBACK MULTI-FUENTE
# ==========================================

def _mag_str(d: dict) -> str:
    """
    Retorna la mejor magnitud disponible como cadena.
    Orden de prioridad: SSN → USGS → 'N/A'.
    """
    m = d.get("ssn_magnitud") or d.get("usgs_magnitud")
    return str(m) if m is not None else "N/A"


def _epi_str(d: dict) -> str:
    """
    Retorna el mejor texto de epicentro disponible.
    Orden de prioridad: epicentro (SASSLA/SSN) → ssn_ubicacion → usgs_ubicacion → 'Desconocido'.
    """
    return (
        d.get("epicentro")
        or d.get("ssn_ubicacion")
        or d.get("usgs_ubicacion")
        or "Desconocido"
    )


def flujo_alerta_sismica():
    """
    Orquesta el flujo cuando se detecta un sismo o simulacro.
    Corre en hilo separado para no bloquear Telethon.

    SIMULACRO: Solo espera a que termine la alarma, guarda en BD, y sale.
    SISMO REAL:
      1. Genera audio de espera (durante la alarma)
      2. Espera a que termine la alarma (alerta_sismica=False)
      3. Espera a que termine la recolección de clima si coincidió
      4. Consulta APIs externas
      5. Genera guion inmediato con IA → sismo_reporte.wav
      6. Guarda localmente + BD
      7. Señala sismo_guion_listo=True para que el DJ entre en intercalado
    """
    estado.sismo_activo = True
    estado.timestamp_sismo = time.time()

    # --- SIMULACRO: flujo simplificado ---
    if estado.sismo_es_simulacro:
        print(f"[SISMO] - {estado.ts()} ⏳ Simulacro: esperando a que termine la alarma...")

        # Esperar a que el DJ termine de reproducir la alarma
        while estado.alerta_sismica:
            time.sleep(0.5)

        # Registrar en BD
        try:
            bd.guardar_condicion_especial({
                "timestamp_evento":      datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tipo":                  "SIMULACRO",
                "subtipo":               "Simulacro programado",
                "descripcion":           "Alarma de simulacro reproducida",
                "ubicacion":             None,
                "latitud":               None,
                "longitud":              None,
                "fuente_alerta":         "SASSLA",
                "datos_fuente_primaria":    json.dumps(estado.datos_sismo or {}),
                "datos_fuente_secundaria":  None,
                "datos_investigacion":   None,
                "guion_inmediato":       None,
                "prompt_inmediato":      None,
                "modelo_ia_usado":       None
            })
        except Exception as e:
            print(f"[SISMO] - {estado.ts()} ⚠️ Error guardando simulacro en BD: {e}")

        # Limpiar estado
        estado.sismo_activo = False
        estado.sismo_es_simulacro = False
        print(f"[SISMO] - {estado.ts()} ✅ Simulacro completado.")
        return

    # --- SISMO REAL: flujo completo ---
    print(f"[SISMO] - {estado.ts()} 🚨 Flujo de sismo REAL iniciado.")

    # 1. Generar audio de espera MIENTRAS la alarma suena (en paralelo)
    generar_audio_espera()

    # 2. Esperar a que el DJ termine de reproducir la alarma
    print(f"[SISMO] - {estado.ts()} ⏳ Esperando fin de la alarma sonora...")
    while estado.alerta_sismica:
        time.sleep(0.5)

    # 3. Esperar a que termine la recolección de clima si coincidió
    if estado.actualizando_clima:
        print(f"[SISMO] - {estado.ts()} ⏳ Recolección de clima en curso. Esperando...")
    while estado.actualizando_clima:
        time.sleep(0.5)

    # 4. Consultar APIs externas
    print(f"[SISMO] - {estado.ts()} 🔍 Consultando APIs sismológicas...")
    _consultar_todas_las_apis()

    # 5. Generar guion inmediato con IA
    prompt_txt = construir_prompt_sismo_inmediato(estado.datos_sismo)
    texto_guion, modelo, err = ia.generar_guion(prompt_txt)

    if texto_guion:
        # Sintetizar directamente a sismo_reporte.wav (NO pisar clima_actual.wav)
        exito = _sintetizar_sismo(texto_guion)
        if exito:
            print(f"[SISMO] - {estado.ts()} ✅ Reporte sísmico inmediato generado: {config.ARCHIVO_SISMO_REPORTE}")
        else:
            print(f"[SISMO] - {estado.ts()} ❌ Falló la síntesis del reporte sísmico.")
    else:
        print(f"[SISMO] - {estado.ts()} ❌ Falló la generación del guion sísmico.")

    # 6. Guardar localmente y en BD
    guardar_datos_locales(estado.datos_sismo)

    id_bd = None
    try:
        # Snapshot del SSN en el momento del INSERT para datos_fuente_secundaria
        datos_ssn_snap = None
        if estado.datos_sismo.get("ssn_magnitud") or estado.datos_sismo.get("epicentro"):
            datos_ssn_snap = json.dumps({
                "magnitud":       estado.datos_sismo.get("ssn_magnitud"),
                "ubicacion":      estado.datos_sismo.get("epicentro"),
                "latitud":        estado.datos_sismo.get("ssn_latitud"),
                "longitud":       estado.datos_sismo.get("ssn_longitud"),
                "profundidad_km": estado.datos_sismo.get("ssn_profundidad_km"),
                "fecha_hora":     estado.datos_sismo.get("hora_evento_sassla"),
            })

        id_bd = bd.guardar_condicion_especial({
            "timestamp_evento":       datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tipo":                   "SISMO",
            "subtipo":                f"Magnitud {_mag_str(estado.datos_sismo)}",
            "descripcion":            f"Epicentro: {_epi_str(estado.datos_sismo)}",
            "ubicacion":              _epi_str(estado.datos_sismo),
            "latitud":                estado.datos_sismo.get("ssn_latitud"),
            "longitud":               estado.datos_sismo.get("ssn_longitud"),
            "fuente_alerta":          "SASSLA",
            "datos_fuente_primaria":  json.dumps(estado.datos_sismo),
            "datos_fuente_secundaria": datos_ssn_snap,
            "datos_investigacion":    json.dumps({
                "usgs_magnitud": estado.datos_sismo.get("usgs_magnitud"),
                "emsc_magnitud": estado.datos_sismo.get("emsc_magnitud"),
                "gfz_magnitud":  estado.datos_sismo.get("gfz_magnitud"),
                "usgs_tsunami":  estado.datos_sismo.get("usgs_tsunami"),
                "replicas":      estado.datos_sismo.get("replicas_detectadas", 0)
            }),
            "guion_inmediato":        texto_guion,
            "prompt_inmediato":       prompt_txt,
            "modelo_ia_usado":        modelo
        })
        # Guardar el ID en estado para que los ciclos de enriquecimiento lo usen con certeza
        if id_bd:
            estado.ultimo_id_sismo_bd = id_bd
    except Exception as e:
        print(f"[SISMO] - {estado.ts()} ⚠️ Error guardando sismo en BD: {e}")

    # 7. Señalar al DJ que el reporte está listo
    estado.sismo_guion_listo = True
    estado.sismo_intercalando = True
    estado.ciclos_sismo_restantes = config.CICLOS_ENRIQUECIMIENTO
    print(f"[SISMO] - {estado.ts()} ✅ Intercalado sismo↔clima activado ({config.CICLOS_ENRIQUECIMIENTO} ciclos de enriquecimiento)")


def enriquecer_con_apis():
    """
    Función pública llamada por noaa_str.py durante los ciclos de clima post-sismo.
    Re-consulta las APIs externas para obtener datos más consolidados.
    Actualiza estado.datos_sismo, el JSON local y la BD con todos los campos definitivos.
    Retorna el dict actualizado.
    """
    if not estado.datos_sismo:
        return None

    ciclo_actual = config.CICLOS_ENRIQUECIMIENTO - estado.ciclos_sismo_restantes + 1
    print(f"[SISMO] - {estado.ts()} 🔍 Re-consultando APIs para enriquecimiento (Ciclo {ciclo_actual}/{config.CICLOS_ENRIQUECIMIENTO})...")
    _consultar_todas_las_apis()
    guardar_datos_locales(estado.datos_sismo)

    # Actualizar BD con ID certífico (guardado en el INSERT inicial)
    id_evento = getattr(estado, "ultimo_id_sismo_bd", None) or _obtener_ultimo_id_evento()
    if not id_evento:
        return estado.datos_sismo

    try:
        # Snapshot del SSN con datos definitivos para datos_fuente_secundaria
        datos_ssn_snap = json.dumps({
            "magnitud":       estado.datos_sismo.get("ssn_magnitud"),
            "ubicacion":      estado.datos_sismo.get("epicentro"),
            "latitud":        estado.datos_sismo.get("ssn_latitud"),
            "longitud":       estado.datos_sismo.get("ssn_longitud"),
            "profundidad_km": estado.datos_sismo.get("ssn_profundidad_km"),
            "fecha_hora":     estado.datos_sismo.get("hora_evento_sassla"),
        })

        datos_actualizados = {
            # Campos descriptivos con los datos definitivos disponibles
            "subtipo":     f"Magnitud {_mag_str(estado.datos_sismo)}",
            "descripcion": f"Epicentro: {_epi_str(estado.datos_sismo)}",
            "ubicacion":   _epi_str(estado.datos_sismo),
            "latitud":     estado.datos_sismo.get("ssn_latitud"),
            "longitud":    estado.datos_sismo.get("ssn_longitud"),
            # Fuente primaria actualizada con el snapshot completo
            "datos_fuente_primaria":   json.dumps(estado.datos_sismo),
            # Fuente secundaria = confirmación definitiva del SSN
            "datos_fuente_secundaria": datos_ssn_snap,
            # Investigación = APIs internacionales consolidadas
            "datos_investigacion":     json.dumps({
                "usgs_magnitud": estado.datos_sismo.get("usgs_magnitud"),
                "emsc_magnitud": estado.datos_sismo.get("emsc_magnitud"),
                "gfz_magnitud":  estado.datos_sismo.get("gfz_magnitud"),
                "usgs_tsunami":  estado.datos_sismo.get("usgs_tsunami"),
                "replicas":      estado.datos_sismo.get("replicas_detectadas", 0)
            }),
        }

        # 1. Registrar entrada histórica para auditoría y trazabilidad
        bd.guardar_historial_condicion_especial(id_evento, datos_actualizados)

        # 2. Actualizar el registro principal para mantener al día los datos del frontend
        bd.actualizar_condicion_especial(id_evento, datos_actualizados)
    except Exception as e:
        print(f"[SISMO] - {estado.ts()} ⚠️ Error actualizando BD en enriquecimiento: {e}")

    return estado.datos_sismo


def _consultar_todas_las_apis():
    """
    Consulta SSN, USGS, EMSC, IRIS y actualiza estado.datos_sismo.

    SSN se consulta primero (3 reintentos internos en sismo_apis).
    - Llamada inmediata (sin hora_ref aún): busca el item mas reciente dentro del margen.
    - Ciclos de enriquecimiento (hora_ref + lat_ref disponibles): busca el evento
      especifico del sismo por proximidad temporal y geografica, evitando confundir
      con replicas u otros eventos posteriores del RSS.
    Las coordenadas lat/lon se toman DESPUES del SSN para que EMSC e IRIS las aprovechen.
    """
    datos = estado.datos_sismo
    hora_str = datos.get("hora_evento_sassla", time.strftime("%Y-%m-%d %H:%M:%S"))

    # Referencias para busqueda dirigida (disponibles cuando ya hay datos SSN/SASSLA)
    hora_ref = datos.get("hora_evento_sassla")
    lat_ref  = datos.get("ssn_latitud")
    lon_ref  = datos.get("ssn_longitud")

    # SSN RSS: primero, para obtener lat/lon y hora definitiva antes que EMSC/IRIS
    datos_ssn = consultar_ssn_xml(
        max_minutos_diff=120,  # ventana amplia para cubrir cualquier ciclo de enriquecimiento
        hora_ref=hora_ref,
        lat_ref=lat_ref,
        lon_ref=lon_ref,
    )
    if datos_ssn:
        if datos_ssn.get("magnitud"):
            datos["ssn_magnitud"] = datos_ssn["magnitud"]
        # Actualizar epicentro con el texto definitivo del SSN (ya incluye estado expandido)
        if datos_ssn.get("ubicacion"):
            datos["epicentro"] = datos_ssn["ubicacion"]
        if datos_ssn.get("fecha_hora"):
            datos["hora_evento_sassla"] = datos_ssn["fecha_hora"]
            hora_str = datos_ssn["fecha_hora"]
        # Guardar coordenadas y profundidad que ahora devuelve el parser del SSN
        if datos_ssn.get("latitud") is not None:
            datos["ssn_latitud"] = datos_ssn["latitud"]
        if datos_ssn.get("longitud") is not None:
            datos["ssn_longitud"] = datos_ssn["longitud"]
        if datos_ssn.get("profundidad_km") is not None:
            datos["ssn_profundidad_km"] = datos_ssn["profundidad_km"]
        print(
            f"[SISMO] - {estado.ts()} \u2139\ufe0f SSN: M{datos_ssn.get('magnitud')} | "
            f"{datos_ssn.get('ubicacion')} | Prof. {datos_ssn.get('profundidad_km')} km"
        )
    else:
        print(f"[SISMO] - {estado.ts()} \u2139\ufe0f SSN: sin datos coincidentes en este momento")

    # Coordenadas obtenidas DESPUES del SSN para aprovechar las actualizadas
    lat = datos.get("ssn_latitud")
    lon = datos.get("ssn_longitud")

    # USGS
    usgs = consultar_usgs(hora_str) or {}
    if usgs.get("magnitud"):
        datos["usgs_magnitud"] = usgs["magnitud"]
        datos["usgs_tsunami"]  = usgs.get("tsunami")
        if usgs.get("ubicacion") and not datos.get("epicentro"):
            datos["epicentro"] = usgs["ubicacion"]
        # Resiliencia: si el SSN está caído, adoptamos las coordenadas de USGS
        if usgs.get("latitud") is not None and datos.get("ssn_latitud") is None:
            datos["ssn_latitud"] = usgs["latitud"]
        if usgs.get("longitud") is not None and datos.get("ssn_longitud") is None:
            datos["ssn_longitud"] = usgs["longitud"]
        if usgs.get("profundidad_km") is not None and datos.get("ssn_profundidad_km") is None:
            datos["ssn_profundidad_km"] = usgs["profundidad_km"]
        print(f"[SISMO] - {estado.ts()} ℹ️ USGS: M{usgs['magnitud']}")

    # Volver a leer coordenadas para que EMSC y GFZ aprovechen las de USGS si el SSN falló
    lat = datos.get("ssn_latitud")
    lon = datos.get("ssn_longitud")

    # EMSC (requiere lat/lon)
    emsc = consultar_emsc(hora_str, lat, lon) or {}
    if emsc.get("magnitud"):
        datos["emsc_magnitud"] = emsc["magnitud"]
        print(f"[SISMO] - {estado.ts()} \u2139\ufe0f EMSC: M{emsc['magnitud']}")

    # GFZ Potsdam — reemplaza a IRIS (HTTP 404 permanente). Requiere lat/lon.
    gfz = consultar_gfz(hora_str, lat, lon) or {}
    if gfz.get("magnitud"):
        datos["gfz_magnitud"] = gfz["magnitud"]
        print(f"[SISMO] - {estado.ts()} ℹ️ GFZ: M{gfz['magnitud']}")


    # Replicas
    if datos.get("hora_evento_sassla"):
        try:
            dt_evento = datetime.datetime.strptime(datos["hora_evento_sassla"], "%Y-%m-%d %H:%M:%S")
            replicas = buscar_replicas_ssn(dt_evento)
            datos["replicas_detectadas"] = len(replicas)
            if replicas:
                print(f"[SISMO] - {estado.ts()} \u2139\ufe0f Replicas detectadas: {len(replicas)}")
        except Exception:
            pass



def _obtener_ultimo_id_evento():
    """Intenta obtener el ID del último evento SISMO en BD dentro de las últimas 3 horas. Retorna None si falla."""
    try:
        conexion = bd.obtener_conexion_bd()
        if conexion:
            cursor = conexion.cursor()
            cursor.execute(
                "SELECT id FROM condiciones_especiales "
                "WHERE tipo = 'SISMO' AND timestamp_evento >= NOW() - INTERVAL 3 HOUR "
                "ORDER BY id DESC LIMIT 1"
            )
            row = cursor.fetchone()
            cursor.close()
            conexion.close()
            return row[0] if row else None
    except Exception:
        pass
    return None