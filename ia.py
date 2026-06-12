# rev 15.2.0
# rev anterior: rev 15.1.0
# Changelog:
#   15.2.0 — Cascada de fallback ampliada a 4 pasos:
#            Gemini principal → Gemini respaldo → Gemini extra (opcional) → Groq.
#            El paso "extra" usa MODELO_GEMINI_EXTRA de config.py; si está vacío
#            o no definido, se omite silenciosamente sin afectar los demás pasos.
#            _generar_gemini() ahora usa un nivel entero (0/1/2) en lugar de un
#            flag booleano, permitiendo escalar limpiamente a N modelos futuros.
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
#   GEMINI (principal, respaldo y extra)
# ==========================================

# Tabla de etiquetas por nivel para los mensajes de log.
# nivel 0 → MODELO_GEMINI (principal)
# nivel 1 → MODELO_GEMINI_RESPALDO
# nivel 2 → MODELO_GEMINI_EXTRA (opcional; se salta si está vacío o no definido)
_NIVEL_LABELS = {0: "principal", 1: "respaldo", 2: "extra"}


def _modelo_para_nivel(nivel):
    # type: (int) -> Optional[str]
    """Retorna el nombre del modelo Gemini para el nivel dado, o None si no aplica."""
    if nivel == 0:
        return config.MODELO_GEMINI
    if nivel == 1:
        return config.MODELO_GEMINI_RESPALDO
    if nivel == 2:
        # getattr con default "" para tolerar configs que no definen MODELO_GEMINI_EXTRA
        return getattr(config, "MODELO_GEMINI_EXTRA", "") or None
    return None


def _generar_gemini(prompt, nivel=0):
    # type: (str, int) -> Tuple[Optional[str], str, Optional[str]]
    """
    Genera el guion vía la API REST de Gemini.
    Cascada por nivel: 0 (principal) → 1 (respaldo) → 2 (extra, opcional) → Groq.

    El nivel 2 (extra) se salta automáticamente si MODELO_GEMINI_EXTRA está
    vacío o no definido en config.py, sin necesidad de modificar esta función.

    Retorna (texto_guion, modelo_usado, mensaje_error).
    """
    modelo_actual = _modelo_para_nivel(nivel)

    # Si el nivel solicitado no tiene modelo configurado (ej. extra vacío), avanzar
    if not modelo_actual:
        siguiente = nivel + 1
        modelo_siguiente = _modelo_para_nivel(siguiente)
        if modelo_siguiente:
            label = _NIVEL_LABELS.get(siguiente, str(siguiente))
            print(f"[SISTEMA] - {estado.ts()} ⚠️  Nivel {nivel} sin modelo configurado. Activando Gemini {label}...")
            return _generar_gemini(prompt, nivel=siguiente)
        print(f"[SISTEMA] - {estado.ts()} 🚨 Sin más modelos Gemini disponibles. Activando modelo de EMERGENCIA Groq...")
        return _generar_groq(prompt)

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{0}:generateContent?key={1}".format(modelo_actual, config.GEMINI_API_KEY)
    )
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    def _siguiente_escalon():
        # type: () -> Tuple[Optional[str], str, Optional[str]]
        """Escala al siguiente nivel Gemini o a Groq si ya no hay más."""
        siguiente = nivel + 1
        modelo_siguiente = _modelo_para_nivel(siguiente)
        if modelo_siguiente:
            label = _NIVEL_LABELS.get(siguiente, str(siguiente))
            print(f"[SISTEMA] - {estado.ts()} ⚠️  Activando Gemini {label} ({modelo_siguiente})...")
            return _generar_gemini(prompt, nivel=siguiente)
        print(f"[SISTEMA] - {estado.ts()} 🚨 Todos los modelos Gemini fallaron. Activando modelo de EMERGENCIA Groq...")
        return _generar_groq(prompt)

    try:
        respuesta = requests.post(url, headers=headers, json=payload, timeout=30)
        if respuesta.status_code == 200:
            texto = respuesta.json()["candidates"][0]["content"]["parts"][0]["text"]
            label = _NIVEL_LABELS.get(nivel, str(nivel))
            print(f"[IA] - {estado.ts()} ✅ Guion generado con éxito por Gemini {label}: {modelo_actual}")
            return texto, modelo_actual, None
        else:
            msg = _sanitizar_error(f"HTTP {respuesta.status_code}: {respuesta.text[:300]}")
            print(f"[ERROR] - {estado.ts()} API Gemini ({modelo_actual}) devolvió código {respuesta.status_code}")
            return _siguiente_escalon()

    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Falló la petición a Gemini ({modelo_actual}): {e}")
        return _siguiente_escalon()


# ==========================================
#   PUNTO DE ENTRADA PÚBLICO
# ==========================================

def generar_guion(prompt):
    # type: (str) -> Tuple[Optional[str], str, Optional[str]]
    """
    Genera el guion meteorológico a partir del prompt dado.
    Ejecuta la cascada completa:
        Gemini principal → Gemini respaldo → Gemini extra (si configurado) → Groq.

    El paso 'Gemini extra' se activa solo si MODELO_GEMINI_EXTRA está definido
    y no vacío en config.py. De lo contrario se salta sin afectar el resto.

    Retorna (texto_guion, modelo_usado, mensaje_error).
    En éxito: (str, str, None).
    En fallo total: (None, str, str).
    """
    return _generar_gemini(prompt, nivel=0)
