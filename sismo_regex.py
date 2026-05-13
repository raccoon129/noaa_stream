# sismo_regex.py — Patrones de análisis de mensajes SASSLA

import re

# 1. Alerta
REGEX_ALERTA = re.compile(r"#TenemosAlerta\s+#SASMEX", re.IGNORECASE)

# 2. Tiempos
REGEX_TIEMPOS = re.compile(r"#Sismo en progreso\.\s*Tiempo Estimado de Llegada:", re.IGNORECASE)

# 3. Efectos
REGEX_EFECTOS = re.compile(r"#Sismo en progreso\.\s*Efectos esperados", re.IGNORECASE)
REGEX_CIUDAD = re.compile(r"(CDMX|CHI|ACA|OAX|MOR|COL|GDL|PUE|CVCA|TOL):\s*[🔴🟠🟡🔵🟢⚪]+\s*(EXTREMO|VIOLENTO|FUERTE|MODERADO|LIGERO|IMPERCEPTIBLE|--)", re.IGNORECASE)

# 4. Detectado (Epicentro preliminar)
REGEX_DETECTADO = re.compile(r"#SismoDetectado\.\s*Posible epicentro en:\s*(.+)", re.IGNORECASE)

# 5. Resumen
REGEX_RESUMEN = re.compile(r"Se registró #sismo de intensidad\s+(.+?)\s+en\s+(.+?)\.", re.IGNORECASE)

# 6. SSN
REGEX_SSN = re.compile(
    r"(?:Preliminar:\s*)?(?:ACTUALIZACIÓN DE MAGNITUD\s*)?SISMO\s+Magnitud\s+(\d+\.?\d*)\s+Loc\.?\s+(.+?),\s*(\w+)\s+(\d{2}/\d{2}/\d{2,4})\s+(\d{2}:\d{2}:\d{2})\s+Lat\s+([\d.-]+)\s+Lon\s+(-?[\d.-]+)\s+Pf\s+(\d+)\s*km",
    re.IGNORECASE
)

# 7. Simulacro
REGEX_SIMULACRO = re.compile(r"(?i)simulacro")

# Escala de intensidad para comparar
ESCALA_INTENSIDAD = {
    "--": 0,
    "IMPERCEPTIBLE": 1,
    "LIGERO": 2,
    "MODERADO": 3,
    "FUERTE": 4,
    "VIOLENTO": 5,
    "EXTREMO": 6
}
