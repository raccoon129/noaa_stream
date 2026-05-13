# sismo_prompts.py — Generación de prompts para reportes sísmicos

import time
import config


def construir_prompt_sismo_inmediato(datos):
    """
    Prompt para el reporte sísmico inmediato (justo después de la alarma).
    SIN cortinilla institucional: se intercalará con el clima que ya la tiene.
    """
    contexto = []
    if datos.get("epicentro"):
        contexto.append(f"Posible epicentro: {datos['epicentro']}")
    if datos.get("ssn_magnitud"):
        contexto.append(f"Magnitud preliminar (SSN/SASSLA): {datos['ssn_magnitud']}")
    if datos.get("intensidad_cdmx"):
        contexto.append(f"Intensidad en CDMX: {datos['intensidad_cdmx']}")
    if datos.get("intensidad_tol"):
        contexto.append(f"Intensidad en Toluca: {datos['intensidad_tol']}")

    # Datos de APIs internacionales (si ya los tenemos)
    if datos.get("usgs_magnitud"):
        contexto.append(f"Magnitud USGS: {datos['usgs_magnitud']}")
    if datos.get("usgs_tsunami") == 1:
        contexto.append("USGS reporta alerta de tsunami")
    if datos.get("emsc_magnitud"):
        contexto.append(f"Magnitud EMSC: {datos['emsc_magnitud']}")
    if datos.get("replicas_detectadas"):
        contexto.append(f"Réplicas detectadas: {datos['replicas_detectadas']}")

    ctx_str = "\n".join(contexto) if contexto else "Datos aún no disponibles."

    return (
        "Eres el locutor de alerta sísmica de una estación de radio automatizada. "
        "Redacta un boletín preliminar de sismo.\n\n"
        f"Datos del evento:\n{ctx_str}\n\n"
        "REGLAS:\n"
        "1. Inicia directamente con 'Boletín especial de alerta sísmica...' "
        "NO incluyas cortinilla institucional (ya se emite en el reporte del clima que se alterna).\n"
        "2. Informa de los datos disponibles de epicentro e intensidades. Si hay magnitud, dila.\n"
        "3. Da recomendaciones básicas de seguridad.\n"
        "4. Indica que la información detallada estará disponible en la próxima actualización.\n"
        "5. Cierra con la frase exacta: 'Este es un reporte en bucle.'\n"
        "6. Expresa los números y horas en letra para locución."
    )
