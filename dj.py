# rev 15.2.0
# rev anterior: rev 15.1.4
# Changelog:
#   15.2.0 — Reemplazo de pi_fm_rds por salida de audio local vía Bluetooth.
#            _construir_comando_stream() ahora soporta dos modos:
#              BT_HABILITADO = True : tee bifurca el PCM crudo antes de sox.
#                Rama BT: sox (PCM→PCM resampled) | aplay en bucle autónomo.
#                Rama Icecast: sox (PCM→WAV) | ffmpeg → Icecast (idéntico al modo anterior).
#                La bifurcación en PCM crudo permite que aplay se reinicie
#                limpiamente tras desconexión BT sin depender del header WAV.
#              BT_HABILITADO = False: pipeline idéntico al anterior (sin FM ni BT).
#            iniciar_o_reiniciar_stream(): pkill pi_fm_rds reemplazado por pkill aplay.
#   15.1.4 — Watchdog reforzado: ahora verifica el mountpoint en Icecast via
#            HTTP (/status-json.xsl) además de poll(). Detecta cuando ffmpeg
#            muere internamente pero bash/sox siguen vivos. Requiere 2 fallos
#            consecutivos antes de reiniciar (evita falsos positivos por red).
#            ffmpeg ahora incluye -reconnect/-reconnect_streamed/-reconnect_delay_max
#            para reconexión automática a Icecast sin reiniciar el pipeline.
#   15.1.3 — Watchdog inicial con poll() solamente.
#   15.1.2 — Corrección bug de silencio entre pistas en modo sin FM:
#            sox se restaura como buffer de entrada en el pipeline sin FM
#            (sox PCM→WAV | ffmpeg→Icecast). El buffer interno de sox
#            suaviza las transiciones entre pistas y evita underruns
#            en ffmpeg al cambiar de archivo.
#   15.1.1 — pkill ffmpeg corregido a sudo pkill. Pausa 1s post-pkill.
#            Modo sin FM: ffmpeg leía PCM raw directo (revertido en 15.1.2).
#   15.1.0 — Anotaciones de tipo migradas a Optional de typing
#            para compatibilidad con Python 3.9 (Raspberry Pi OS).
#   15.0.0 — Extracción del motor de audio a módulo independiente.

import glob
import os
import random
import subprocess
import threading
import time
import wave
from typing import Optional
try:
    import urllib.request as _urllib
except ImportError:
    _urllib = None

import config
import estado


# ==========================================
#   CONSTRUCCIÓN DEL COMANDO DE STREAM
# ==========================================

