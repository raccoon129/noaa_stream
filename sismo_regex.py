# sismo_regex.py — Patrones de análisis de mensajes SASSLA

import re

# 1. Alerta SASMEX
REGEX_ALERTA = re.compile(r"#TenemosAlerta\s+#SASMEX", re.IGNORECASE)

# 2. Tiempos estimados de llegada — se ignoran: datos inmediatos sin valor posterior
REGEX_TIEMPOS = re.compile(r"#Sismo en progreso\.\s*Tiempo Estimado de Llegada:", re.IGNORECASE)

# 3. Efectos esperados por ciudad
REGEX_EFECTOS = re.compile(r"#Sismo en progreso\.\s*Efectos esperados", re.IGNORECASE)

# Captura ciudad + intensidad. EXTREMO es el nivel máximo de la escala SASSLA.
REGEX_CIUDAD = re.compile(
    r"(CDMX|CHI|ACA|OAX|MOR|COL|GDL|PUE|CVCA|TOL):\s*"
    r"[\U0001F534\U0001F7E0\U0001F7E1\U0001F535\U0001F7E2\u26AA]+"
    r"\s*(EXTREMO|VIOLENTO|FUERTE|MODERADO|LIGERO|IMPERCEPTIBLE|--)",
    re.IGNORECASE
)

# 4. Detectado — epicentro preliminar de SASSLA
REGEX_DETECTADO = re.compile(r"#SismoDetectado\.\s*Posible epicentro en:\s*(.+)", re.IGNORECASE)

# 5. Resumen post-evento de SASSLA
# Ej: "Se registró #sismo de intensidad FUERTE en Guerrero Costa Central."
REGEX_RESUMEN = re.compile(
    r"Se registró #sismo de intensidad\s+(\S+)\s+en\s+(.+?)\.",
    re.IGNORECASE
)
# Efecto estimado en CDMX dentro del mensaje de resumen
# Ej: "Se estimó efecto MODERADO para la #CDMX."
REGEX_RESUMEN_CDMX = re.compile(
    r"Se estim[oó] efecto\s+(\S+)\s+para la\s+#?(CDMX)",
    re.IGNORECASE
)

# 6a. SSN formato raw (llega directamente del SSN, con lat/lon)
REGEX_SSN = re.compile(
    r"(?:Preliminar:\s*)?(?:ACTUALIZACIÓN DE MAGNITUD\s*)?SISMO\s+Magnitud\s+([\d.]+)\s+Loc\.?\s+(.+?),\s*(\w+)\s+(\d{2}/\d{2}/\d{2,4})\s+(\d{2}:\d{2}:\d{2})\s+Lat\s+([\d.-]+)\s+Lon\s+(-?[\d.-]+)\s+Pf\s+(\d+)\s*km",
    re.IGNORECASE
)

# 6b. SSN formato SASSLA-relay — mensajes que SASSLA publica con datos del SSN
#     SIN coordenadas, en su propio formato narrativo.
#     Ej: "Información del SSN:\nPreliminar: Magnitud 5.3, 26 km al SUROESTE de SAN MARCOS, GRO."
#     Ej: "Actualización de Información del SSN:\nMagnitud final 5.2, 25 km al OESTE de San Marcos, Guerrero."
REGEX_SSN_SASSLA = re.compile(
    r"(?:Preliminar:\s*Magnitud|Magnitud final)\s+([\d.]+),\s+(.+?)\.",
    re.IGNORECASE
)

# 7. Simulacro
REGEX_SIMULACRO = re.compile(r"(?i)simulacro")

# Escala de intensidad numérica (para comparar y conservar la más alta)
# Escala oficial SASSLA: IMPERCEPTIBLE → LIGERO → MODERADO → FUERTE → VIOLENTO → EXTREMO
ESCALA_INTENSIDAD = {
    "--":            0,
    "IMPERCEPTIBLE": 1,
    "LIGERO":         2,
    "MODERADO":       3,
    "FUERTE":         4,
    "VIOLENTO":       5,
    "EXTREMO":        6,
}

# Nombres completos de las abreviaturas de ciudades que usa SASSLA en sus reportes
# NOTA: CHI = Chilpancingo (capital de Guerrero), NO Chiapas.
#       SASSLA usa "CHI" para Chilpancingo, ciudad cercana al epicentro típico de sismos del Pacífico.
CIUDADES_SASSLA = {
    "CDMX":  "Ciudad de México",
    "CHI":   "Chilpancingo, Guerrero",
    "ACA":   "Acapulco, Guerrero",
    "OAX":   "Oaxaca",
    "MOR":   "Morelos",
    "COL":   "Colima",
    "GDL":   "Guadalajara, Jalisco",
    "PUE":   "Puebla",
    "CVCA":  "Cuernavaca, Morelos",
    "TOL":   "Toluca, Estado de México",
}
