# rev 15.1.1
# rev anterior: rev 15.1.0
# Changelog:
#   15.1.1 — Corrección bug FM_HABILITADO=False: con FM apagado, ffmpeg ahora
#            lee PCM raw directamente desde stdin (-f s16le) sin pasar por sox,
#            eliminando la ambigüedad del header WAV en el pipeline.
#            pkill de ffmpeg corregido a sudo pkill para matar procesos
#            lanzados como root. Añadida pausa de 1s tras pkill para que
#            el SO libere el puerto de Icecast antes de reconectar.
#   15.1.0 — Anotaciones de tipo migradas a Optional de typing
#            para compatibilidad con Python 3.9 (Raspberry Pi OS).
#   15.0.0 — Extracción del motor de audio a módulo independiente.

import glob
import os
import random
import subprocess
import wave
from typing import Optional

import config
import estado


# ==========================================
#   CONSTRUCCIÓN DEL COMANDO DE STREAM
# ==========================================

def _construir_comando_stream():
    """
    Construye el comando de pipeline de audio según la configuración.

    Cuando FM_HABILITADO = True:
        sox raw → tee → (pi_fm_rds FM local) + (ffmpeg → Icecast)

    Cuando FM_HABILITADO = False:
        sox raw → ffmpeg → Icecast   (sin bifurcación FM)

    El pipeline siempre recibe PCM raw signed-16bit 22050Hz mono por stdin.
    """
    icecast_url = (
        "icecast://{user}:{pwd}@{host}:{port}{mount}".format(
            user=config.ICECAST_USER,
            pwd=config.ICECAST_PASSWORD,
            host=config.ICECAST_HOST,
            port=config.ICECAST_PORT,
            mount=config.ICECAST_MOUNTPOINT,
        )
    )

    if config.FM_HABILITADO:
        # -------------------------------------------------------
        # Modo FM + Icecast:
        #   sox convierte PCM raw → WAV en stdout
        #   tee bifurca: una copia a pi_fm_rds, otra a ffmpeg → Icecast
        # -------------------------------------------------------
        sox_raw_to_wav = (
            "sox -t raw -r {rate} -e signed -b 16 -c 1 - -t wav -".format(
                rate=config.SAMPLE_RATE
            )
        )
        ffmpeg_desde_wav = (
            "ffmpeg -hide_banner -loglevel error -i - "
            "-c:a libmp3lame -b:a {bitrate}k "
            "-ac 1 -content_type audio/mpeg -f mp3 "
            "{url}".format(bitrate=config.ICECAST_BITRATE_K, url=icecast_url)
        )
        fm_cmd = (
            "sudo {exe} -freq {freq} -audio - "
            '-ps "{ps}" -rt "{rt}"'.format(
                exe=config.FM_EJECUTABLE,
                freq=config.FRECUENCIA_FM,
                ps=config.FM_PS,
                rt=config.FM_RT,
            )
        )
        return (
            "{sox} | "
            "tee >({fm}) | "
            "{ffmpeg}".format(sox=sox_raw_to_wav, fm=fm_cmd, ffmpeg=ffmpeg_desde_wav)
        )
    else:
        # -------------------------------------------------------
        # Modo solo Icecast (sin FM):
        #   ffmpeg lee PCM raw directamente desde stdin, sin sox
        #   de por medio. Elimina la ambigüedad del header WAV y
        #   simplifica el pipeline a un único proceso.
        # -------------------------------------------------------
        return (
            "ffmpeg -hide_banner -loglevel error "
            "-f s16le -ar {rate} -ac 1 -i - "
            "-c:a libmp3lame -b:a {bitrate}k "
            "-ac 1 -content_type audio/mpeg -f mp3 "
            "{url}".format(
                rate=config.SAMPLE_RATE,
                bitrate=config.ICECAST_BITRATE_K,
                url=icecast_url,
            )
        )


# ==========================================
#   INICIALIZACIÓN / AUTO-RECUPERACIÓN DEL STREAM
# ==========================================