def _construir_comando_stream():
    """
    Construye el comando de pipeline de audio según la configuración.

    Cuando BT_HABILITADO = True:
        El PCM crudo se bifurca con tee antes de cualquier conversión de formato,
        lo que permite que cada rama tenga su propio sox independiente:

        Rama BT (best-effort):
            sox (PCM→PCM, resamplea si BT_SAMPLE_RATE_SALIDA != SAMPLE_RATE)
            | while true; do aplay -t raw ...; sleep 2; done
            El bucle while permite que aplay se reinicie automáticamente si el
            transmisor FM BT se desconecta temporalmente. El formato explícito
            (-t raw) elimina la dependencia del header WAV, por lo que cada
            reinicio de aplay retoma el stream sin artefactos.

        Rama Icecast:
            sox (PCM→WAV) | ffmpeg → Icecast
            Idéntica al modo sin BT; no se ve afectada por el estado del BT.

    Cuando BT_HABILITADO = False:
        sox raw → WAV → ffmpeg → Icecast   (sin bifurcación; idéntico al modo anterior)

    El pipeline siempre recibe PCM raw signed-16bit mono a SAMPLE_RATE Hz por stdin.
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

    # Conversión PCM→WAV para la rama Icecast (buffer de sox suaviza transiciones)
    sox_a_wav = (
        "sox -t raw -r {rate} -e signed -b 16 -c 1 - -t wav -".format(
            rate=config.SAMPLE_RATE
        )
    )
    ffmpeg_a_icecast = (
        "ffmpeg -hide_banner -loglevel error "
        "-re -i - "
        "-c:a libmp3lame -b:a {bitrate}k "
        "-ac 1 -content_type audio/mpeg -f mp3 "
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 "
        "{url}".format(bitrate=config.ICECAST_BITRATE_K, url=icecast_url)
    )

    if config.BT_HABILITADO:
        # -------------------------------------------------------
        # Modo BT + Icecast:
        #   tee bifurca el PCM crudo (antes de sox) en dos ramas independientes.
        #   La bifurcación en crudo evita que un reinicio de aplay necesite
        #   el header WAV; sox de la rama BT entrega PCM con formato explícito.
        # -------------------------------------------------------

        # sox de la rama BT: PCM→PCM (resamplea solo si el rate difiere)
        sox_a_pcm_bt = (
            "sox -t raw -r {sr_in} -e signed -b 16 -c 1 - "
            "-t raw -r {sr_out} -e signed -b 16 -c 1 -".format(
                sr_in=config.SAMPLE_RATE,
                sr_out=config.BT_SAMPLE_RATE_SALIDA,
            )
        )
        # aplay con formato explícito: no depende del header WAV para iniciar
        aplay_bt = (
            "aplay -D {dispositivo} -t raw -f S16_LE -r {rate} -c 1".format(
                dispositivo=config.BT_DISPOSITIVO,
                rate=config.BT_SAMPLE_RATE_SALIDA,
            )
        )
        # Bucle de resiliencia: si el transmisor BT se desconecta, aplay
        # se reinicia automáticamente cada 2 s sin afectar la rama Icecast
        rama_bt = (
            "{sox_bt} | while true; do {aplay}; sleep 2; done".format(
                sox_bt=sox_a_pcm_bt,
                aplay=aplay_bt,
            )
        )
        return (
            "tee >({rama_bt}) | "
            "{sox_wav} | "
            "{ffmpeg}".format(
                rama_bt=rama_bt,
                sox_wav=sox_a_wav,
                ffmpeg=ffmpeg_a_icecast,
            )
        )
    else:
        # -------------------------------------------------------
        # Modo solo Icecast (sin BT):
        #   sox actúa como buffer de entrada (PCM raw → WAV stdout).
        #   ffmpeg toma el WAV y publica en Icecast.
        #   El buffer interno de sox (~32KB por defecto) suaviza
        #   las transiciones entre pistas y evita underruns en
        #   ffmpeg cuando el DJ cambia de archivo.
        # -------------------------------------------------------
        return "{sox} | {ffmpeg}".format(sox=sox_a_wav, ffmpeg=ffmpeg_a_icecast)


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
    if config.BT_HABILITADO:
        subprocess.run("sudo pkill -f aplay", shell=True, stderr=subprocess.DEVNULL)
    subprocess.run("sudo pkill -f ffmpeg", shell=True, stderr=subprocess.DEVNULL)

    # Pausa breve para que el SO libere el puerto de Icecast antes de
    # que ffmpeg intente reconectarse
    time.sleep(1)

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

def transmitir_silencio(segundos, es_espera=False, es_alarma=False):
    """
    Inyecta muestras de silencio PCM al stream durante los segundos indicados
    respetando el tempo real mediante rate-limiting explícito.
    Se interrumpe si cambia el modo (espera <-> transmisión normal) o si hay alerta sísmica.
    """
    try:
        frames_totales  = int(config.SAMPLE_RATE * segundos)
        chunk           = config.SAMPLE_RATE // 2   # bloques de 0.5 s
        frames_escritos = 0

        while frames_escritos < frames_totales:
            if not es_alarma and estado.alerta_sismica:
                break
            if not es_espera and estado.actualizando_clima:
                break
            if es_espera and not estado.actualizando_clima:
                break

            t_inicio          = time.monotonic()
            frames_a_escribir = min(chunk, frames_totales - frames_escritos)
            estado.flujo_radio.stdin.write(b"\x00" * (frames_a_escribir * 2))
            estado.flujo_radio.stdin.flush()
            frames_escritos  += frames_a_escribir

            # Rate-limiting: respetar el tempo real del silencio
            duracion_chunk = frames_a_escribir / config.SAMPLE_RATE
            transcurrido   = time.monotonic() - t_inicio
            pausa          = duracion_chunk - transcurrido
            if pausa > 0:
                time.sleep(pausa)

    except Exception as e:
        if _es_broken_pipe(e):
            print(f"[ERROR] - {estado.ts()} ⚠️  Stream roto (Broken Pipe). Intentando auto-recuperación...")
            iniciar_o_reiniciar_stream()
        else:
            print(f"[ERROR] - {estado.ts()} Stream cortado: {e}")


# ==========================================
#   INYECCIÓN DE ARCHIVO WAV AL STREAM
# ==========================================

def inyectar_audio_al_stream(ruta_archivo, es_espera=False, es_alarma=False):
    """
    Lee un archivo WAV y escribe sus frames PCM al stdin del stream
    respetando el tempo real del audio mediante rate-limiting explícito.

    Sin rate-limiting, Python escribe todos los frames al pipe del SO
    en microsegundos (I/O de memoria), lo que hace que sox/ffmpeg los
    consuman y transmitan a velocidad descontrolada. El rate-limiting
    garantiza que cada chunk de audio se escribe aproximadamente en el
    tiempo que le correspondería reproducirse en tiempo real.

    Se interrumpe si cambia el modo o si entra alerta sísmica.
    Gestiona Broken Pipe con auto-recuperación.
    """
    if not os.path.exists(ruta_archivo):
        print(f"[DJ] - {estado.ts()} ⚠️  Archivo no encontrado: {ruta_archivo}")
        transmitir_silencio(2)
        return

    try:
        with wave.open(ruta_archivo, "rb") as w:
            framerate = w.getframerate()   # sample rate real del archivo
            ncanales  = w.getnchannels()
            sampwidth = w.getsampwidth()
            chunk     = framerate // 2     # bloques de 0.5 s en la frecuencia real del archivo

            while True:
                if not es_alarma and estado.alerta_sismica:
                    break
                if not es_espera and estado.actualizando_clima:
                    break
                if es_espera and not estado.actualizando_clima:
                    break

                t_inicio = time.monotonic()
                pcm_data = w.readframes(chunk)
                if not pcm_data:
                    break

                estado.flujo_radio.stdin.write(pcm_data)
                estado.flujo_radio.stdin.flush()

                # Calcular cuánto tiempo debería haber durado este chunk
                # frames_leidos = bytes / (canales * bytes_por_muestra)
                frames_leidos   = len(pcm_data) // (ncanales * sampwidth)
                duracion_chunk  = frames_leidos / framerate
                transcurrido    = time.monotonic() - t_inicio
                pausa           = duracion_chunk - transcurrido
                if pausa > 0:
                    time.sleep(pausa)

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
#   WATCHDOG DE PIPELINE
# ==========================================

def _icecast_stream_activo():
    """
    Consulta el endpoint JSON de estado de Icecast para verificar si el
    mountpoint configurado tiene oyentes o al menos está montado y activo.

    Retorna True si el mountpoint responde correctamente, False si no
    aparece en el estado de Icecast o si Icecast no responde.
    Este chequeo es más fiable que poll() porque detecta cuando ffmpeg
    muere internamente pero bash/sox siguen vivos.
    """
    if _urllib is None:
        return True  # Sin urllib no podemos verificar; asumir activo

    url = "http://{host}:{port}/status-json.xsl".format(
        host=config.ICECAST_HOST,
        port=config.ICECAST_PORT,
    )
    try:
        req = _urllib.urlopen(url, timeout=5)
        datos = req.read().decode("utf-8", errors="ignore")
        # El mountpoint configurado debe aparecer en la respuesta JSON
        return config.ICECAST_MOUNTPOINT in datos
    except Exception:
        # Icecast no responde en absoluto — también es fallo
        return False


def _watchdog_stream(intervalo=15):
    """
    Hilo demonio que verifica cada `intervalo` segundos la salud real
    del pipeline de audio usando dos estrategias complementarias:

    1. poll() sobre flujo_radio: detecta si el proceso bash padre cayó.
    2. Consulta HTTP al endpoint de estado de Icecast: detecta cuando
       ffmpeg murió internamente pero bash/sox siguen vivos, o cuando
       la conexión a Icecast se cortó silenciosamente.

    Si cualquiera de las dos falla, reinicia el pipeline completo.
    No actúa mientras actualizando_clima sea True.
    """
    # Espera inicial para dejar que el pipeline arranque antes del primer chequeo
    time.sleep(intervalo * 2)

    fallos_consecutivos = 0
    MAX_FALLOS = 2   # Reiniciar solo si falla N veces seguidas (evita falsos positivos)

    while True:
        time.sleep(intervalo)
        if estado.actualizando_clima or estado.alerta_sismica:
            fallos_consecutivos = 0
            continue

        try:
            proceso_muerto = (
                estado.flujo_radio is None
                or estado.flujo_radio.poll() is not None
            )
            stream_caido = not _icecast_stream_activo()

            if proceso_muerto or stream_caido:
                fallos_consecutivos += 1
                causa = "proceso muerto" if proceso_muerto else "stream Icecast inactivo"
                print(
                    f"[WATCHDOG] - {estado.ts()} ⚠️  Fallo detectado: {causa} "
                    f"({fallos_consecutivos}/{MAX_FALLOS})"
                )
                if fallos_consecutivos >= MAX_FALLOS:
                    print(
                        f"\n[WATCHDOG] - {estado.ts()} 🔄 Reiniciando pipeline "
                        f"tras {MAX_FALLOS} fallos consecutivos..."
                    )
                    iniciar_o_reiniciar_stream()
                    fallos_consecutivos = 0
            else:
                # Stream saludable — resetear contador
                fallos_consecutivos = 0

        except Exception as e:
            print(f"[WATCHDOG] - {estado.ts()} ⚠️  Error en watchdog: {e}")


def iniciar_watchdog(intervalo=15):
    """
    Lanza el hilo watchdog como demonio.
    Debe llamarse una sola vez desde noaa_str.py al arrancar la estación.
    """
    hilo = threading.Thread(
        target=_watchdog_stream,
        args=(intervalo,),
        daemon=True,
        name="watchdog-stream"
    )
    hilo.start()
    print(f"[WATCHDOG] - {estado.ts()} ✅ Watchdog de pipeline iniciado (intervalo: {intervalo}s)")


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