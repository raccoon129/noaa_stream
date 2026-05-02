# rev 15.1.4
# rev anterior: rev 15.1.3
# Changelog:
#   15.1.4 — Banner de inicio actualizado: ya no referencia pi_fm_rds ni MHz.
#            Muestra ciudad y estado de BT según config.BT_HABILITADO.
#   15.1.3 — Se lanza el watchdog de dj.py al arrancar la estación para
#            detectar y recuperar caídas silenciosas del pipeline de audio.
#   15.1.0 — Se pasa el dict forecast a construir_prompt para integrar
#            los datos del pronóstico horario de Open-Meteo en el guion.
#   15.0.0 — Refactorización modular completa. Este archivo es el único punto
#            de entrada de la estación. Orquesta: recolección meteorológica
#            (meteorologo + conagua), construcción del prompt (prompt),
#            generación del guion (ia), síntesis de voz (tts), persistencia
#            en BD (bd) y el bucle de transmisión (dj).
#            La funcionalidad es idéntica a la rev 14.9.2.

import datetime
import os
import threading
import time

import schedule

import bd
import config
import conagua
import dj
import estado
import ia
import meteorologo
import prompt
import tts


# ==========================================
#   CICLO DE ACTUALIZACIÓN DEL REPORTE
# ==========================================

