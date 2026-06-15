# sismo.py — Punto de entrada: Monitor Telethon SASSLA + Simulacros locales
# rev 15.3.0
# Changelog:
#   15.3.0 — Refactorización modular: lógica dividida en sismo_regex, sismo_apis,
#            sismo_prompts, sismo_utils y sismo_flujo. Este archivo solo contiene
#            el monitor Telethon y el hilo de simulacros locales.
#            Simulacros simplificados: solo reproducen alarma, sin reporte.
#            Evaluación de simulacros usa caché RAM (1 lectura de disco/día).

import asyncio
import datetime
import json
import os
import threading
import time

from telethon import TelegramClient, events

import config
import estado
from sismo_regex import (REGEX_ALERTA, REGEX_EFECTOS, REGEX_DETECTADO, REGEX_TIEMPOS,
                          REGEX_SSN, REGEX_SSN_SASSLA, REGEX_SIMULACRO, REGEX_CIUDAD,
                          REGEX_RESUMEN, REGEX_RESUMEN_CDMX,
                          ESCALA_INTENSIDAD, CIUDADES_SASSLA)


# Tabla de abreviaturas SSN → nombre completo del estado
_ESTADOS_MX = {
    "AGS": "Aguascalientes",
    "BC":  "Baja California",
    "BCS": "Baja California Sur",
    "CAM": "Campeche",
    "CHIS": "Chiapas",
    "CHIH": "Chihuahua",
    "COAH": "Coahuila",
    "COL": "Colima",
    "CDMX": "Ciudad de México",
    "DGO": "Durango",
    "GTO": "Guanajuato",
    "GRO": "Guerrero",
    "HGO": "Hidalgo",
    "JAL": "Jalisco",
    "MEX": "Estado de México",
    "MICH": "Michoacán",
    "MOR": "Morelos",
    "NAY": "Nayarit",
    "NL":  "Nuevo León",
    "OAX": "Oaxaca",
    "PUE": "Puebla",
    "QRO": "Querétaro",
    "QROO": "Quintana Roo",
    "SLP": "San Luis Potosí",
    "SIN": "Sinaloa",
    "SON": "Sonora",
    "TAB": "Tabasco",
    "TAMS": "Tamaulipas",
    "TLAX": "Tlaxcala",
    "VER": "Veracruz",
    "YUC": "Yucatán",
    "ZAC": "Zacatecas",
}
from sismo_flujo import flujo_alerta_sismica

# Re-exportar para que noaa_str.py pueda hacer sismo.enriquecer_con_apis()
from sismo_flujo import enriquecer_con_apis  # noqa: F401


# ==========================================
#   CACHÉ DE SIMULACROS (RAM)
# ==========================================

_cache_simulacros_hoy = []
_cache_simulacros_fecha = None


