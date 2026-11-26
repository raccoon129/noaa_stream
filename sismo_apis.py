# sismo_apis.py — Consultas a APIs sismológicas (SSN, USGS, EMSC, GFZ)
# rev 15.4.0
# Changelog:
#   15.4.0 — Corrección de huso horario (UTC-6 → UTC) en consultar_usgs(),
#            consultar_emsc() y consultar_gfz(). Ventana acotada con
#            SISMO_VENTANA_ANTES_MIN / SISMO_VENTANA_DESPUES_MIN y filtro
#            geográfico (SISMO_RADIO_COINCIDENCIA_KM) cuando hay coordenadas SSN.
#            Extracción de campos extendidos USGS: alert (PAGER), mmi (ShakeMap),
#            cdi y felt (DYFI), sig, y redondeo de magnitud/profundidad a 1 decimal.
#            describir_usgs_para_prompt() formatea estos indicadores en español.
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


def _hora_local_a_utc(hora_str: str) -> datetime.datetime:
    """
    Convierte una marca de tiempo en hora local del centro de México (UTC-6,
    formato '%Y-%m-%d %H:%M:%S' usado por SSN y SASSLA) a datetime en UTC
    para consultar agencias internacionales FDSNWS (USGS, EMSC, GFZ).
    """
    dt_local = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
    return dt_local + datetime.timedelta(hours=6)


_PAGER_ALERTA_ES = {
    "green":  "verde (sin probabilidad de daños estructurales ni víctimas estimadas)",
    "yellow": "amarillo (posibles daños locales menores; alerta regional baja)",
    "orange": "naranja (daños significativos probables a nivel regional)",
    "red":    "rojo (alerta máxima por probables daños severos e impacto humano)",
}


def _etiqueta_mercalli_es(valor: float) -> str:
    """Traduce un valor numérico de escala Mercalli Modificada (MMI/CDI) a etiqueta en español."""
    if valor < 2.0:
        return "imperceptible"
    elif valor < 3.5:
        return "débil"
    elif valor < 4.5:
        return "ligera"
    elif valor < 5.5:
        return "moderada"
    elif valor < 6.5:
        return "fuerte"
    elif valor < 7.5:
        return "muy fuerte"
    elif valor < 8.5:
        return "severa"
    return "violenta a extrema"


def describir_usgs_para_prompt(datos: dict) -> str:
    """
    Construye la línea descriptiva de USGS para los prompts (inmediato y clima),
    integrando magnitud e indicadores adicionales (ShakeMap MMI, PAGER alert,
    reportes ciudadanos DYFI/CDI) cuando estén disponibles.
    Retorna cadena vacía si no hay usgs_magnitud.
    """
    mag = datos.get("usgs_magnitud")
    if not mag:
        return ""

    partes = [
        f"USGS (Servicio Geológico de los Estados Unidos, principal agencia geofísica de referencia mundial) "
        f"reporta magnitud {mag}"
    ]

    mmi = datos.get("usgs_mmi")
    if mmi is not None:
        try:
            mmi_val = float(mmi)
            partes.append(
                f"intensidad instrumental en superficie {_etiqueta_mercalli_es(mmi_val)} "
                f"(nivel {mmi_val:.1f} en la escala Mercalli de ShakeMap)"
            )
        except (ValueError, TypeError):
            pass

    alert = datos.get("usgs_alert")
    if alert and str(alert).lower() in _PAGER_ALERTA_ES:
        desc_alerta = _PAGER_ALERTA_ES[str(alert).lower()]
        partes.append(f"nivel de alerta PAGER en color {desc_alerta}")

    felt = datos.get("usgs_felt")
    cdi  = datos.get("usgs_cdi")
    if felt is not None:
        try:
            felt_num = int(felt)
            if felt_num > 0:
                if cdi is not None:
                    try:
                        cdi_val = float(cdi)
                        partes.append(
                            f"{felt_num} reportes ciudadanos de percepción recibidos "
                            f"(intensidad percibida {_etiqueta_mercalli_es(cdi_val)}, nivel {cdi_val:.1f})"
                        )
                    except (ValueError, TypeError):
                        partes.append(f"{felt_num} reportes ciudadanos de percepción recibidos")
                else:
                    partes.append(f"{felt_num} reportes ciudadanos de percepción recibidos")
        except (ValueError, TypeError):
            pass

    if len(partes) == 1:
        return partes[0]
    return partes[0] + ", con " + "; ".join(partes[1:])