def actualizar_audio_clima():
    """
    Ciclo completo de actualización del reporte meteorológico:
        1. Recolecta datos de CONAGUA, OWM y Open-Meteo.
        2. Construye el paquete de datos y el JSON del monitor web.
        3. Construye el prompt para la IA.
        4. Genera el guion con Gemini/Groq.
        5. Sintetiza la voz y rota el archivo WAV maestro.
        6. Persiste el reporte, resumen y prompt en MySQL (hilo secundario).
    """
    estado.actualizando_clima = True
    print(f"\n[METEORÓLOGO] - {estado.ts()} 📡 Recolectando OWM + CONAGUA + Open-Meteo...")

    # Conexión compartida de auditoría para este ciclo completo
    conexion_auditoria = bd.obtener_conexion_bd()

    try:
        # --------------------------------------------------
        # 1. Recolección de fuentes
        # --------------------------------------------------

        # CONAGUA
        error_conagua  = None
        datos_conagua  = None
        try:
            datos_conagua = conagua.obtener_pronostico()
        except Exception as e_cna:
            error_conagua = bd._sanitizar_error(str(e_cna))

        if not datos_conagua:
            print(f"[SISTEMA] - {estado.ts()} ⚠️  CONAGUA no disponible. Se omitirá del guion actual.")
            bd.registrar_error_bd(
                conexion_auditoria, "CONAGUA",
                error_conagua or "Sin datos o respuesta vacía."
            )

        # OWM + Open-Meteo (meteorologo gestiona sus propios errores en BD)
        datos_met = meteorologo.recolectar(conexion_auditoria)
        owm       = datos_met["owm"]
        aqi       = datos_met["aqi"]

        # Extraer hoy y mañana de CONAGUA para uso posterior
        cna_hoy    = datos_conagua["hoy"]    if datos_conagua else None
        cna_manana = datos_conagua.get("manana") if datos_conagua else None

        # --------------------------------------------------
        # 2. Continuar solo si al menos UNA fuente respondió
        # --------------------------------------------------
        if not (owm or datos_conagua or aqi):
            print(f"[SISTEMA] - {estado.ts()} ❌ Todas las APIs fallaron. No se generará guion en este ciclo.")
            return

        # --------------------------------------------------
        # 3. Timestamp del ciclo
        # --------------------------------------------------
        fecha_exacta = time.strftime("%Y-%m-%d")
        hora_exacta  = time.strftime("%H:%M")

        # --------------------------------------------------
        # 4. JSON del monitor web
        # --------------------------------------------------
        datos_web = meteorologo.construir_datos_web(owm, cna_hoy, aqi, hora_exacta)
        meteorologo.volcar_datos_json(datos_web)

        # --------------------------------------------------
        # 5. Construcción del prompt
        # --------------------------------------------------
        texto_prompt = prompt.construir_prompt(datos_conagua, owm, aqi, datos_met["forecast"])

        # --------------------------------------------------
        # 6. Generación del guion con IA
        # --------------------------------------------------
        texto_guion, modelo_usado, error_gemini = ia.generar_guion(texto_prompt)

        if not texto_guion:
            bd.registrar_error_bd(
                conexion_auditoria, "GEMINI",
                error_gemini or "Ambos modelos fallaron."
            )

        # --------------------------------------------------
        # 7. Paquete de datos para MySQL
        # --------------------------------------------------
        datos_para_bd = {
            # Metadatos
            "fecha_reporte":      fecha_exacta,
            "hora_reporte":       hora_exacta,
            "timestamp_completo": f"{fecha_exacta} {hora_exacta}:00",
            "ciudad":             config.CIUDAD,

            # CONAGUA
            "cna_disponible":    1 if datos_conagua else 0,
            "cna_condicion":     cna_hoy.get("condicion")    if cna_hoy else None,
            "cna_temp_max":      cna_hoy.get("temp_max")     if cna_hoy else None,
            "cna_temp_min":      cna_hoy.get("temp_min")     if cna_hoy else None,
            "cna_prob_lluvia":   cna_hoy.get("prob_lluvia")  if cna_hoy else None,
            "cna_precipitacion": cna_hoy.get("precipitacion")if cna_hoy else None,
            "cna_viento":        cna_hoy.get("viento")       if cna_hoy else None,
            "cna_dir_viento":    cna_hoy.get("dir_viento")   if cna_hoy else None,
            "cna_rafagas":       cna_hoy.get("rafagas")      if cna_hoy else None,
            "cna_man_condicion": cna_manana.get("condicion") if cna_manana else None,
            "cna_man_temp_max":  cna_manana.get("temp_max")  if cna_manana else None,
            "cna_man_temp_min":  cna_manana.get("temp_min")  if cna_manana else None,

            # OWM
            "owm_disponible":   1 if owm else 0,
            "owm_temp_actual":  owm.get("temp")       if owm else None,
            "owm_sensacion":    owm.get("feels")      if owm else None,
            "owm_humedad":      owm.get("humedad")    if owm else None,
            "owm_condicion":    owm.get("desc")       if owm else None,
            "owm_visibilidad":  owm.get("visibilidad")if owm else None,
            "owm_lluvia_1h":    owm.get("lluvia_1h")  if owm else None,
            "owm_amanecer":     owm.get("amanecer")   if owm else None,
            "owm_atardecer":    owm.get("atardecer")  if owm else None,

            # Open-Meteo AQI
            "aqm_disponible":   1 if aqi else 0,
            "aqm_aqi":          aqi.get("aqi")   if aqi else None,
            "aqm_pm10":         aqi.get("pm10")  if aqi else None,
            "aqm_pm25":         aqi.get("pm25")  if aqi else None,
            "aqm_uv_index":     aqi.get("uv")    if aqi else None,
            "aqm_co":           aqi.get("co")    if aqi else None,
            "aqm_no2":          aqi.get("no2")   if aqi else None,
            "aqm_so2":          aqi.get("so2")   if aqi else None,
            "aqm_ozono":        aqi.get("ozono") if aqi else None,

            # Guion IA
            "guion_texto":     texto_guion,
            "modelo_ia_usado": modelo_usado,
            "guion_generado":  1 if texto_guion else 0,
        }

        # --------------------------------------------------
        # 8. Persistencia en BD (hilo secundario para no bloquear el audio)
        # --------------------------------------------------
        def _tarea_bd(datos_r, datos_w, p_texto):
            id_generado = bd.guardar_reporte_en_bd(datos_r)
            if id_generado:
                if datos_w:
                    bd.guardar_resumen_en_bd(datos_w, id_generado)
                bd.guardar_prompt_en_bd(id_generado, p_texto)

        hilo_bd = threading.Thread(
            target=_tarea_bd,
            args=(datos_para_bd, datos_web, texto_prompt),
            daemon=True,
        )
        hilo_bd.start()

        # --------------------------------------------------
        # 9. Síntesis de voz
        # --------------------------------------------------
        if texto_guion:
            print(f"[METEORÓLOGO] - {estado.ts()} Guion maestro redactado. Sintetizando voz ({config.VOZ_TTS})...")
            tts.sintetizar(texto_guion)
        else:
            print(f"[SISTEMA] - {estado.ts()} ❌ No se generó guion. No se actualizará el audio.")

    except Exception as e:
        print(f"[ERROR] - {estado.ts()} Fallo en la actualización del clima: {e}")
    finally:
        if conexion_auditoria and conexion_auditoria.is_connected():
            conexion_auditoria.close()
        estado.actualizando_clima = False