def _cargar_cache_simulacros():
    """Lee simulacros.json UNA vez al día y cachea las horas del día en RAM."""
    global _cache_simulacros_hoy, _cache_simulacros_fecha
    ahora = datetime.datetime.now()
    fecha_actual = ahora.date()

    if fecha_actual != _cache_simulacros_fecha:
        _cache_simulacros_fecha = fecha_actual
        _cache_simulacros_hoy = []

        if os.path.exists(config.ARCHIVO_SIMULACROS):
            try:
                with open(config.ARCHIVO_SIMULACROS, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    hoy_str = ahora.strftime("%Y-%m-%d")
                    for fecha_str in data.get("fechas_simulacro", []):
                        if fecha_str.startswith(hoy_str):
                            partes = fecha_str.split(" ")
                            if len(partes) == 2:
                                _cache_simulacros_hoy.append(partes[1])
                if _cache_simulacros_hoy:
                    print(f"[SISMO] - {estado.ts()} ℹ️ Simulacros programados hoy: {_cache_simulacros_hoy}")
            except Exception:
                pass


# ==========================================
#   EVALUADORES
# ==========================================

def _evaluar_simulacro(texto):
    """Determina si un evento es simulacro. Usa caché RAM, NO lee disco."""
    # 1. El mensaje de SASSLA dice explícitamente que es simulacro
    if REGEX_SIMULACRO.search(texto):
        return True

    # 2. Verificar si la hora actual coincide con un simulacro programado (±15 min)
    ahora = datetime.datetime.now()
    hora_actual_min = ahora.hour * 60 + ahora.minute
    for hora_str in _cache_simulacros_hoy:
        try:
            partes = hora_str.split(":")
            hora_sim_min = int(partes[0]) * 60 + int(partes[1])
            if abs(hora_actual_min - hora_sim_min) <= 15:
                return True
        except (ValueError, IndexError):
            pass

    return False


def _evaluar_activacion(texto_efectos):
    """
    Determina si el sismo es perceptible en CDMX o TOL (nivel > IMPERCEPTIBLE).
    Usada antes de activar la alerta para filtrar sismos imperceptibles localmente.
    """
    cdmx_nivel = 0
    tol_nivel = 0

    for linea in texto_efectos.split('\n'):
        m = REGEX_CIUDAD.search(linea)
        if m:
            ciudad, intensidad = m.groups()
            nivel = ESCALA_INTENSIDAD.get(intensidad.upper(), 0)
            if ciudad.upper() == 'CDMX':
                cdmx_nivel = nivel
            if ciudad.upper() == 'TOL':
                tol_nivel = nivel

    return cdmx_nivel > 1 or tol_nivel > 1


def _extraer_datos(texto, datos_dict):
    """
    Extrae datos de un mensaje SASSLA y los acumula en datos_dict.
    - Ignora mensajes de "Tiempo Estimado de Llegada" (datos inmediatos sin valor posterior).
    - Para mensajes de "Efectos esperados": captura TODAS las ciudades reportadas.
      Si una ciudad ya tenía intensidad, conserva la más alta entre los mensajes recibidos.
    - Para mensajes de epicentro y SSN: actualiza los campos correspondientes.
    """
    # Ignorar explícitamente los mensajes de tiempos estimados (desfasados de inmediato)
    if REGEX_TIEMPOS.search(texto):
        return

    # Efectos esperados por ciudad
    if REGEX_EFECTOS.search(texto):
        if "intensidades_sassla" not in datos_dict:
            datos_dict["intensidades_sassla"] = {}

        for linea in texto.split('\n'):
            m = REGEX_CIUDAD.search(linea)
            if m:
                ciudad_abr, intensidad = m.groups()
                ciudad_abr = ciudad_abr.upper()
                intensidad = intensidad.upper()
                nivel_nuevo = ESCALA_INTENSIDAD.get(intensidad, 0)

                # Ignorar la intensidad "--" (sin dato)
                if nivel_nuevo == 0:
                    continue

                nivel_prev = ESCALA_INTENSIDAD.get(
                    datos_dict["intensidades_sassla"].get(ciudad_abr, "--"), 0
                )
                # Conservar la intensidad más alta reportada entre múltiples mensajes
                if nivel_nuevo > nivel_prev:
                    datos_dict["intensidades_sassla"][ciudad_abr] = intensidad

        # Retrocompatibilidad: mantener los campos planos de CDMX y TOL
        datos_dict["intensidad_cdmx"] = datos_dict["intensidades_sassla"].get("CDMX", "IMPERCEPTIBLE")
        datos_dict["intensidad_tol"]  = datos_dict["intensidades_sassla"].get("TOL", "IMPERCEPTIBLE")

    # Epicentro preliminar
    m_epi = REGEX_DETECTADO.search(texto)
    if m_epi:
        datos_dict["epicentro"] = m_epi.group(1).strip()

    # SSN formato raw (con lat/lon — llega directamente del SSN vía Telethon)
    m_ssn = REGEX_SSN.search(texto)
    if m_ssn:
        mag, loc, edo, fecha, hora, lat, lon, pf = m_ssn.groups()
        datos_dict["ssn_magnitud"] = float(mag)
        edo_completo = _ESTADOS_MX.get(edo.upper().strip(), edo)
        datos_dict["ssn_ubicacion"] = f"{loc}, {edo_completo}"
        if not datos_dict.get("epicentro"):
            datos_dict["epicentro"] = datos_dict["ssn_ubicacion"]
        datos_dict["ssn_latitud"] = float(lat)
        datos_dict["ssn_longitud"] = float(lon)
        datos_dict["hora_evento_sassla"] = f"20{fecha[-2:]}-{fecha[3:5]}-{fecha[0:2]} {hora}"

    # SSN formato SASSLA-relay (sin lat/lon — SASSLA lo publica en su propio formato narrativo)
    # Ej: "Preliminar: Magnitud 5.3, 26 km al SUROESTE de SAN MARCOS, GRO."
    # Ej: "Magnitud final 5.2, 25 km al OESTE de San Marcos, Guerrero."
    # Solo se captura la magnitud; el resto (epicentro, coordenadas) viene del SSN RSS.
    m_ssn_relay = REGEX_SSN_SASSLA.search(texto)
    if m_ssn_relay and not m_ssn:  # No sobreescribir si ya procesó el raw
        mag_relay, loc_relay = m_ssn_relay.groups()
        try:
            mag_val = float(mag_relay)
            # Solo actualizar si es la primera vez o si es el dato definitivo ("Magnitud final")
            es_final = "final" in texto.lower()
            if not datos_dict.get("ssn_magnitud") or es_final:
                datos_dict["ssn_magnitud"] = mag_val
        except ValueError:
            pass

    # Resumen post-evento de SASSLA
    # Ej: "Se registró #sismo de intensidad FUERTE en Guerrero Costa Central."
    # Ej: "Se estimó efecto MODERADO para la #CDMX."
    m_resumen = REGEX_RESUMEN.search(texto)
    if m_resumen:
        intensidad_zona, zona = m_resumen.groups()
        datos_dict["sassla_resumen_intensidad"] = intensidad_zona.upper()
        datos_dict["sassla_resumen_zona"]        = zona.strip()
    m_resumen_cdmx = REGEX_RESUMEN_CDMX.search(texto)
    if m_resumen_cdmx:
        efecto_cdmx = m_resumen_cdmx.group(1).upper()
        # Actualizar la intensidad de CDMX si este resumen tiene dato más reciente
        if "intensidades_sassla" not in datos_dict:
            datos_dict["intensidades_sassla"] = {}
        nivel_resumen = ESCALA_INTENSIDAD.get(efecto_cdmx, 0)
        nivel_prev    = ESCALA_INTENSIDAD.get(datos_dict["intensidades_sassla"].get("CDMX", "--"), 0)
        if nivel_resumen > nivel_prev:
            datos_dict["intensidades_sassla"]["CDMX"] = efecto_cdmx
            datos_dict["intensidad_cdmx"] = efecto_cdmx


# ==========================================
#   MONITOR TELETHON (SASSLA)
# ==========================================

def iniciar_monitor():
    """Punto de entrada para lanzar Telethon + simulacros locales en hilos background."""
    if not config.TELEGRAM_API_ID or config.TELEGRAM_API_HASH == "PENDIENTE":
        print(f"[SISMO] - {estado.ts()} ⚠️  Credenciales de Telegram no configuradas. Monitor SASSLA apagado.")
        # Aun así lanzar el hilo de simulacros locales
        _iniciar_hilo_simulacros()
        return

    # Cargar caché de simulacros al arranque
    _cargar_cache_simulacros()

    def _loop_telethon():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        client = TelegramClient('sesion_noaa', config.TELEGRAM_API_ID, config.TELEGRAM_API_HASH, loop=loop)

        @client.on(events.NewMessage(chats=config.TELEGRAM_CANAL))
        async def handler(event):
            texto = event.raw_text

            # Acumular datos silenciosamente si ya hay un evento activo
            if estado.alerta_sismica or estado.sismo_activo:
                if estado.datos_sismo is not None:
                    _extraer_datos(texto, estado.datos_sismo)
                return

            # Trigger primario: alerta o detección
            if REGEX_ALERTA.search(texto) or REGEX_DETECTADO.search(texto):
                es_simulacro = _evaluar_simulacro(texto)

                # Simulacro confirmado por SASSLA → activar de inmediato
                if es_simulacro:
                    print(f"[SISMO] - {estado.ts()} 🚨 ¡¡¡SIMULACRO DETECTADO POR SASSLA!!! 🚨")
                    estado.datos_sismo = {}
                    _extraer_datos(texto, estado.datos_sismo)

                    # Simulacro NO espera a que termine el clima; la alarma suena de inmediato
                    estado.alerta_sismica = True
                    estado.sismo_es_simulacro = True
                    threading.Thread(target=flujo_alerta_sismica, daemon=True).start()
                    return

            # Trigger con filtro de intensidad (sismos reales)
            if REGEX_EFECTOS.search(texto):
                es_simulacro = _evaluar_simulacro(texto)

                if not es_simulacro and not _evaluar_activacion(texto):
                    print(f"[SISMO] - {estado.ts()} ℹ️ Sismo IMPERCEPTIBLE en CDMX/TOL. Ignorando.")
                    return

                # ACTIVAR
                tipo = "SIMULACRO" if es_simulacro else "SISMO"
                print(f"[SISMO] - {estado.ts()} 🚨 ¡¡¡ALERTA {tipo} SASSLA!!! 🚨")
                estado.datos_sismo = {}
                _extraer_datos(texto, estado.datos_sismo)

                estado.alerta_sismica = True
                estado.sismo_es_simulacro = es_simulacro
                threading.Thread(target=flujo_alerta_sismica, daemon=True).start()

        print(f"[SISMO] - {estado.ts()} ✅ Monitor SASSLA iniciado (Telethon). Esperando eventos...")
        client.start()
        client.run_until_disconnected()

    # Hilo Telethon
    t = threading.Thread(target=_loop_telethon, daemon=True)
    t.start()

    # Hilo simulacros locales
    _iniciar_hilo_simulacros()


def _iniciar_hilo_simulacros():
    """Lanza el hilo autónomo de simulacros programados."""

    def _loop_simulacros_locales():
        simulacros_ejecutados = set()

        while True:
            try:
                # Recargar caché si cambió el día
                _cargar_cache_simulacros()

                if _cache_simulacros_hoy and not estado.alerta_sismica and not estado.sismo_activo:
                    hora_actual_str = datetime.datetime.now().strftime("%H:%M")

                    if hora_actual_str in _cache_simulacros_hoy and hora_actual_str not in simulacros_ejecutados:
                        simulacros_ejecutados.add(hora_actual_str)
                        print(f"\n[SISMO] - {estado.ts()} 🚨 ¡¡¡SIMULACRO LOCAL PROGRAMADO ({hora_actual_str})!!! 🚨")
                        estado.datos_sismo = {}
                        estado.alerta_sismica = True
                        estado.sismo_es_simulacro = True
                        threading.Thread(target=flujo_alerta_sismica, daemon=True).start()

                # Reset ejecutados si cambió el día
                if datetime.datetime.now().date() != _cache_simulacros_fecha:
                    simulacros_ejecutados = set()

            except Exception:
                pass

            # Sincronización tipo Cron: dormir hasta el próximo minuto :00
            segundos_restantes = 60 - datetime.datetime.now().second
            time.sleep(segundos_restantes)

    t_sim = threading.Thread(target=_loop_simulacros_locales, daemon=True)
    t_sim.start()
