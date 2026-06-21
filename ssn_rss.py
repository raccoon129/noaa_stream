# rev 1.1.0
# Módulo: ssn_rss.py
# Changelog:
#   1.1.0 — Corrección crítica: _parsear_item() reescrito para coincidir con
#            el formato real del RSS del SSN (verificado en vivo 2026-06-19).
#            Formato real:
#              <title>4.0, 17 km al SURESTE de PETATLAN, GRO</title>
#              <description> Fecha:2026-06-19 19:58:33 ... Lat/Lon: X/Y
#                            Profundidad: Z km </description>
#            El formato anterior (M 4.0 + Lat/Long con °) no existe en el feed.
#   1.0.0 — Módulo inicial. Consulta el RSS del Servicio Sismológico Nacional (SSN)
#            y detecta sismos ocurridos en Hidalgo (HGO) con magnitud > 4.0.
#            Implementa deduplicación por clave, cálculo de slots horarios,
#            agrupamiento temporal (60 min) y filtro de antigüedad (35 min).

import datetime
import json
import re
import xml.etree.ElementTree as ET
from typing import Optional

import requests

import bd
import config
import estado


# ==========================================
#   CONSTANTES
# ==========================================

# Ventana de agrupamiento: sismos dentro de este rango se mencionan juntos
_VENTANA_GRUPO_MIN = 60

# Antigüedad máxima de un sismo para ser considerado "nuevo" al arranque o ciclo.
# Si el sismo tiene más de este tiempo, se guarda en BD pero no se menciona.
_MAX_ANTIGUEDAD_MIN = 35

# Número de slots de HORAS_PROGRAMADAS que se incluyen como ventana de mención
_SLOTS_MENCION = 2


# ==========================================
#   PARSEO DEL FEED RSS
# ==========================================

