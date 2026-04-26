# rev 15.1.0
# rev anterior: rev 15.0.0
# Changelog:
#   15.1.0 — Anotaciones de tipo migradas a Optional/Tuple de typing
#            para compatibilidad con Python 3.9 (Raspberry Pi OS).
#   15.0.0 — Extracción de la generación de guiones a módulo independiente.
#            Cascada de fallback intacta: Gemini principal → Gemini respaldo → Groq.
#            Credenciales y nombres de modelos se leen desde config.py.

from typing import Optional, Tuple

import requests

import config
import estado
from bd import _sanitizar_error


# ==========================================
#   MODELO DE EMERGENCIA: GROQ
# ==========================================

def _generar_groq(prompt):
    # type: (str) -> Tuple[Optional[str], str, Optional[str]]
    """
    Genera el guion vía Groq con el modelo especificado. 
    Retorna (texto_guion, modelo_usado, mensaje_error).
    """
    url     = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": "Bearer {0}".format(config.GROQ_API_KEY),
        "Content-Type":  "application/json",
    }
    payload = {
        "model":                 config.MODELO_GROQ,
        "messages":              [{"role": "user", "content": prompt}],
        "temperature":           0.6,
        "max_completion_tokens": 4096,
        "top_p":                 0.95,
        "stream":                False,
        "stop":                  None,
    }
    try:
        respuesta = requests.post(url, headers=headers, json=payload, timeout=45)
        if respuesta.status_code == 200:
            texto = respuesta.json()["choices"][0]["message"]["content"]
            print(f"[IA] - {estado.ts()} ✅ Guion generado con éxito por el modelo de EMERGENCIA: {config.MODELO_GROQ}")
            return texto, config.MODELO_GROQ, None
        else:
            msg = _sanitizar_error(f"HTTP {respuesta.status_code}: {respuesta.text[:300]}")
            print(f"[ERROR] - {estado.ts()} Groq ({config.MODELO_GROQ}) devolvió código {respuesta.status_code}")
            return None, config.MODELO_GROQ, msg
    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Falló la petición a Groq ({config.MODELO_GROQ}): {e}")
        return None, config.MODELO_GROQ, msg


# ==========================================
#   GEMINI (principal y respaldo)
# ==========================================

def _generar_gemini(prompt, usar_respaldo=False):
    # type: (str, bool) -> Tuple[Optional[str], str, Optional[str]]
    """
    Genera el guion vía la API REST de Gemini.
    Cascada interna: modelo principal → modelo respaldo → Groq de emergencia.
    Retorna (texto_guion, modelo_usado, mensaje_error).
    """
    modelo_actual = config.MODELO_GEMINI_RESPALDO if usar_respaldo else config.MODELO_GEMINI
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{0}:generateContent?key={1}".format(modelo_actual, config.GEMINI_API_KEY)
    )
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        respuesta = requests.post(url, headers=headers, json=payload, timeout=30)
        if respuesta.status_code == 200:
            texto = respuesta.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"[IA] - {estado.ts()} ✅ Guion generado con éxito por: {modelo_actual}")
            return texto, modelo_actual, None
        else:
            msg = _sanitizar_error(f"HTTP {respuesta.status_code}: {respuesta.text[:300]}")
            print(f"[ERROR] - {estado.ts()} API Gemini ({modelo_actual}) devolvió código {respuesta.status_code}")
            if not usar_respaldo:
                print(f"[SISTEMA] - {estado.ts()} ⚠️  Activando modelo Gemini de RESPALDO...")
                return _generar_gemini(prompt, usar_respaldo=True)
            print(f"[SISTEMA] - {estado.ts()} 🚨 Ambos modelos Gemini fallaron. Activando modelo de EMERGENCIA Groq...")
            return _generar_groq(prompt)

    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Falló la petición a Gemini ({modelo_actual}): {e}")
        if not usar_respaldo:
            print(f"[SISTEMA] - {estado.ts()} ⚠️  Activando modelo Gemini de RESPALDO...")
            return _generar_gemini(prompt, usar_respaldo=True)
        print(f"[SISTEMA] - {estado.ts()} 🚨 Ambos modelos Gemini fallaron. Activando modelo de EMERGENCIA Groq...")
        return _generar_groq(prompt)


# ==========================================
#   PUNTO DE ENTRADA PÚBLICO
# ==========================================

def generar_guion(prompt):
    # type: (str) -> Tuple[Optional[str], str, Optional[str]]
    """
    Genera el guion meteorológico a partir del prompt dado.
    Ejecuta la cascada completa: Gemini principal → Gemini respaldo → Groq.

    Retorna (texto_guion, modelo_usado, mensaje_error).
    En éxito: (str, str, None).
    En fallo total: (None, str, str).
    """
    return _generar_gemini(prompt)
