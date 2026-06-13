# sismo_apis.py — Consultas a APIs sismológicas (SSN, USGS, EMSC, IRIS)
# rev 15.3.2
# Changelog:
#   15.3.2 — consultar_ssn_xml() reescrito:
#            - 3 reintentos con 3 s de espera (SSN se satura con frecuencia).
#            - Coordenadas obtenidas de <geo:lat>/<geo:long> (más fiables que la URL).
#            - Profundidad extraída del bloque CDATA de <description>.
#            - Ubicación extraída del <title> (formato "M, descripción").
#            - Abreviaturas de estado expandidas al nombre completo.
#            - Nuevo parámetro hora_ref/lat_ref/lon_ref: en los ciclos de
#              enriquecimiento busca el evento más cercano al registrado en lugar
#              de devolver siempre el ítem más reciente.
#            buscar_replicas_ssn() también usa _fetch_ssn_root() con reintentos.

import datetime
import re
import time
import xml.etree.ElementTree as ET

import requests

import config
import estado

# Namespace del estándar geo del SSN
_GEO_NS = "http://www.w3.org/2003/01/geo/wgs84_pos#"

# Abreviaturas SSN → nombre completo del estado
_ESTADOS_MX = {
    "AGS":  "Aguascalientes",
    "BC":   "Baja California",
    "BCS":  "Baja California Sur",
    "CAM":  "Campeche",
    "CHIS": "Chiapas",
    "CHIH": "Chihuahua",
    "COAH": "Coahuila",
    "COL":  "Colima",
    "CDMX": "Ciudad de México",
    "DGO":  "Durango",
    "GTO":  "Guanajuato",
    "GRO":  "Guerrero",
    "HGO":  "Hidalgo",
    "JAL":  "Jalisco",
    "MEX":  "Estado de México",
    "MICH": "Michoacán",
    "MOR":  "Morelos",
    "NAY":  "Nayarit",
    "NL":   "Nuevo León",
    "OAX":  "Oaxaca",
    "PUE":  "Puebla",
    "QRO":  "Querétaro",
    "QROO": "Quintana Roo",
    "SLP":  "San Luis Potosí",
    "SIN":  "Sinaloa",
    "SON":  "Sonora",
    "TAB":  "Tabasco",
    "TAMS": "Tamaulipas",
    "TLAX": "Tlaxcala",
    "VER":  "Veracruz",
    "YUC":  "Yucatán",
    "ZAC":  "Zacatecas",
}


def _expandir_estado(abrev: str) -> str:
    """Convierte la abreviatura del estado al nombre completo si existe en la tabla."""
    return _ESTADOS_MX.get(abrev.upper().strip(), abrev)


def _fetch_ssn_root(max_intentos=3, pausa_s=3):
    """
    Descarga el RSS del SSN con hasta max_intentos reintentos.
    Retorna el ElementTree root o None si todos los intentos fallan.
    """
    for intento in range(1, max_intentos + 1):
        try:
            r = requests.get(config.SSN_RSS_URL, timeout=10)
            if r.status_code == 200:
                return ET.fromstring(r.content)
            print(f"[SISMO] ⚠️ SSN intento {intento}/{max_intentos}: HTTP {r.status_code}")
        except Exception as e:
            print(f"[SISMO] ⚠️ SSN intento {intento}/{max_intentos}: {e}")
        if intento < max_intentos:
            time.sleep(pausa_s)
    return None


