# rev 15.3.0
# rev anterior: rev 15.2.0
# Changelog:
#   15.3.0 — Diagnóstico de fallos de síntesis: se captura y se imprime en
#            consola el stderr/stdout completo, el returncode y el tamaño de
#            los archivos de edge-tts y sox (antes se descartaba con DEVNULL).
#            Se valida returncode y tamaño > 0 del MP3 en lugar de solo su
#            existencia. edge-tts se reintenta (3 intentos). Los temporales
#            NO se borran para poder inspeccionarlos tras un fallo.
#   15.2.0 — Se elimina el guardado de copias históricas de guiones en
#            CARPETA_HISTORIAL. El historial queda exclusivamente en la BD
#            (tabla reportes_climatologicos). Se conserva ARCHIVO_TEXTO
#            (guion.txt) porque edge-tts lo necesita como entrada en cada
#            ciclo de síntesis.
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

INTENTOS_EDGE_TTS = 3
ESPERA_ENTRE_INTENTOS = 5  # segundos


def _tam(ruta: str) -> str:
    """Devuelve el tamaño en bytes del archivo o 'no existe'."""
    try:
        return f"{os.path.getsize(ruta)} bytes"
    except OSError:
        return "no existe"


def _volcar_error(etiqueta: str, cmd: list, res) -> None:
    """Imprime en consola el detalle completo de un subproceso fallido."""
    print(f"[TTS] - {estado.ts()} ❌ {etiqueta} falló (returncode={res.returncode})")
    print(f"[TTS]   Comando: {' '.join(cmd)}")
    print(f"[TTS]   Directorio de trabajo: {os.getcwd()}")
    if res.stdout:
        print(f"[TTS]   --- stdout ---\n{res.stdout}")
    if res.stderr:
        print(f"[TTS]   --- stderr ---\n{res.stderr}")


# ==========================================
#   SÍNTESIS Y CONVERSIÓN
# ==========================================

def sintetizar(texto_guion: str) -> bool:
    """
    Convierte el texto del guion en el archivo WAV maestro del stream.

    Flujo:
        1. Escribe el guion en ARCHIVO_TEXTO (requerido por edge-tts).
        2. Llama a edge-tts para generar ARCHIVO_TEMP_MP3.
        3. Convierte con sox a WAV 22050Hz mono → ARCHIVO_TEMP_WAV.
        4. Reemplaza atómicamente ARCHIVO_CLIMA con el nuevo WAV.

    El historial de guiones se persiste en la BD (reportes_climatologicos),
    no en disco. ARCHIVO_TEXTO se sobreescribe en cada ciclo.

    Retorna True si todo el proceso fue exitoso, False en caso contrario.
    """
    try:
        # 1. Escribir guion al disco
        with open(config.ARCHIVO_TEXTO, "w", encoding="utf-8") as f:
            f.write(texto_guion)

        # 2. Síntesis edge-tts → MP3 temporal
        # Timeout de 90 s: edge-tts usa la API de Azure TTS vía red; sin timeout
        # una conexión colgada bloquea este hilo indefinidamente.
        cmd_tts = [
            "edge-tts",
            "--voice", str(config.VOZ_TTS),
            "-f", str(config.ARCHIVO_TEXTO),
            "--write-media", str(config.ARCHIVO_TEMP_MP3),
        ]
        mp3_ok = False
        for intento in range(1, INTENTOS_EDGE_TTS + 1):
            try:
                res = subprocess.run(
                    cmd_tts, capture_output=True, text=True, timeout=90
                )
            except subprocess.TimeoutExpired:
                print(f"[TTS] - {estado.ts()} ❌ edge-tts superó el timeout (90 s) "
                      f"(intento {intento}/{INTENTOS_EDGE_TTS}).")
                res = None
            except FileNotFoundError as e:
                print(f"[TTS] - {estado.ts()} ❌ No se encontró el ejecutable edge-tts: {e}")
                print(f"[TTS]   PATH: {os.environ.get('PATH')}")
                return False

            if res is not None:
                tam_mp3 = _tam(config.ARCHIVO_TEMP_MP3)
                if res.returncode == 0 and os.path.exists(config.ARCHIVO_TEMP_MP3) \
                        and os.path.getsize(config.ARCHIVO_TEMP_MP3) > 0:
                    mp3_ok = True
                    break
                _volcar_error(f"edge-tts (intento {intento}/{INTENTOS_EDGE_TTS})", cmd_tts, res)
                print(f"[TTS]   MP3 temporal: {tam_mp3}")

            if intento < INTENTOS_EDGE_TTS:
                print(f"[TTS] - {estado.ts()} ⏳ Reintentando edge-tts en {ESPERA_ENTRE_INTENTOS} s...")
                time.sleep(ESPERA_ENTRE_INTENTOS)

        if not mp3_ok:
            print(f"[TTS] - {estado.ts()} ❌ edge-tts no generó un MP3 válido tras "
                  f"{INTENTOS_EDGE_TTS} intentos. Abortando síntesis.")
            return False

        # 3. Conversión sox: MP3 → WAV 22050Hz mono
        # Timeout de 60 s: sox es local pero puede bloquearse si el MP3 está corrupto.
        cmd_sox = [
            "sox", str(config.ARCHIVO_TEMP_MP3),
            "-t", "wav", "-r", str(config.SAMPLE_RATE), "-c", "1",
            str(config.ARCHIVO_TEMP_WAV),
        ]
        try:
            res = subprocess.run(cmd_sox, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            print(f"[TTS] - {estado.ts()} ❌ sox superó el timeout (60 s). Abortando síntesis.")
            return False
        except FileNotFoundError as e:
            print(f"[TTS] - {estado.ts()} ❌ No se encontró el ejecutable sox: {e}")
            return False

        if res.returncode != 0 or not os.path.exists(config.ARCHIVO_TEMP_WAV):
            _volcar_error("sox", cmd_sox, res)
            print(f"[TTS]   MP3 de entrada: {_tam(config.ARCHIVO_TEMP_MP3)}")
            print(f"[TTS]   WAV de salida:  {_tam(config.ARCHIVO_TEMP_WAV)}")
            print(f"[TTS] - {estado.ts()} ❌ sox no generó el archivo WAV.")
            return False

        # 4. Rotación atómica del archivo maestro
        os.replace(config.ARCHIVO_TEMP_WAV, config.ARCHIVO_CLIMA)

        print(f"[TTS] - {estado.ts()} ✅ ¡Nuevo audio integral listo! Bajando bandera de espera.")
        return True

    except Exception as e:
        print(f"[TTS] - {estado.ts()} ❌ Error en la síntesis: {e}")
        return False
