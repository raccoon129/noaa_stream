# rev 15.0.0
# rev anterior: monolito noaa_estable.py rev 14.9.2
# Changelog:
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