def _parsear_items_ssn(root):
    """
    Parsea todos los <item> del RSS del SSN y devuelve una lista de dicts con:
      magnitud, ubicacion (texto completo con estado expandido), profundidad_km,
      fecha_hora (str), dt (datetime), latitud, longitud.
    """
    resultados = []
    for item in root.findall("./channel/item"):
        # ── Título: "5.2, 25 km al OESTE de SAN MARCOS, GRO "
        title_el = item.find("title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        mag = None
        ubicacion = ""
        m_title = re.match(r"^([\d.]+),\s*(.+)$", title)
        if m_title:
            try:
                mag = float(m_title.group(1))
            except ValueError:
                pass
            ubicacion_raw = m_title.group(2).strip()
            # Expandir abreviatura del estado (último token separado por coma)
            partes = ubicacion_raw.rsplit(",", 1)
            if len(partes) == 2:
                loc_lugar = partes[0].strip()
                edo_abrev = partes[1].strip()
                ubicacion = f"{loc_lugar}, {_expandir_estado(edo_abrev)}"
            else:
                ubicacion = ubicacion_raw

        # ── Description (CDATA): "Fecha:2026-06-13 12:20:45 ... Profundidad: 10.0 km"
        desc_el = item.find("description")
        desc = desc_el.text if desc_el is not None and desc_el.text else ""

        dt_evento = None
        m_fecha = re.search(r"Fecha:(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", desc)
        if m_fecha:
            try:
                dt_evento = datetime.datetime.strptime(m_fecha.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        profundidad = None
        m_prf = re.search(r"Profundidad:\s*([\d.]+)\s*km", desc)
        if m_prf:
            try:
                profundidad = float(m_prf.group(1))
            except ValueError:
                pass

        # ── Coordenadas desde <geo:lat> / <geo:long> (más fiables que la URL)
        lat_el = item.find(f"{{{_GEO_NS}}}lat")
        lon_el = item.find(f"{{{_GEO_NS}}}long")
        lat = None
        lon = None
        if lat_el is not None and lat_el.text:
            try:
                lat = float(lat_el.text.strip())
            except ValueError:
                pass
        if lon_el is not None and lon_el.text:
            try:
                lon = float(lon_el.text.strip())
            except ValueError:
                pass

        resultados.append({
            "magnitud":       mag,
            "ubicacion":      ubicacion,
            "profundidad_km": profundidad,
            "fecha_hora":     dt_evento.strftime("%Y-%m-%d %H:%M:%S") if dt_evento else None,
            "dt":             dt_evento,
            "latitud":        lat,
            "longitud":       lon,
        })

    return resultados


def consultar_ssn_xml(max_minutos_diff=5, hora_ref=None, lat_ref=None, lon_ref=None):
    """
    Descarga el RSS del SSN (3 intentos) y localiza el evento relevante.

    Modos de búsqueda:
      - Sin referencias (hora_ref/lat_ref/lon_ref ausentes):
          Devuelve el ítem más reciente si ocurrió dentro de max_minutos_diff.
          Útil para la consulta inmediata post-alarma.
      - Con referencias:
          Busca en TODOS los ítems el evento más cercano al evento registrado
          (por tiempo y/o posición geográfica). max_minutos_diff actúa como
          ventana máxima de tolerancia temporal.
          Útil para los ciclos de enriquecimiento donde el SSN ya habrá
          publicado el evento con datos definitivos.

    Retorna dict con: magnitud, ubicacion, profundidad_km, fecha_hora,
                      latitud, longitud — o None si no se encuentra.
    """
    root = _fetch_ssn_root()
    if root is None:
        return None

    items = _parsear_items_ssn(root)
    if not items:
        return None

    # ── Modo referencia: buscar el evento más cercano al registrado
    if hora_ref or (lat_ref is not None and lon_ref is not None):
        dt_ref = None
        if hora_ref:
            try:
                dt_ref = datetime.datetime.strptime(hora_ref, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass

        mejor = None
        mejor_score = float("inf")

        for c in items:
            # Filtro temporal: descartar eventos demasiado alejados
            if dt_ref and c["dt"]:
                diff_min = abs((c["dt"] - dt_ref).total_seconds()) / 60
                if diff_min > max_minutos_diff:
                    continue
                score = diff_min
            elif dt_ref and not c["dt"]:
                continue
            else:
                score = 0

            # Peso geográfico (si tenemos coordenadas de referencia)
            if lat_ref is not None and lon_ref is not None and c["latitud"] and c["longitud"]:
                dist = ((c["latitud"] - lat_ref) ** 2 + (c["longitud"] - lon_ref) ** 2) ** 0.5
                score += dist * 10  # ~1.1 km por grado a esas latitudes

            if score < mejor_score:
                mejor_score = score
                mejor = c

        if mejor is None:
            return None

        return {k: v for k, v in mejor.items() if k != "dt"}

    # ── Modo inmediato: primer ítem dentro del margen temporal
    primero = items[0]
    if primero["dt"]:
        diff = datetime.datetime.now() - primero["dt"]
        if diff.total_seconds() / 60 > max_minutos_diff:
            return None

    return {k: v for k, v in primero.items() if k != "dt"}


def buscar_replicas_ssn(hora_evento, min_mag=3.5):
    """Busca sismos en el RSS del SSN que hayan ocurrido después de hora_evento."""
    replicas = []
    root = _fetch_ssn_root()
    if root is None:
        return replicas

    for c in _parsear_items_ssn(root):
        if c["dt"] and c["dt"] > hora_evento:
            mag = c["magnitud"] or 0.0
            if mag >= min_mag:
                replicas.append({"magnitud": mag, "titulo": c["ubicacion"]})

    return replicas


def consultar_usgs(hora_str):
    try:
        dt    = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
        start = (dt - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        # Ventana de 90 min: USGS tiene latencia alta para México (no es región prioritaria)
        end   = (dt + datetime.timedelta(minutes=90)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
            f"&starttime={start}&endtime={end}&minmagnitude={config.SISMO_MIN_MAG}"
            # Bounding box ampliado: México completo (lat 14-32.5, lon -118.5 a -86)
            f"&minlatitude={config.SISMO_MIN_LAT}&maxlatitude={config.SISMO_MAX_LAT}"
            f"&minlongitude={config.SISMO_MIN_LON}&maxlongitude={config.SISMO_MAX_LON}&orderby=time"
        )
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if data.get("features"):
                f = data["features"][0]
                coords = f["geometry"].get("coordinates", [])
                return {
                    "magnitud":       f["properties"].get("mag"),
                    "ubicacion":      f["properties"].get("place"),
                    "tsunami":        f["properties"].get("tsunami"),
                    "profundidad_km": coords[2] if len(coords) > 2 else None,
                }
    except Exception as e:
        print(f"[SISMO] ⚠️ Error USGS: {e}")
    return None


def consultar_emsc(hora_str, lat, lon):
    if lat is None or lon is None:
        return None
    try:
        dt    = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
        start = (dt - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://www.seismicportal.eu/fdsnws/event/1/query?format=json"
            f"&starttime={start}&minmag={config.SISMO_MIN_MAG}&lat={lat}&lon={lon}&maxradius=3"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("features"):
                return {"magnitud": data["features"][0]["properties"].get("mag")}
    except Exception as e:
        print(f"[SISMO] ⚠️ Error EMSC: {e}")
    return None


def consultar_gfz(hora_str, lat, lon):
    """
    GFZ Potsdam FDSNWS — reemplaza a IRIS (cuyo endpoint devuelve HTTP 404 permanentemente).
    Busca el evento por proximidad geografica (maxradius=3 grados).
    El servicio GFZ usa FDSN estandar con parametros latitude/longitude/maxradius.
    Retorna dict con: magnitud — o None si no se encuentra.
    """
    if lat is None or lon is None:
        return None
    try:
        dt    = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
        start = (dt - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://geofon.gfz-potsdam.de/fdsnws/event/1/query?format=text"
            f"&starttime={start}&minmagnitude={config.SISMO_MIN_MAG}"
            f"&latitude={lat}&longitude={lon}&maxradius=3"
        )
        r = requests.get(url, timeout=12)
        if r.status_code == 200:
            lineas = r.text.strip().split("\n")
            # Formato: #EventID|Time|Latitude|Longitude|Depth|...|MagType|Magnitude|...
            # Indice: 0        1    2         3          4     5   9       10
            if len(lineas) > 1:
                partes = lineas[1].split("|")
                if len(partes) > 10:
                    try:
                        return {"magnitud": float(partes[10])}
                    except (ValueError, IndexError):
                        pass
        elif r.status_code == 204:
            pass  # Sin datos — no es un error
    except Exception as e:
        print(f"[SISMO] ⚠️ Error GFZ: {e}")
    return None
