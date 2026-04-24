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
