# rev 15.2.0
# rev anterior: rev 15.0.0
# Changelog:
#   15.2.0 — Se añade caché de estaciones solares USNO (estaciones_solares,
#            anio_estaciones_cache). Se consultan una vez al arrancar desde
#            noaa_str.iniciar_estacion() y se reutilizan por todo el año.
#   15.1.0 — Se añade ssn_sismos_activos: lista de grupos de sismos HGO detectados
#            via SSN RSS que aún tienen slots de mención pendientes. Gestionado
#            por ssn_rss.py; consultado en noaa_str.py y prompt.py.
#   15.0.0 — Módulo nuevo. Centraliza el estado mutable compartido entre dj.py,
#            meteorologo.py y noaa_str.py, evitando importaciones circulares.
#            También expone la utilidad ts() usada en todos los módulos.

import datetime

# ==========================================
#   ESTADO GLOBAL DE TRANSMISIÓN
# ==========================================

# Flag: True mientras el meteorólogo está generando un nuevo reporte.
# El DJ lo consulta para saber si debe entrar en modo espera.
actualizando_clima: bool = False

# Referencia al proceso Popen del pipeline de audio (sox | tee | ffmpeg).
# Se inicializa en dj.py al llamar a iniciar_o_reiniciar_stream().
flujo_radio = None


# ==========================================
#   UTILIDAD: TIMESTAMP PARA CONSOLA
# ==========================================

def ts() -> str:
    """Retorna el timestamp actual formateado para impresión en consola."""
    return datetime.datetime.now().strftime("%H:%M:%S %d/%m/%Y")


# ==========================================
#   ESTADO GLOBAL SÍSMICO
# ==========================================

# Flag: True mientras se reproduce alerta_sismica.wav en el DJ
alerta_sismica: bool = False

# Flag: True mientras hay un evento sísmico en cualquier fase activa
sismo_activo: bool = False

# Flag: True cuando el reporte sísmico inmediato está listo (sismo_reporte.wav)
sismo_guion_listo: bool = False

# Flag: True mientras el DJ intercala sismo_reporte.wav con clima_actual.wav
sismo_intercalando: bool = False

# Contador: cuántos ciclos de clima todavía re-consultan APIs sísmicas (2→1→0)
ciclos_sismo_restantes: int = 0

# Dict con todos los datos recopilados del sismo actual (SASSLA + SSN + APIs)
datos_sismo: dict = None

# time.time() del momento de activación de la alerta
timestamp_sismo: float = 0

# True si el evento activo es un simulacro (flujo simplificado: solo alarma)
sismo_es_simulacro: bool = False

# ID de la fila en condiciones_especiales del evento actual.
# Se asigna justo después del INSERT inicial para que enriquecer_con_apis()
# usa siempre el ID correcto (evita race condition con _obtener_ultimo_id_evento).
ultimo_id_sismo_bd: int = None


# ==========================================
#   ESTADO GLOBAL SSN RSS (HIDALGO)
# ==========================================

# Lista de grupos de sismos HGO activos con slots de mención pendientes.
# Cada elemento es un dict con las claves:
#   clave         — str identificador único del grupo (timestamp|ubicacion)
#   bd_id         — int ID del registro en condiciones_especiales, o None
#   grupo         — list[dict] de sismos del grupo
#   slots_mencion — list[str] de slots HH:MM pendientes de procesar
# Gestionado por ssn_rss.py; consumido en noaa_str.py y prompt.py.
ssn_sismos_activos: list = []


# ==========================================
#   ESTADO GLOBAL — ESTACIONES SOLARES (USNO)
# ==========================================

# Lista de eventos solares del año actual (solsticios, equinoccios, perihelio, afelio).
# Cada elemento es un dict con las claves:
#   phenom          — str en inglés: 'Solstice', 'Equinox', 'Perihelion', 'Aphelion'
#   nombre_es       — str en español con contexto estacional
#   year, month, day— ints
#   hora_local      — str 'HH:MM' en hora centro (UTC-6)
#   fecha_dt        — datetime.date del evento
# Se rellena en noaa_str.iniciar_estacion() y persiste toda la sesión.
estaciones_solares: list = []

# Año al que pertenece la caché. Si cambia el año calendario,
# meteorologo.obtener_estaciones_solares() rehace la consulta.
anio_estaciones_cache: int = 0

# Conjunto de claves de eventos solares ya guardados en BD durante esta sesión.
# Formato de cada clave: "phenom|YYYY-MM-DD" (ej. "Solstice|2026-06-21").
# Previene inserciones duplicadas si el ciclo de 30 min corre varias veces
# en el mismo día del evento. Se reinicia al reiniciar el proceso.
estaciones_guardadas_bd: set = set()
