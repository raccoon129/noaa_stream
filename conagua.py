# rev 16.2.0
# rev anterior: rev 16.1.0
# Changelog:
#   16.2.0 — Selección de 'hoy' y 'mañana' por fecha local (campo dloc, formato
#            YYYYMMDDTHH) en lugar de por ndia 0/1. De 00:00 a ~06:00 el feed
#            aún trae como ndia=0 el día anterior (verificado 2026-10-27), por
#            lo que 'hoy' y 'mañana' salían desfasados un día. Si no existe un
#            registro con la fecha de hoy se retorna None (sin datos) antes que
#            reportar un pronóstico de otra fecha.
#   16.1.0 — Se eliminan obtener_pronostico_horario() y funciones auxiliares
#            de method=3 (CONAGUA horario): demasiado pesadas para el hardware.
#            Solo permanece obtener_pronostico() (method=1, pronóstico diario).
#   16.0.0 — _extraer_dia() extiende campos: cc (nubosidad %), dirvieng (grados),
#            dloc (timestamp). obtener_pronostico() expone campos completos de
#            mañana. Se añadió obtener_pronostico_horario() (method=3) — retirado.
#   15.1.0 — Anotaciones de tipo migradas a Optional/Tuple de typing.
#   15.0.0 — Módulo refactorizado.

import datetime
import gzip
import io
import json
from typing import Optional

import requests
import urllib3

import config
import estado

# Ocultar advertencias de certificado SSL roto del servidor de gobierno
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ==========================================
#   RECUPERACIÓN RAW DEL WEBSERVICE
# ==========================================

def _obtener_datos_crudos(
    clave_estado=config.CLAVE_ESTADO_CONAGUA,
    nombre_municipio=config.MUNICIPIO_CONAGUA
):
    """
    Descarga y descomprime el feed GZIP del SMN.
    Retorna la lista de dicts del municipio (hoy + mañana), o None si falla.
    """
    url = (
        f"https://smn.conagua.gob.mx/tools/GUI/webservices/index.php"
        f"?method=1&type=pm&cveEdo={clave_estado}"
    )
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        respuesta = requests.get(url, headers=headers, timeout=15, verify=False)
        if respuesta.status_code != 200:
            print(f"[CONAGUA] - {estado.ts()} ⚠️ HTTP {respuesta.status_code}")
            return None

        archivo_comprimido = io.BytesIO(respuesta.content)
        with gzip.GzipFile(fileobj=archivo_comprimido) as gz:
            contenido_crudo = gz.read().decode("utf-8")

        datos = json.loads(contenido_crudo)

        pronostico = []
        for reporte in datos:
            if reporte.get("nmun", "").lower() == nombre_municipio.lower():
                pronostico.append(reporte)

        return pronostico if pronostico else None

    except Exception as e:
        print(f"[CONAGUA] - {estado.ts()} ⚠️ Error al recuperar datos: {e}")
        return None


# ==========================================
#   EXTRACCIÓN Y NORMALIZACIÓN
# ==========================================

def _num(valor):
    """Convierte un valor a float; retorna None si no es convertible."""
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _fecha_dloc(dloc):
    """Convierte 'YYYYMMDDTHH' a datetime.date; retorna None si no es válido."""
    try:
        return datetime.datetime.strptime(str(dloc)[:8], "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def _extraer_dia(registro):
    """
    Extrae y normaliza todos los campos de un registro diario del SMN.
    v16: añade cc (nubosidad %), dirvieng (dirección en grados) y dloc (timestamp).
    """
    return {
        "condicion":     registro.get("desciel"),
        "temp_max":      _num(registro.get("tmax")),
        "temp_min":      _num(registro.get("tmin")),
        "prob_lluvia":   _num(registro.get("probprec", 0)),
        "precipitacion": _num(registro.get("prec", 0)),
        "viento":        _num(registro.get("velvien")),
        "dir_viento":    registro.get("dirvienc"),
        "dirvieng":      _num(registro.get("dirvieng")),
        "rafagas":       _num(registro.get("raf")),
        "cc":            _num(registro.get("cc")),
        "dloc":          registro.get("dloc"),
    }


# ==========================================
#   PUNTO DE ENTRADA PÚBLICO
# ==========================================

def obtener_pronostico(
    clave_estado=config.CLAVE_ESTADO_CONAGUA,
    nombre_municipio=config.MUNICIPIO_CONAGUA
):
    # type: (...) -> Optional[dict]
    """
    Recupera y extrae el pronóstico de hoy y mañana del SMN/CONAGUA (method=1).
    v16: mañana incluye campos completos (prob_lluvia, precipitacion, viento, etc.).

    Retorna un dict con la estructura:
        {
            "hoy":    { condicion, temp_max, temp_min, prob_lluvia, precipitacion,
                        viento, dir_viento, dirvieng, rafagas, cc, dloc },
            "manana": { idénticos campos } o None
        }
    Retorna None si no fue posible obtener ningún dato.
    """
    registros = _obtener_datos_crudos(clave_estado, nombre_municipio)
    if not registros:
        return None

    # Selección por fecha local, no por posición (ndia): de madrugada el feed
    # todavía publica el día anterior como ndia=0.
    tz_mx = datetime.timezone(datetime.timedelta(hours=-6))
    fecha_hoy    = datetime.datetime.now(tz_mx).date()
    fecha_manana = fecha_hoy + datetime.timedelta(days=1)

    por_fecha = {}
    for reg in registros:
        f = _fecha_dloc(reg.get("dloc"))
        if f is not None:
            por_fecha[f] = reg

    reg_hoy    = por_fecha.get(fecha_hoy)
    reg_manana = por_fecha.get(fecha_manana)

    if reg_hoy is None:
        print(
            f"[CONAGUA] - {estado.ts()} ⚠️ Sin registro para hoy ({fecha_hoy}); "
            f"fechas disponibles: {sorted(str(f) for f in por_fecha)}"
        )
        return None

    hoy    = _extraer_dia(reg_hoy)
    manana = _extraer_dia(reg_manana) if reg_manana else None

    return {"hoy": hoy, "manana": manana}