# ==========================================
#   GESTOR DE HORARIOS (SCHEDULER)
# ==========================================

def hilo_programador():
    """Registra todos los horarios programados y mantiene el scheduler corriendo."""
    for h in config.HORAS_PROGRAMADAS:
        schedule.every().day.at(h).do(actualizar_audio_clima)

    while True:
        schedule.run_pending()
        time.sleep(1)


# ==========================================
#   ARRANQUE INTERACTIVO
# ==========================================

def preguntar_arranque_inicial() -> bool:
    """
    Al arrancar, si la hora actual no coincide exactamente con alguno de los
    horarios programados, pregunta al operador si desea ejecutar el primer
    reporte ahora o esperar al próximo horario programado.

    Retorna True cuando el reporte debe ejecutarse (inmediatamente o al llegar
    el horario). Bloquea el hilo principal si el operador elige esperar.
    """
    ahora        = datetime.datetime.now()
    hhmm_actual  = ahora.strftime("%H:%M")

    # Si ya coincide con un horario programado, ejecutar de inmediato
    if hhmm_actual in config.HORAS_PROGRAMADAS:
        return True

    # Calcular el próximo horario programado
    proximo_dt = None
    for h in config.HORAS_PROGRAMADAS:
        hora_cand = datetime.datetime.strptime(h, "%H:%M").replace(
            year=ahora.year, month=ahora.month, day=ahora.day
        )
        if hora_cand <= ahora:
            hora_cand += datetime.timedelta(days=1)
        if proximo_dt is None or hora_cand < proximo_dt:
            proximo_dt = hora_cand

    espera_segundos = int((proximo_dt - ahora).total_seconds())
    espera_mins     = espera_segundos // 60
    espera_segs     = espera_segundos % 60
    proximo_str     = proximo_dt.strftime("%H:%M del %d/%m/%Y")

    print("")
    print("┌─────────────────────────────────────────────────────┐")
    print("│          NOAA HUICHAPAN — ARRANQUE INTERACTIVO      │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  Hora actual        : {hhmm_actual}                              │")
    print(f"│  Próximo horario    : {proximo_str}             │")
    print(f"│  Tiempo de espera   : {espera_mins}m {espera_segs:02d}s                         │")
    print("├─────────────────────────────────────────────────────┤")
    print("│  [1] Ejecutar reporte ahora                         │")
    print(f"│  [2] Esperar al próximo horario ({proximo_str}) │")
    print("└─────────────────────────────────────────────────────┘")

    while True:
        try:
            opcion = input("  Ingresa tu opción (1 o 2): ").strip()
            if opcion == "1":
                print(f"[SISTEMA] - {estado.ts()} ▶  Ejecutando reporte inmediato por decisión del operador.")
                return True
            elif opcion == "2":
                print(f"[SISTEMA] - {estado.ts()} ⏳ Entrando en modo espera. El reporte iniciará a las {proximo_str}.")
                while True:
                    restante = int((proximo_dt - datetime.datetime.now()).total_seconds())
                    if restante <= 0:
                        break
                    if restante % 60 == 0 or restante <= 60:
                        mins_r = restante // 60
                        segs_r = restante % 60
                        print(f"[RELOJ] - {estado.ts()} ⏳ Próximo reporte en {mins_r}m {segs_r:02d}s...")
                    time.sleep(1)
                print(f"[SISTEMA] - {estado.ts()} ▶  Hora alcanzada. Iniciando reporte programado.")
                return True
            else:
                print("  Opción inválida. Ingresa 1 o 2.")
        except (KeyboardInterrupt, EOFError):
            print(f"\n[SISTEMA] - {estado.ts()} Interrupción detectada. Ejecutando reporte inmediato.")
            return True