def _parsear_item(item) -> Optional[dict]:
    """
    Extrae los datos de un <item> del RSS del SSN.

    Formato real del feed (verificado en vivo 2026-06-19):

    <title>4.0, 17 km al SURESTE de PETATLAN, GRO </title>
    <description><![CDATA[ <p>Fecha:2026-06-19 19:58:33 (Hora de México)<br/>
    Lat/Lon: 17.415/-101.181<br/>Profundidad: 42.5 km </p> ]]></description>

    Retorna un dict con los campos extraídos, o None si no puede parsear.
    """
    title = item.findtext("title", "").strip()
    desc  = item.findtext("description", "")

    # --- TÍTULO: "4.0, 17 km al SURESTE de PETATLAN, GRO" ---
    m_title = re.match(r"([\d.]+),\s*(.+)", title)
    if not m_title:
        return None

    try:
        magnitud = float(m_title.group(1))
    except ValueError:
        return None

    ubicacion = m_title.group(2).strip()

    # --- DESCRIPTION (CDATA con HTML): extraer fecha, lat/lon, profundidad ---
    # Fecha: "Fecha:2026-06-19 19:58:33"
    m_fecha = re.search(r"Fecha:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})", desc)
    if not m_fecha:
        return None

    fecha_str = m_fecha.group(1)
    hora_str  = m_fecha.group(2)
    try:
        timestamp_evento = datetime.datetime.strptime(
            f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return None

    # Lat/Lon: "Lat/Lon: 17.415/-101.181"
    lat, lon = None, None
    m_coords = re.search(r"Lat/Lon:\s*(-?[\d.]+)/(-?[\d.]+)", desc)
    if m_coords:
        try:
            lat = float(m_coords.group(1))
            lon = float(m_coords.group(2))
        except ValueError:
            pass

    # Profundidad: "Profundidad: 42.5 km"
    prof = None
    m_prof = re.search(r"Profundidad:\s*([\d.]+)\s*km", desc)
    if m_prof:
        try:
            prof = float(m_prof.group(1))
        except ValueError:
            pass

    return {
        "magnitud":         magnitud,
        "fecha_str":        fecha_str,
        "hora_str":         hora_str,
        "timestamp_evento": timestamp_evento,
        "ubicacion":        ubicacion,
        "latitud":          lat,
        "longitud":         lon,
        "profundidad_km":   prof,
        "es_hgo":           "HGO" in ubicacion.upper(),
    }


def _obtener_items_rss() -> list:
    """
    Descarga y parsea el feed RSS del SSN.
    Retorna lista de dicts (uno por <item>), o lista vacía si falla.
    """
    try:
        res = requests.get(config.SSN_RSS_URL, timeout=10)
        if res.status_code != 200:
            print(f"[SSN_RSS] - {estado.ts()} ⚠️  RSS devolvió HTTP {res.status_code}")
            return []
        root = ET.fromstring(res.content)
        items_raw = root.findall(".//item")
        resultado = []
        for item in items_raw:
            parsed = _parsear_item(item)
            if parsed:
                resultado.append(parsed)
        return resultado
    except Exception as e:
        print(f"[SSN_RSS] - {estado.ts()} ⚠️  Error al obtener RSS: {e}")
        return []


# ==========================================
#   FILTRADO Y AGRUPAMIENTO
# ==========================================

def _filtrar_hgo(items: list) -> list:
    """
    De todos los items del RSS, retorna solo los que son de Hidalgo (HGO).
    No aplica filtro de magnitud aquí; se aplicará al detectar el grupo.
    """
    return [i for i in items if i["es_hgo"]]


def _agrupar_por_ventana(items_hgo: list) -> list:
    """
    Agrupa sismos HGO en grupos de hasta _VENTANA_GRUPO_MIN minutos.
    Un grupo se crea cuando hay al menos UN sismo con magnitud > 4.0.
    Sismos en el mismo grupo que no superen 4.0 se incluyen igualmente
    en la mención (son parte del mismo episodio sísmico).

    Retorna lista de grupos; cada grupo es una lista de dicts de sismos.
    Solo se retornan grupos que tengan al menos un sismo > 4.0.
    """
    if not items_hgo:
        return []

    # Ordenar por timestamp ascendente
    ordenados = sorted(items_hgo, key=lambda x: x["timestamp_evento"])

    grupos = []
    grupo_actual = []

    for item in ordenados:
        if not grupo_actual:
            grupo_actual.append(item)
        else:
            ref = grupo_actual[0]["timestamp_evento"]
            delta = abs((item["timestamp_evento"] - ref).total_seconds()) / 60
            if delta <= _VENTANA_GRUPO_MIN:
                grupo_actual.append(item)
            else:
                grupos.append(grupo_actual)
                grupo_actual = [item]

    if grupo_actual:
        grupos.append(grupo_actual)

    # Solo conservar grupos con al menos un sismo > 4.0
    grupos_validos = [g for g in grupos if any(s["magnitud"] > 4.0 for s in g)]
    return grupos_validos


# ==========================================
#   CLAVE DE DEDUPLICACIÓN
# ==========================================

def _clave_grupo(grupo: list) -> str:
    """
    Genera una clave única para un grupo de sismos basándose en el sismo
    de mayor magnitud (o el primero si hay empate).
    Formato: "YYYY-MM-DD HH:MM:SS|ubicacion"
    """
    ancla = max(grupo, key=lambda x: x["magnitud"])
    ts_str = ancla["timestamp_evento"].strftime("%Y-%m-%d %H:%M:%S")
    return f"{ts_str}|{ancla['ubicacion']}"


# ==========================================
#   CÁLCULO DE SLOTS DE MENCIÓN
# ==========================================

def _calcular_slots_mencion(timestamp_sismo: datetime.datetime) -> list:
    """
    Calcula los próximos _SLOTS_MENCION slots de config.HORAS_PROGRAMADAS
    que sean posteriores al timestamp del sismo.

    Retorna una lista de strings "HH:MM" (vacía si no hay suficientes slots).
    """
    hoy = timestamp_sismo.date()
    manana = hoy + datetime.timedelta(days=1)

    # Construir todos los slots del día del sismo + siguiente día como datetime
    candidatos = []
    for hhmm in config.HORAS_PROGRAMADAS:
        try:
            h, m = map(int, hhmm.split(":"))
            # Slot en el mismo día
            dt_hoy = datetime.datetime(hoy.year, hoy.month, hoy.day, h, m)
            candidatos.append(dt_hoy)
            # Slot en el día siguiente (para cubrir medianoche)
            dt_man = datetime.datetime(manana.year, manana.month, manana.day, h, m)
            candidatos.append(dt_man)
        except ValueError:
            continue

    # Filtrar solo los que son estrictamente POSTERIORES al sismo
    posteriores = sorted(
        [c for c in candidatos if c > timestamp_sismo],
        key=lambda x: x,
    )

    # Tomar los primeros _SLOTS_MENCION y convertir a "HH:MM" del día local
    slots = []
    for dt in posteriores[:_SLOTS_MENCION]:
        slots.append(dt.strftime("%H:%M"))

    return slots


# ==========================================
#   ACTUALIZACIÓN DEL ESTADO
# ==========================================

def actualizar_sismos_hgo(conexion_auditoria=None):
    """
    Consulta el RSS del SSN, detecta grupos de sismos nuevos en Hidalgo (HGO)
    con magnitud > 4.0 y actualiza estado.ssn_sismos_activos.

    - Sismos más antiguos que _MAX_ANTIGUEDAD_MIN minutos se descartan
      (no se mencionan, no se guardan en BD).
    - Cada grupo nuevo se guarda una única vez en condiciones_especiales.
    - La deduplicación por clave evita re-registros cuando el sismo
      permanece en el RSS en ciclos sucesivos.
    """
    ahora = datetime.datetime.now()
    items = _obtener_items_rss()
    items_hgo = _filtrar_hgo(items)
    grupos = _agrupar_por_ventana(items_hgo)

    claves_conocidas = {ev["clave"] for ev in estado.ssn_sismos_activos}

    for grupo in grupos:
        clave = _clave_grupo(grupo)

        # --- Deduplicación: ya está en el estado activo ---
        if clave in claves_conocidas:
            continue

        # --- Antigüedad: sismo demasiado viejo para mencionar ---
        ts_ancla = max(grupo, key=lambda x: x["magnitud"])["timestamp_evento"]
        antiguedad_min = (ahora - ts_ancla).total_seconds() / 60
        if antiguedad_min > _MAX_ANTIGUEDAD_MIN:
            print(
                f"[SSN_RSS] - {estado.ts()} ℹ️  Sismo HGO detectado pero ignorado "
                f"(antigüedad: {antiguedad_min:.0f} min > {_MAX_ANTIGUEDAD_MIN} min): "
                f"{clave}"
            )
            continue

        # --- Calcular slots de mención ---
        slots = _calcular_slots_mencion(ts_ancla)
        if not slots:
            print(f"[SSN_RSS] - {estado.ts()} ⚠️  No se pudieron calcular slots para: {clave}")
            continue

        # --- Guardar en BD (una sola vez por grupo) ---
        ancla = max(grupo, key=lambda x: x["magnitud"])
        descripcion_partes = []
        for s in sorted(grupo, key=lambda x: -x["magnitud"]):
            descripcion_partes.append(
                f"M {s['magnitud']} a las {s['hora_str']} — {s['ubicacion']}"
            )
        descripcion = " | ".join(descripcion_partes)

        datos_evento = {
            "timestamp_evento":       ahora.strftime("%Y-%m-%d %H:%M:%S"),
            "tipo":                   "SISMO_SSN_HIDALGO",
            "subtipo":                f"M {ancla['magnitud']}",
            "descripcion":            descripcion,
            "ubicacion":              ancla["ubicacion"],
            "latitud":                ancla["latitud"],
            "longitud":               ancla["longitud"],
            "fuente_alerta":          "SSN_RSS",
            "datos_fuente_primaria":  json.dumps(
                [
                    {
                        "magnitud":       s["magnitud"],
                        "fecha":          s["fecha_str"],
                        "hora":           s["hora_str"],
                        "ubicacion":      s["ubicacion"],
                        "latitud":        s["latitud"],
                        "longitud":       s["longitud"],
                        "profundidad_km": s["profundidad_km"],
                    }
                    for s in grupo
                ],
                ensure_ascii=False,
            ),
            "datos_fuente_secundaria": None,
            "datos_investigacion":     None,
            "guion_inmediato":         None,
            "prompt_inmediato":        None,
            "guion_analisis":          None,
            "prompt_analisis":         None,
            "modelo_ia_usado":         None,
        }
        bd_id = bd.guardar_condicion_especial(datos_evento)
        print(
            f"[SSN_RSS] - {estado.ts()} ✅ Sismo HGO registrado en BD "
            f"(ID: {bd_id}): {descripcion} | Slots: {slots}"
        )

        # --- Añadir al estado activo ---
        estado.ssn_sismos_activos.append({
            "clave":         clave,
            "bd_id":         bd_id,
            "grupo":         grupo,
            "slots_mencion": slots,
        })


# ==========================================
#   OBTENER EVENTOS PARA EL REPORTE ACTUAL
# ==========================================

def obtener_eventos_para_reporte(hora_exacta: str) -> list:
    """
    Evalúa estado.ssn_sismos_activos y retorna la lista de grupos que deben
    mencionarse en el reporte de la hora hora_exacta ("HH:MM").

    Reglas de slot:
    - Si hora_exacta == slot_actual → incluir evento, consumir slot.
    - Si hora_exacta > slot_actual (slot expirado/perdido) → descartar slot sin mencionar.
    - Si hora_exacta < slot_actual → aún no es el momento, no incluir.

    Después de procesar, elimina del estado los eventos sin slots pendientes.
    """
    try:
        ahora_min = _hhmm_a_minutos(hora_exacta)
    except ValueError:
        return []

    eventos_para_reporte = []
    nuevos_activos = []

    for evento in estado.ssn_sismos_activos:
        slots = list(evento["slots_mencion"])  # copia mutable

        # Procesar todos los slots que ya llegaron (o pasaron)
        incluir = False
        slots_pendientes = []
        for slot in slots:
            try:
                slot_min = _hhmm_a_minutos(slot)
            except ValueError:
                continue  # slot malformado → descartar

            if ahora_min >= slot_min:
                if ahora_min == slot_min:
                    # Slot actual → incluir y consumir
                    incluir = True
                # Si ahora_min > slot_min → expirado → descartar sin incluir
            else:
                # Slot futuro → conservar
                slots_pendientes.append(slot)

        evento["slots_mencion"] = slots_pendientes

        if incluir:
            eventos_para_reporte.append(evento)

        # Conservar en el estado si aún hay slots futuros pendientes
        if slots_pendientes:
            nuevos_activos.append(evento)
        # Si slots_pendientes está vacío:
        #   - incluir=True  → último slot consumido, evento termina
        #   - incluir=False → todos los slots expiraron, evento termina

    estado.ssn_sismos_activos = nuevos_activos
    return eventos_para_reporte


# ==========================================
#   UTILIDAD INTERNA
# ==========================================

def _hhmm_a_minutos(hhmm: str) -> int:
    """Convierte 'HH:MM' a minutos desde medianoche. Lanza ValueError si malformado."""
    partes = hhmm.split(":")
    if len(partes) != 2:
        raise ValueError(f"Formato HH:MM inválido: {hhmm}")
    return int(partes[0]) * 60 + int(partes[1])
