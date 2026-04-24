# rev 15.1.0
# rev anterior: rev 15.0.0
# Changelog:
#   15.1.0 — Anotaciones de tipo migradas a Optional/Tuple de typing
#            para compatibilidad con Python 3.9 (Raspberry Pi OS).
#   15.0.0 — Módulo refactorizado. Se conserva la lógica de recuperación del
#            webservice CONAGUA/SMN y se añade la extracción y normalización
#            de todos los campos relevantes (hoy y mañana) en un dict
#            estructurado listo para usar en prompt.py y meteorologo.py.
#            Los parámetros de localización se leen desde config.py.

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
                if reporte.get("ndia") in ("0", "1"):
                    pronostico.append(reporte)
                if len(pronostico) == 2:
                    break

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


def _extraer_dia(registro):
    """
    Extrae y normaliza todos los campos de un registro diario del SMN
    en un diccionario de tipos nativos (float/str/None).
    """
    return {
        "condicion":     registro.get("desciel"),
        "temp_max":      _num(registro.get("tmax")),
        "temp_min":      _num(registro.get("tmin")),
        "prob_lluvia":   _num(registro.get("probprec", 0)),
        "precipitacion": _num(registro.get("prec", 0)),
        "viento":        _num(registro.get("velvien")),
        "dir_viento":    registro.get("dirvienc"),
        "rafagas":       _num(registro.get("raf")),
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
    Recupera y extrae el pronóstico de hoy y mañana del SMN/CONAGUA.

    Retorna un dict con la estructura:
        {
            "hoy":    { condicion, temp_max, temp_min, prob_lluvia,
                        precipitacion, viento, dir_viento, rafagas },
            "manana": { condicion, temp_max, temp_min, ... } o None
        }
    Retorna None si no fue posible obtener ningún dato.
    """
    registros = _obtener_datos_crudos(clave_estado, nombre_municipio)
    if not registros:
        return None

    hoy    = _extraer_dia(registros[0])
    manana = _extraer_dia(registros[1]) if len(registros) > 1 else None

    return {"hoy": hoy, "manana": manana}
