# rev 15.1.0
# rev anterior: rev 15.0.0
# Changelog:
#   15.1.0 — Timeout en subprocess.run() de edge-tts (90 s) y sox (60 s).
#            Sin timeout, una conexión a Azure TTS que se cuelga bloquea
#            el hilo de actualizar_audio_clima() indefinidamente, impidiendo
#            que estado.actualizando_clima vuelva a False y dejando al DJ
#            varado en modo espera.
#   15.0.0 — Extracción de la síntesis de voz a módulo independiente.
#            Incluye: escritura del guion en disco, llamada a edge-tts,
#            conversión sox a WAV 22050Hz mono, rotación atómica del
#            archivo maestro y guardado en historial.
#            Parámetros de audio y rutas se leen desde config.py.

import os
import subprocess
import time

import config
import estado


# ==========================================
#   SÍNTESIS Y CONVERSIÓN
# ==========================================

def sintetizar(texto_guion: str) -> bool:
    """
    Convierte el texto del guion en el archivo WAV maestro del stream.

    Flujo:
        1. Escribe el guion en ARCHIVO_TEXTO.
        2. Llama a edge-tts para generar ARCHIVO_TEMP_MP3.
        3. Convierte con sox a WAV 22050Hz mono → ARCHIVO_TEMP_WAV.
        4. Reemplaza atómicamente ARCHIVO_CLIMA con el nuevo WAV.
        5. Guarda una copia en CARPETA_HISTORIAL.

    Retorna True si todo el proceso fue exitoso, False en caso contrario.
    """
    try:
        # 1. Escribir guion al disco
        with open(config.ARCHIVO_TEXTO, "w", encoding="utf-8") as f:
            f.write(texto_guion)

        # 2. Síntesis edge-tts → MP3 temporal
        # Timeout de 90 s: edge-tts usa la API de Azure TTS vía red; sin timeout
        # una conexión colgada bloquea este hilo indefinidamente.
        cmd_tts = (
            f"edge-tts --voice {config.VOZ_TTS} "
            f"-f {config.ARCHIVO_TEXTO} "
            f"--write-media {config.ARCHIVO_TEMP_MP3}"
        )
        try:
            subprocess.run(cmd_tts, shell=True, stderr=subprocess.DEVNULL, timeout=90)
        except subprocess.TimeoutExpired:
            print(f"[TTS] - {estado.ts()} ❌ edge-tts superó el timeout (90 s). Abortando síntesis.")
            return False

        if not os.path.exists(config.ARCHIVO_TEMP_MP3):
            print(f"[TTS] - {estado.ts()} ❌ edge-tts no generó el archivo MP3.")
            return False

        # 3. Conversión sox: MP3 → WAV 22050Hz mono
        # Timeout de 60 s: sox es local pero puede bloquearse si el MP3 está corrupto.
        cmd_sox = (
            f"sox '{config.ARCHIVO_TEMP_MP3}' "
            f"-t wav -r {config.SAMPLE_RATE} -c 1 "
            f"'{config.ARCHIVO_TEMP_WAV}'"
        )
        try:
            subprocess.run(cmd_sox, shell=True, stderr=subprocess.DEVNULL, timeout=60)
        except subprocess.TimeoutExpired:
            print(f"[TTS] - {estado.ts()} ❌ sox superó el timeout (60 s). Abortando síntesis.")
            return False

        if not os.path.exists(config.ARCHIVO_TEMP_WAV):
            print(f"[TTS] - {estado.ts()} ❌ sox no generó el archivo WAV.")
            return False

        # 4. Rotación atómica del archivo maestro
        os.replace(config.ARCHIVO_TEMP_WAV, config.ARCHIVO_CLIMA)

        # 5. Copia al historial
        if not os.path.exists(config.CARPETA_HISTORIAL):
            os.makedirs(config.CARPETA_HISTORIAL)
        timestamp_archivo = time.strftime("%Y%m%d_%H%M%S")
        ruta_historico = f"{config.CARPETA_HISTORIAL}/guion_{timestamp_archivo}.txt"
        with open(ruta_historico, "w", encoding="utf-8") as f_hist:
            f_hist.write(texto_guion)

        print(f"[TTS] - {estado.ts()} ✅ ¡Nuevo audio integral listo! Bajando bandera de espera.")
        return True

    except Exception as e:
        print(f"[TTS] - {estado.ts()} ❌ Error en la síntesis: {e}")
        return False