# ==========================================
#   INICIO DE LA ESTACIÓN
# ==========================================

def iniciar_estacion():
    salidas = f"Icecast + BT → {config.FRECUENCIA_FM} MHz" if config.BT_HABILITADO else "Icecast"
    print("=====================================================")
    print(f" INICIANDO RADIO NOAA STREAM — {config.CIUDAD}    ")
    print(f" Salidas: {salidas}                               ")
    print("=====================================================")

    # Crear carpetas necesarias si no existen
    if not os.path.exists(config.CARPETA_MUSICA):
        os.makedirs(config.CARPETA_MUSICA)

    # Inicializar el pipeline de audio
    dj.iniciar_o_reiniciar_stream()

    # Lanzar watchdog que detecta y recupera caídas silenciosas del pipeline
    dj.iniciar_watchdog(intervalo=15)

    # Pregunta de arranque interactivo
    ejecutar_ahora = preguntar_arranque_inicial()
    if ejecutar_ahora:
        actualizar_audio_clima()

    # Lanzar el hilo del scheduler
    hilo_reloj = threading.Thread(target=hilo_programador, daemon=True)
    hilo_reloj.start()

    # ---- Bucle principal del DJ ----
    contador_reportes  = 0
    contador_canciones = 0
    aviso_previo_mostrado = False

    while True:
        segundos_proximo = schedule.idle_seconds()
        if segundos_proximo is not None:
            if 0 <= segundos_proximo <= 120 and not aviso_previo_mostrado:
                mins = int(segundos_proximo // 60)
                segs = int(segundos_proximo % 60)
                print(f"\n[RELOJ] - {estado.ts()} ⏳ ¡Atención! El reporte actualizará en {mins}m y {segs}s.")
                aviso_previo_mostrado = True
            elif segundos_proximo > 120 or segundos_proximo < 0:
                aviso_previo_mostrado = False

        # Modo espera: el meteorólogo está trabajando
        if estado.actualizando_clima:
            contador_canciones += 1
            print(
                f"\n[DJ] - {estado.ts()} Modo espera activo. "
                f"Reproduciendo pista de espera (Canción total #{contador_canciones})"
            )
            pista = dj.obtener_pista_aleatoria()
            if pista:
                dj.inyectar_audio_al_stream(pista, es_espera=True)
            else:
                dj.transmitir_silencio(5, es_espera=True)
            continue

        # Modo normal: 3 repeticiones del reporte + 2 canciones
        reporte_interrumpido = False
        for i in range(3):
            if estado.actualizando_clima:
                reporte_interrumpido = True
                break
            contador_reportes += 1
            print(
                f"\n[DJ] - {estado.ts()} 🎙️  Transmitiendo Reporte NOAA "
                f"(Ciclo {i + 1}/3 | Total histórico: #{contador_reportes})"
            )
            dj.inyectar_audio_al_stream(config.ARCHIVO_CLIMA)
            dj.transmitir_silencio(1.0)

        if reporte_interrumpido:
            continue

        for j in range(2):
            if estado.actualizando_clima:
                break
            pista = dj.obtener_pista_aleatoria()
            if pista:
                contador_canciones += 1
                nombre_pista = os.path.basename(pista)
                print(
                    f"\n[DJ] - {estado.ts()} 🎵 Transmitiendo Música: {nombre_pista} "
                    f"(Ciclo {j + 1}/2 | Total histórico: #{contador_canciones})"
                )
                dj.inyectar_audio_al_stream(pista)
            else:
                dj.transmitir_silencio(1)


# ==========================================
#   PUNTO DE ENTRADA
# ==========================================

if __name__ == "__main__":
    iniciar_estacion()