def iniciar_o_reiniciar_stream():
    """
    Crea o reinicia la tubería de audio completa.
    Mata los procesos previos y abre un nuevo Popen.
    Actualiza estado.flujo_radio con la nueva referencia.
    """
    print(f"\n[SISTEMA] - {estado.ts()} 🔄 Inicializando/Reiniciando tubería de transmisión...")

    # Terminar pipeline anterior si existe
    try:
        if estado.flujo_radio:
            estado.flujo_radio.terminate()
    except Exception:
        pass

    # Matar procesos huérfanos.
    # Se usa sudo en ambos pkill porque el script se ejecuta como root
    # (sudo python3) y los procesos hijo heredan ese UID. Sin sudo,
    # pkill no puede señalar procesos root desde un contexto no root.
    if config.FM_HABILITADO:
        subprocess.run("sudo pkill -f pi_fm_rds", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run("sudo pkill -f ffmpeg", shell=True, stderr=subprocess.DEVNULL)

    # Pausa breve para que el SO libere el puerto de Icecast antes de
    # que ffmpeg intente reconectarse
    import time as _time
    _time.sleep(1)

    comando = _construir_comando_stream()

    estado.flujo_radio = subprocess.Popen(
        comando,
        shell=True,
        executable="/bin/bash",
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# ==========================================
#   TRANSMISIÓN DE SILENCIO
# ==========================================

def transmitir_silencio(segundos, es_espera=False):
    """
    Inyecta muestras de silencio PCM al stream durante los segundos indicados.
    Se interrumpe si cambia el modo (espera <-> transmisión normal).
    """
    try:
        frames_totales  = int(config.SAMPLE_RATE * segundos)
        chunk           = config.SAMPLE_RATE // 2   # bloques de 0.5 s
        frames_escritos = 0

        while frames_escritos < frames_totales:
            if not es_espera and estado.actualizando_clima:
                break
            if es_espera and not estado.actualizando_clima:
                break

            frames_a_escribir = min(chunk, frames_totales - frames_escritos)
            estado.flujo_radio.stdin.write(b"\x00" * (frames_a_escribir * 2))
            estado.flujo_radio.stdin.flush()
            frames_escritos += frames_a_escribir

    except Exception as e:
        if _es_broken_pipe(e):
            print(f"[ERROR] - {estado.ts()} ⚠️  Stream roto (Broken Pipe). Intentando auto-recuperación...")
            iniciar_o_reiniciar_stream()
        else:
            print(f"[ERROR] - {estado.ts()} Stream cortado: {e}")


# ==========================================
#   INYECCIÓN DE ARCHIVO WAV AL STREAM
# ==========================================

def inyectar_audio_al_stream(ruta_archivo, es_espera=False):
    """
    Lee un archivo WAV y escribe sus frames PCM al stdin del stream.
    Se interrumpe si cambia el modo (espera <-> transmisión normal).
    Gestiona Broken Pipe con auto-recuperación.
    """
    if not os.path.exists(ruta_archivo):
        print(f"[DJ] - {estado.ts()} ⚠️  Archivo no encontrado: {ruta_archivo}")
        transmitir_silencio(2)
        return

    try:
        with wave.open(ruta_archivo, "rb") as w:
            chunk = config.SAMPLE_RATE // 2   # bloques de 0.5 s
            while True:
                if not es_espera and estado.actualizando_clima:
                    break
                if es_espera and not estado.actualizando_clima:
                    break

                pcm_data = w.readframes(chunk)
                if not pcm_data:
                    break

                estado.flujo_radio.stdin.write(pcm_data)
                estado.flujo_radio.stdin.flush()

    except Exception as e:
        if _es_broken_pipe(e):
            print(
                f"[DJ] - {estado.ts()} ⚠️  Error crítico de tubería (Broken Pipe) "
                f"con {ruta_archivo}. Reiniciando stream..."
            )
            iniciar_o_reiniciar_stream()
        else:
            print(f"[DJ] - {estado.ts()} ⚠️  Error al inyectar {ruta_archivo}: {e}")
            transmitir_silencio(2)


# ==========================================
#   SELECCIÓN MUSICAL ALEATORIA
# ==========================================

def obtener_pista_aleatoria():
    # type: () -> Optional[str]
    """
    Retorna la ruta de un archivo WAV aleatorio de la carpeta de música.
    Retorna None si la carpeta no existe o está vacía.
    """
    if not os.path.exists(config.CARPETA_MUSICA):
        os.makedirs(config.CARPETA_MUSICA)
        return None
    pistas = glob.glob("{0}/*.wav".format(config.CARPETA_MUSICA))
    return random.choice(pistas) if pistas else None


# ==========================================
#   UTILIDAD INTERNA
# ==========================================

def _es_broken_pipe(exc):
    """Detecta si una excepción corresponde a un Broken Pipe (errno 32)."""
    return (
        isinstance(exc, BrokenPipeError)
        or getattr(exc, "errno", None) == 32
        or "Broken pipe" in str(exc)
    )