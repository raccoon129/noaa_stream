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
    if datos.get("ssn_profundidad_km") is not None:
        contexto.append(f"Profundidad del foco: {datos['ssn_profundidad_km']} km")
    if datos.get("intensidad_cdmx"):
        contexto.append(f"Intensidad en CDMX: {datos['intensidad_cdmx']}")
    if datos.get("intensidad_tol"):
        contexto.append(f"Intensidad en Toluca: {datos['intensidad_tol']}")


    # Datos de APIs internacionales (si ya los tenemos) — con descripción de la fuente
    if datos.get("usgs_magnitud"):
        contexto.append(
            f"USGS (Servicio Geológico de los Estados Unidos, principal agencia geofísica de referencia mundial) "
            f"reporta magnitud {datos['usgs_magnitud']}"
        )
    if datos.get("usgs_tsunami") == 1:
        contexto.append("USGS ha emitido alerta de tsunami para este evento")
    if datos.get("emsc_magnitud"):
        contexto.append(
            f"EMSC (Centro Sismológico Euro-Mediterráneo, red de monitoreo sismológico en tiempo real de Europa) "
            f"reporta magnitud {datos['emsc_magnitud']}"
        )
    if datos.get("gfz_magnitud"):
        contexto.append(
            f"GFZ Potsdam (Centro Alemán de Investigación en Geociencias, observatorio sismológico global) "
            f"reporta magnitud {datos['gfz_magnitud']}"
        )
    if datos.get("replicas_detectadas"):
        contexto.append(
            f"El SSN (Servicio Sismológico Nacional de México) ha registrado "
            f"{datos['replicas_detectadas']} réplicas posteriores al evento"
        )


    ctx_str = "\n".join(contexto) if contexto else "Datos aún no disponibles."

    return (
        "Eres el locutor de alerta sísmica de una estación meteorológica automatizada. "
        "Redacta un boletín preliminar de sismo.\n\n"
        "JERARQUÍA DE FUENTES (importante para interpretar los datos):\n"
        "- FUENTE PRIMARIA Y OFICIAL: SSN (Servicio Sismológico Nacional de México). "
        "Sus datos de magnitud, epicentro y profundidad son los de referencia para México.\n"
        "- FUENTES SECUNDARIAS (confirmación internacional): USGS, EMSC y GFZ Potsdam. "
        "Si sus magnitudes difieren ligeramente del SSN, es normal debido a diferencias metodológicas; "
        "el dato del SSN tiene prioridad.\n\n"
        f"Datos del evento:\n{ctx_str}\n\n"
        "REGLAS:\n"
        "1. Inicia directamente con 'Boletín de alerta sísmica...' "
        "NO incluyas cortinilla institucional (ya se emite en el reporte del clima que se alterna).\n"
        "2. Informa de los datos disponibles de epicentro e intensidades con una interpretación precisa. Si hay magnitud, dila.\n"
        "3. Si hay confirmación de agencias internacionales, menciónalas brevemente como respaldo al reporte del SSN.\n"
        "4. Da recomendaciones básicas de seguridad.\n"
        "5. Indica que la información detallada estará disponible en la próxima actualización.\n"
        "6. Cierra con la frase exacta: 'Este es un reporte especial de alerta sísmica reciente.'\n"
        "7. Expresa los números y horas en letra para locución."
    )

