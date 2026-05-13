# sismo_flujo.py — Orquestación del flujo sísmico (alerta + enriquecimiento)

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
                         consultar_iris, buscar_replicas_ssn)
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
                "timestamp_evento": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tipo": "SIMULACRO",
                "subtipo": "Simulacro programado",
                "descripcion": "Alarma de simulacro reproducida",
                "ubicacion": None,
                "latitud": None,
                "longitud": None,
                "datos_sassla": json.dumps(estado.datos_sismo or {}),
                "datos_ssn": None,
                "datos_investigacion": None,
                "guion_inmediato": None,
                "prompt_inmediato": None,
                "modelo_ia_usado": None
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
        id_bd = bd.guardar_condicion_especial({
            "timestamp_evento": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "tipo": "SISMO",
            "subtipo": f"Magnitud {estado.datos_sismo.get('ssn_magnitud', 'N/A')}",
            "descripcion": f"Epicentro: {estado.datos_sismo.get('epicentro', 'Desconocido')}",
            "ubicacion": estado.datos_sismo.get("epicentro"),
            "latitud": estado.datos_sismo.get("ssn_latitud"),
            "longitud": estado.datos_sismo.get("ssn_longitud"),
            "datos_sassla": json.dumps(estado.datos_sismo),
            "datos_ssn": None,
            "datos_investigacion": json.dumps({
                "usgs_magnitud": estado.datos_sismo.get("usgs_magnitud"),
                "emsc_magnitud": estado.datos_sismo.get("emsc_magnitud"),
                "iris_magnitud": estado.datos_sismo.get("iris_magnitud"),
                "replicas": estado.datos_sismo.get("replicas_detectadas", 0)
            }),
            "guion_inmediato": texto_guion,
            "prompt_inmediato": prompt_txt,
            "modelo_ia_usado": modelo
        })
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
    Actualiza estado.datos_sismo y el JSON local.
    Retorna el dict actualizado.
    """
    if not estado.datos_sismo:
        return None

    print(f"[SISMO] - {estado.ts()} 🔍 Re-consultando APIs para enriquecimiento...")
    _consultar_todas_las_apis()
    guardar_datos_locales(estado.datos_sismo)

    # Actualizar BD si tenemos datos nuevos
    try:
        bd.actualizar_condicion_especial(
            _obtener_ultimo_id_evento(),
            {"datos_investigacion": json.dumps({
                "usgs_magnitud": estado.datos_sismo.get("usgs_magnitud"),
                "emsc_magnitud": estado.datos_sismo.get("emsc_magnitud"),
                "iris_magnitud": estado.datos_sismo.get("iris_magnitud"),
                "usgs_tsunami": estado.datos_sismo.get("usgs_tsunami"),
                "replicas": estado.datos_sismo.get("replicas_detectadas", 0)
            })}
        )
    except Exception:
        pass

    return estado.datos_sismo


def _consultar_todas_las_apis():
    """Consulta SSN, USGS, EMSC, IRIS y actualiza estado.datos_sismo."""
    datos = estado.datos_sismo
    hora_str = datos.get("hora_evento_sassla", time.strftime("%Y-%m-%d %H:%M:%S"))
    lat = datos.get("ssn_latitud")
    lon = datos.get("ssn_longitud")

    # SSN RSS
    datos_ssn = consultar_ssn_xml(max_minutos_diff=60)
    if datos_ssn:
        if datos_ssn.get("magnitud"):
            datos["ssn_magnitud"] = datos_ssn["magnitud"]
        if not datos.get("epicentro") and datos_ssn.get("ubicacion"):
            datos["epicentro"] = datos_ssn["ubicacion"]
        if datos_ssn.get("fecha_hora"):
            datos["hora_evento_sassla"] = datos_ssn["fecha_hora"]
            hora_str = datos_ssn["fecha_hora"]
        print(f"[SISMO] - {estado.ts()} ℹ️ SSN: M{datos_ssn.get('magnitud')}")

    # USGS
    usgs = consultar_usgs(hora_str) or {}
    if usgs.get("magnitud"):
        datos["usgs_magnitud"] = usgs["magnitud"]
        datos["usgs_tsunami"] = usgs.get("tsunami")
        print(f"[SISMO] - {estado.ts()} ℹ️ USGS: M{usgs['magnitud']}")

    # EMSC
    emsc = consultar_emsc(hora_str, lat, lon) or {}
    if emsc.get("magnitud"):
        datos["emsc_magnitud"] = emsc["magnitud"]
        print(f"[SISMO] - {estado.ts()} ℹ️ EMSC: M{emsc['magnitud']}")

    # IRIS
    iris = consultar_iris(hora_str, lat, lon) or {}
    if iris.get("magnitud"):
        datos["iris_magnitud"] = iris["magnitud"]
        print(f"[SISMO] - {estado.ts()} ℹ️ IRIS: M{iris['magnitud']}")

    # Réplicas
    if datos.get("hora_evento_sassla"):
        try:
            dt_evento = datetime.datetime.strptime(datos["hora_evento_sassla"], "%Y-%m-%d %H:%M:%S")
            replicas = buscar_replicas_ssn(dt_evento)
            datos["replicas_detectadas"] = len(replicas)
            if replicas:
                print(f"[SISMO] - {estado.ts()} ℹ️ Réplicas detectadas: {len(replicas)}")
        except Exception:
            pass


def _obtener_ultimo_id_evento():
    """Intenta obtener el ID del último evento en BD. Retorna None si falla."""
    try:
        conexion = bd.obtener_conexion_bd()
        if conexion:
            cursor = conexion.cursor()
            cursor.execute("SELECT id FROM condiciones_especiales ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            cursor.close()
            conexion.close()
            return row[0] if row else None
    except Exception:
        pass
    return None