def consultar_usgs(hora_str, lat_ref=None, lon_ref=None):
    try:
        dt_utc = _hora_local_a_utc(hora_str)
        start  = (dt_utc - datetime.timedelta(minutes=config.SISMO_VENTANA_ANTES_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        end    = (dt_utc + datetime.timedelta(minutes=config.SISMO_VENTANA_DESPUES_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
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
            features = data.get("features") or []
            if not features:
                return None

            mejor_f = None
            mejor_score = float("inf")
            for f in features:
                p = f.get("properties", {})
                coords = f.get("geometry", {}).get("coordinates", [])
                f_lon = coords[0] if len(coords) > 0 else None
                f_lat = coords[1] if len(coords) > 1 else None

                # Si ya tenemos coordenadas de referencia (SSN), filtrar por distancia
                dist_km = 0.0
                if lat_ref is not None and lon_ref is not None and f_lat is not None and f_lon is not None:
                    dist_km = (((f_lat - lat_ref) ** 2 + (f_lon - lon_ref) ** 2) ** 0.5) * 111.0
                    if dist_km > config.SISMO_RADIO_COINCIDENCIA_KM:
                        continue

                # Diferencia temporal respecto a dt_utc en minutos
                t_ms = p.get("time")
                if t_ms is not None:
                    dt_ev_utc = datetime.datetime.fromtimestamp(
                        t_ms / 1000.0, tz=datetime.timezone.utc
                    ).replace(tzinfo=None)
                    diff_min = abs((dt_ev_utc - dt_utc).total_seconds()) / 60.0
                else:
                    diff_min = 0.0

                score = diff_min + (dist_km / 10.0)
                if score < mejor_score:
                    mejor_score = score
                    mejor_f = f

            if mejor_f is None:
                return None

            p = mejor_f.get("properties", {})
            coords = mejor_f.get("geometry", {}).get("coordinates", [])
            mag_raw  = p.get("mag")
            mmi_raw  = p.get("mmi")
            cdi_raw  = p.get("cdi")
            felt_raw = p.get("felt")
            prof_raw = coords[2] if len(coords) > 2 else None

            return {
                "magnitud":       round(float(mag_raw), 1)  if mag_raw  is not None else None,
                "ubicacion":      p.get("place"),
                "tsunami":        p.get("tsunami"),
                "profundidad_km": round(float(prof_raw), 1) if prof_raw is not None else None,
                "latitud":        coords[1] if len(coords) > 1 else None,
                "longitud":       coords[0] if len(coords) > 0 else None,
                "alert":          p.get("alert"),
                "mmi":            round(float(mmi_raw), 1)  if mmi_raw  is not None else None,
                "cdi":            round(float(cdi_raw), 1)  if cdi_raw  is not None else None,
                "felt":           int(felt_raw)             if felt_raw is not None else None,
                "sig":            p.get("sig"),
            }
    except Exception as e:
        print(f"[SISMO] ⚠️ Error USGS: {e}")
    return None


def consultar_emsc(hora_str, lat, lon):
    if lat is None or lon is None:
        return None
    try:
        dt_utc = _hora_local_a_utc(hora_str)
        start  = (dt_utc - datetime.timedelta(minutes=config.SISMO_VENTANA_ANTES_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        end    = (dt_utc + datetime.timedelta(minutes=config.SISMO_VENTANA_DESPUES_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://www.seismicportal.eu/fdsnws/event/1/query?format=json"
            f"&starttime={start}&endtime={end}&minmag={config.SISMO_MIN_MAG}&lat={lat}&lon={lon}&maxradius=3"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("features"):
                mag_raw = data["features"][0]["properties"].get("mag")
                return {"magnitud": round(float(mag_raw), 1) if mag_raw is not None else None}
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
        dt_utc = _hora_local_a_utc(hora_str)
        start  = (dt_utc - datetime.timedelta(minutes=config.SISMO_VENTANA_ANTES_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        end    = (dt_utc + datetime.timedelta(minutes=config.SISMO_VENTANA_DESPUES_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://geofon.gfz-potsdam.de/fdsnws/event/1/query?format=text"
            f"&starttime={start}&endtime={end}&minmagnitude={config.SISMO_MIN_MAG}"
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
                        return {"magnitud": round(float(partes[10]), 1)}
                    except (ValueError, IndexError):
                        pass
        elif r.status_code == 204:
            pass  # Sin datos — no es un error
    except Exception as e:
        print(f"[SISMO] ⚠️ Error GFZ: {e}")
    return None
