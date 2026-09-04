# rev 15.3.0
# rev anterior: rev 15.2.0
# Changelog:
#   15.3.0 — Modelo de emergencia migrado de Groq a OpenRouter.
#            _generar_groq() reemplazado por _generar_openrouter().
#            El razonamiento interno se desactiva vía {"reasoning": {"enabled": False}}
#            para que el thinking nunca llegue al contenido retornado.
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

import re
from typing import Optional, Tuple

import requests

import config
import estado
from bd import _sanitizar_error


# ==========================================
#   LIMPIEZA DE PENSAMIENTO INTERNO
# ==========================================

# Patrón que captura bloques de "thinking" de cualquier modelo.
# Cubre: <think>…</think>, <thinking>…</thinking> y variantes en mayúsculas.
# \s* al inicio también consume el espacio previo al bloque cuando está en
# mitad del texto, evitando que queden palabras pegadas al eliminar el bloque.
_RE_THINKING = re.compile(
    r"\s*<think(?:ing)?>[\s\S]*?</think(?:ing)?>\s*",
    re.IGNORECASE,
)


def _strip_thinking(texto):
    # type: (str) -> str
    """Elimina bloques <think>…</think> / <thinking>…</thinking> del texto generado.
    El razonamiento interno del modelo no debe almacenarse ni mostrarse."""
    limpio = _RE_THINKING.sub(" ", texto)   # reemplaza el bloque por un espacio
    limpio = re.sub(r"^ +", "", limpio)     # elimina espacios al inicio de línea
    limpio = re.sub(r"  +", " ", limpio)    # colapsa espacios dobles
    return limpio.lstrip()


# ==========================================
#   MODELO DE EMERGENCIA: OPENROUTER
# ==========================================

def _generar_openrouter(prompt):
    # type: (str) -> Tuple[Optional[str], str, Optional[str]]
    """
    Genera el guion vía OpenRouter (API compatible con OpenAI).
    Se desactiva el reasoning explícitamente para que el pensamiento interno
    del modelo no llegue ni al campo 'content' ni a 'reasoning_details'.
    Retorna (texto_guion, modelo_usado, mensaje_error).
    """
    url     = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": "Bearer {0}".format(config.OPENROUTER_API_KEY),
        "Content-Type":  "application/json",
    }
    payload = {
        "model":    config.MODELO_OPENROUTER,
        "messages": [{"role": "user", "content": prompt}],
        # Desactivar el razonamiento: el thinking no debe aparecer en el
        # contenido retornado ni almacenarse en la base de datos.
        "reasoning": {"enabled": False},
        "temperature":           0.6,
        "max_completion_tokens": 4096,
        "top_p":                 0.95,
    }
    try:
        respuesta = requests.post(url, headers=headers, json=payload, timeout=60)
        if respuesta.status_code == 200:
            texto = _strip_thinking(
                respuesta.json()["choices"][0]["message"].get("content") or ""
            )
            print(
                f"[IA] - {estado.ts()} ✅ Guion generado con éxito por el modelo de "
                f"EMERGENCIA (OpenRouter): {config.MODELO_OPENROUTER}"
            )
            return texto, config.MODELO_OPENROUTER, None
        else:
            msg = _sanitizar_error(f"HTTP {respuesta.status_code}: {respuesta.text[:300]}")
            print(
                f"[ERROR] - {estado.ts()} OpenRouter ({config.MODELO_OPENROUTER}) "
                f"devolvió código {respuesta.status_code}"
            )
            return None, config.MODELO_OPENROUTER, msg
    except Exception as e:
        msg = _sanitizar_error(str(e))
        print(f"[ERROR] - {estado.ts()} Falló la petición a OpenRouter ({config.MODELO_OPENROUTER}): {e}")
        return None, config.MODELO_OPENROUTER, msg


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
    Cascada por nivel: 0 (principal) → 1 (respaldo) → 2 (extra, opcional) → OpenRouter.

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
        print(f"[SISTEMA] - {estado.ts()} 🚨 Sin más modelos Gemini disponibles. Activando modelo de EMERGENCIA OpenRouter...")
        return _generar_openrouter(prompt)

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "{0}:generateContent?key={1}".format(modelo_actual, config.GEMINI_API_KEY)
    )
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    def _siguiente_escalon():
        # type: () -> Tuple[Optional[str], str, Optional[str]]
        """Escala al siguiente nivel Gemini o a OpenRouter si ya no hay más."""
        siguiente = nivel + 1
        modelo_siguiente = _modelo_para_nivel(siguiente)
        if modelo_siguiente:
            label = _NIVEL_LABELS.get(siguiente, str(siguiente))
            print(f"[SISTEMA] - {estado.ts()} ⚠️  Activando Gemini {label} ({modelo_siguiente})...")
            return _generar_gemini(prompt, nivel=siguiente)
        print(f"[SISTEMA] - {estado.ts()} 🚨 Todos los modelos Gemini fallaron. Activando modelo de EMERGENCIA OpenRouter...")
        return _generar_openrouter(prompt)

    try:
        respuesta = requests.post(url, headers=headers, json=payload, timeout=30)
        if respuesta.status_code == 200:
            texto = _strip_thinking(respuesta.json()["candidates"][0]["content"]["parts"][0]["text"])
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
        Gemini principal → Gemini respaldo → Gemini extra (si configurado) → OpenRouter.

    El paso 'Gemini extra' se activa solo si MODELO_GEMINI_EXTRA está definido
    y no vacío en config.py. De lo contrario se salta sin afectar el resto.

    Retorna (texto_guion, modelo_usado, mensaje_error).
    En éxito: (str, str, None).
    En fallo total: (None, str, str).
    """
    return _generar_gemini(prompt, nivel=0)
