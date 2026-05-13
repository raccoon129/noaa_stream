# sismo_utils.py — Utilidades: TTS de espera, guardado local, formato de fecha

import datetime
import json
import os
import subprocess

import config
import estado


# Nombres en español para formateo de fecha
_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
]


def fecha_espanol():
    """Retorna (hora_str, fecha_str) en español. Ej: ('11:00', 'Viernes 8 de Mayo de 2026')"""
    ahora = datetime.datetime.now()
    dia = _DIAS[ahora.weekday()]
    mes = _MESES[ahora.month - 1]
    hora = ahora.strftime("%H:%M")
    fecha = f"{dia} {ahora.day} de {mes} de {ahora.year}"
    return hora, fecha


def generar_audio_espera():
    """
    Genera el WAV corto de espera con TTS.
    Texto: 'Se ha emitido la alerta sísmica a las HH:MM, hoy FECHA.
    Nos encontramos en periodo de recolección de información del evento
    telúrico, por favor, espere.'
    Guarda como config.ARCHIVO_SISMO_ESPERA.
    """
    hora, fecha = fecha_espanol()
    texto = (
        f"Se ha emitido la alerta sísmica a las {hora}, hoy {fecha}. "
        "Nos encontramos en periodo de recolección de información del evento "
        "telúrico, por favor, espere."
    )

    try:
        # Escribir texto temporal
        with open("_espera_tmp.txt", "w", encoding="utf-8") as f:
            f.write(texto)

        # edge-tts → MP3
        cmd_tts = (
            f"edge-tts --voice {config.VOZ_TTS} "
            f"-f _espera_tmp.txt "
            f"--write-media _espera_tmp.mp3"
        )
        subprocess.run(cmd_tts, shell=True, stderr=subprocess.DEVNULL)

        if not os.path.exists("_espera_tmp.mp3"):
            print(f"[SISMO] - {estado.ts()} ⚠️ No se pudo generar audio de espera")
            return False

        # sox → WAV
        cmd_sox = (
            f"sox '_espera_tmp.mp3' "
            f"-t wav -r {config.SAMPLE_RATE} -c 1 "
            f"'{config.ARCHIVO_SISMO_ESPERA}'"
        )
        subprocess.run(cmd_sox, shell=True, stderr=subprocess.DEVNULL)

        # Limpieza
        for tmp in ["_espera_tmp.txt", "_espera_tmp.mp3"]:
            if os.path.exists(tmp):
                os.remove(tmp)

        if os.path.exists(config.ARCHIVO_SISMO_ESPERA):
            print(f"[SISMO] - {estado.ts()} ✅ Audio de espera generado")
            return True

        return False

    except Exception as e:
        print(f"[SISMO] - {estado.ts()} ⚠️ Error generando audio de espera: {e}")
        return False


def guardar_datos_locales(datos):
    """Guarda el dict de datos sísmicos como JSON local para consulta rápida."""
    try:
        datos_guardar = datos.copy()
        datos_guardar["timestamp_guardado"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(config.ARCHIVO_SISMO_LOCAL, "w", encoding="utf-8") as f:
            json.dump(datos_guardar, f, ensure_ascii=False, indent=2)
        print(f"[SISMO] - {estado.ts()} ✅ Datos guardados localmente en {config.ARCHIVO_SISMO_LOCAL}")
    except Exception as e:
        print(f"[SISMO] - {estado.ts()} ⚠️ Error guardando JSON local: {e}")


def cargar_datos_locales():
    """Carga el JSON local del último sismo, o retorna None."""
    try:
        if os.path.exists(config.ARCHIVO_SISMO_LOCAL):
            with open(config.ARCHIVO_SISMO_LOCAL, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return None
