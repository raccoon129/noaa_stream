# sismo_apis.py — Consultas a APIs sismológicas (SSN, USGS, EMSC, IRIS)

import datetime
import re
import urllib.parse
import xml.etree.ElementTree as ET

import requests

import config
import estado


def consultar_ssn_xml(max_minutos_diff=5):
    """Descarga el RSS del SSN y devuelve el último evento si ocurrió dentro del margen."""
    try:
        response = requests.get(config.SSN_RSS_URL, timeout=10)
        if response.status_code != 200:
            return None
        root = ET.fromstring(response.content)
        items = root.findall('./channel/item')
        if not items:
            return None
        item = items[0]
        title = item.find('title').text if item.find('title') is not None else ""
        desc = item.find('description').text if item.find('description') is not None else ""
        mag = None
        m_mag = re.match(r"^([\d.]+),", title)
        if m_mag:
            mag = float(m_mag.group(1))
        dt_evento = None
        m_fecha = re.search(r"Fecha:(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", desc)
        if m_fecha:
            try:
                dt_evento = datetime.datetime.strptime(m_fecha.group(1), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
        if dt_evento:
            diff = datetime.datetime.now() - dt_evento
            if diff.total_seconds() / 60 > max_minutos_diff:
                return None
        loc = ""
        link = item.find('link').text if item.find('link') is not None else ""
        m_loc = re.search(r"&loc=([^&]+)&", link)
        if m_loc:
            loc = urllib.parse.unquote(m_loc.group(1)).strip()
        return {
            "magnitud": mag,
            "ubicacion": loc,
            "profundidad_km": None,
            "fecha_hora": dt_evento.strftime("%Y-%m-%d %H:%M:%S") if dt_evento else None
        }
    except Exception as e:
        print(f"[SISMO] ⚠️ Error leyendo SSN XML: {e}")
        return None


def buscar_replicas_ssn(hora_evento, min_mag=3.5):
    """Busca sismos en el RSS del SSN que hayan ocurrido después de hora_evento."""
    replicas = []
    try:
        response = requests.get(config.SSN_RSS_URL, timeout=10)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            for item in root.findall('./channel/item'):
                desc = item.find('description').text or ""
                m_fecha = re.search(r"Fecha:(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})", desc)
                if not m_fecha:
                    continue
                dt_item = datetime.datetime.strptime(m_fecha.group(1), "%Y-%m-%d %H:%M:%S")
                if dt_item > hora_evento:
                    title = item.find('title').text or ""
                    m_mag = re.match(r"^([\d.]+),", title)
                    mag = float(m_mag.group(1)) if m_mag else 0.0
                    if mag >= min_mag:
                        replicas.append({"magnitud": mag, "titulo": title.strip()})
    except Exception:
        pass
    return replicas


def consultar_usgs(hora_str):
    try:
        dt = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
        start = (dt - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        end = (dt + datetime.timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson"
            f"&starttime={start}&endtime={end}&minmagnitude={config.SISMO_MIN_MAG}"
            f"&minlatitude={config.SISMO_MIN_LAT}&maxlatitude={config.SISMO_MAX_LAT}"
            f"&minlongitude={config.SISMO_MIN_LON}&maxlongitude={config.SISMO_MAX_LON}&orderby=time"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("features"):
                f = data["features"][0]
                return {
                    "magnitud": f["properties"].get("mag"),
                    "ubicacion": f["properties"].get("place"),
                    "tsunami": f["properties"].get("tsunami"),
                    "profundidad_km": f["geometry"]["coordinates"][2] if len(f["geometry"]["coordinates"]) > 2 else None
                }
    except Exception as e:
        print(f"[SISMO] ⚠️ Error USGS: {e}")
    return None


def consultar_emsc(hora_str, lat, lon):
    if not lat or not lon:
        return None
    try:
        dt = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
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


def consultar_iris(hora_str, lat, lon):
    if not lat or not lon:
        return None
    try:
        dt = datetime.datetime.strptime(hora_str, "%Y-%m-%d %H:%M:%S")
        start = (dt - datetime.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S")
        url = (
            f"https://service.iris.edu/fdsnws/event/1/query?format=text"
            f"&starttime={start}&minmag={config.SISMO_MIN_MAG}&lat={lat}&lon={lon}&maxradius=3"
        )
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            lineas = r.text.strip().split("\n")
            if len(lineas) > 1:
                partes = lineas[1].split("|")
                if len(partes) > 10:
                    return {"magnitud": float(partes[10])}
    except Exception as e:
        print(f"[SISMO] ⚠️ Error IRIS: {e}")
    return None
