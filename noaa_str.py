# rev 16.6.0
# rev anterior: rev 16.5.0
# Changelog:
#   16.6.0 — Se integran las estaciones solares USNO: obtener_estaciones_solares()
#            se llama una sola vez en iniciar_estacion(); en cada ciclo se calcula
#            el evento cercano con obtener_evento_solar_cercano() y se pasa a
#            construir_prompt() como evento_solar (FUENTE 7 en el prompt).
# Changelog:
#   16.4.0 — Se pasa lunar en datos_para_bd para persistencia en MySQL.
#   16.3.0 — Se migra la fuente de fase lunar a USNO (U.S. Naval Observatory), pasándola
#            como parámetro desde datos_met a prompt.construir_prompt().
#   16.2.0 — Se extrae lunar de datos_met y se pasa a prompt.construir_prompt()
#            como parámetro para que la FUENTE 5 (fase lunar) se incluya en el
#            prompt en horario nocturno.
#   16.1.0 — Se retira conagua.obtener_pronostico_horario() (method=3 suspendido
#            por rendimiento en hardware). Se elimina rocio_relevante. modo_nocturno
#            se conserva: se calcula desde sunset_ts de OWM y controla la perspectiva
#            ampliada de mañana en el prompt (CONAGUA method=1 sigue activo).
#   16.0.0 — Llama a method=3, calcula modo_nocturno y rocio_relevante desde OWM.
#   15.1.5 — datos_para_bd reestructurado para el esquema normalizado por fuente.

import datetime
import json
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
import sismo
import ssn_rss
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

        # CONAGUA diario (method=1)
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

        # OWM + Open-Meteo + Fase Lunar (meteorologo gestiona sus propios errores en BD)
        datos_met = meteorologo.recolectar(conexion_auditoria)
        owm       = datos_met["owm"]
        aqi       = datos_met["aqi"]
        lunar     = datos_met.get("lunar")

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
        # 3. Timestamp + flags modo_nocturno y rocio_relevante
        # --------------------------------------------------
        fecha_exacta = time.strftime("%Y-%m-%d")
        hora_exacta  = time.strftime("%H:%M")

        modo_nocturno = False
        if owm:
            import datetime as _dt
            ahora_ts  = _dt.datetime.now().timestamp()
            sunset_ts = owm.get("sunset_ts")
            if sunset_ts:
                modo_nocturno = ahora_ts >= sunset_ts

        # --------------------------------------------------
        # 4. JSON del monitor web
        # --------------------------------------------------
        datos_web = meteorologo.construir_datos_web(owm, cna_hoy, aqi, hora_exacta)
        meteorologo.volcar_datos_json(datos_web)
        print(f"[SISTEMA] - {estado.ts()} 🌐 datos.json actualizado ({hora_exacta}).")

        # --------------------------------------------------
        # 4.5  SSN RSS — Sismos HGO
        # --------------------------------------------------
        print(f"[SSN] - {estado.ts()} 📡 Consultando RSS del Servicio Sismológico Nacional...")
        ssn_rss.actualizar_sismos_hgo(conexion_auditoria)
        eventos_ssn = ssn_rss.obtener_eventos_para_reporte(hora_exacta)
        print(f"[SSN] - {estado.ts()} ✅ RSS SSN procesado ({len(eventos_ssn)} evento(s) relevante(s) para el reporte).")

        # --------------------------------------------------
        # 4.6  Estaciones solares — evento cercano (FUENTE 7)
        # --------------------------------------------------
        # Solo computa proximidad; la caché ya fue cargada al arrancar.
        evento_solar = meteorologo.obtener_evento_solar_cercano()

        # Guardar en BD únicamente el día que ocurre el evento (dias_al_evento == 0)
        if evento_solar and evento_solar.get("dias_al_evento") == 0:
            clave_bd = "{phenom}|{fecha}".format(
                phenom=evento_solar.get("phenom", ""),
                fecha=str(evento_solar.get("fecha_dt", "")),
            )
            if clave_bd not in estado.estaciones_guardadas_bd:
                bd.guardar_condicion_especial({
                    "timestamp_evento": "{} {}".format(
                        evento_solar["fecha_dt"], evento_solar.get("hora_local", "00:00") + ":00"
                    ),
                    "tipo":             "EVENTO_SOLAR_USNO",
                    "subtipo":          evento_solar.get("phenom"),
                    "descripcion":      "{} — {}".format(
                        evento_solar.get("nombre_es", ""),
                        evento_solar.get("significado", ""),
                    ),
                    "ubicacion":        None,
                    "latitud":          None,
                    "longitud":         None,
                    "fuente_alerta":    "USNO_SEASONS",
                    "datos_fuente_primaria": json.dumps({
                        "phenom":    evento_solar.get("phenom"),
                        "nombre_es": evento_solar.get("nombre_es"),
                        "year":      evento_solar.get("year"),
                        "month":     evento_solar.get("month"),
                        "day":       evento_solar.get("day"),
                        "hora_local": evento_solar.get("hora_local"),
                    }, ensure_ascii=False),
                    "datos_fuente_secundaria": None,
                    "datos_investigacion":     None,
                    "guion_inmediato":         None,
                    "prompt_inmediato":        None,
                    "guion_analisis":          None,
                    "prompt_analisis":         None,
                    "modelo_ia_usado":         None,
                })
                estado.estaciones_guardadas_bd.add(clave_bd)

        # --------------------------------------------------
        # 5. Construcción del prompt
        # --------------------------------------------------
        contexto = None
        if estado.sismo_activo and estado.ciclos_sismo_restantes > 0:
            contexto = sismo.enriquecer_con_apis()
        elif estado.sismo_activo:
            contexto = estado.datos_sismo
        texto_prompt = prompt.construir_prompt(
            datos_conagua, owm, aqi, datos_met["forecast"],
            contexto_sismo=contexto,
            modo_nocturno=modo_nocturno,
            lunar=lunar,
            eventos_ssn=eventos_ssn,
            evento_solar=evento_solar,
        )

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
        # 7. Paquete de datos para MySQL (esquema normalizado)
        # --------------------------------------------------
        datos_para_bd = {
            # Metadatos del reporte
            "fecha_reporte":      fecha_exacta,
            "hora_reporte":       hora_exacta,
            "timestamp_completo": f"{fecha_exacta} {hora_exacta}:00",
            "ciudad":             config.CIUDAD,

            # Guion IA
            "guion_texto":     texto_guion,
            "modelo_ia_usado": modelo_usado,
            "guion_generado":  1 if texto_guion else 0,

            # Sub-dict CONAGUA: None si no respondió → bd.py no insertará en datos_conagua
            "conagua": {
                "condicion":     cna_hoy.get("condicion")     if cna_hoy else None,
                "temp_max":      cna_hoy.get("temp_max")      if cna_hoy else None,
                "temp_min":      cna_hoy.get("temp_min")      if cna_hoy else None,
                "prob_lluvia":   cna_hoy.get("prob_lluvia")   if cna_hoy else None,
                "precipitacion": cna_hoy.get("precipitacion") if cna_hoy else None,
                "viento":        cna_hoy.get("viento")        if cna_hoy else None,
                "dir_viento":    cna_hoy.get("dir_viento")    if cna_hoy else None,
                "rafagas":       cna_hoy.get("rafagas")       if cna_hoy else None,
                "cc":            cna_hoy.get("cc")            if cna_hoy else None,
                "dirvieng":      cna_hoy.get("dirvieng")      if cna_hoy else None,
                "dloc":          cna_hoy.get("dloc")          if cna_hoy else None,

                "man_condicion":     cna_manana.get("condicion")     if cna_manana else None,
                "man_temp_max":      cna_manana.get("temp_max")      if cna_manana else None,
                "man_temp_min":      cna_manana.get("temp_min")      if cna_manana else None,
                "man_prob_lluvia":   cna_manana.get("prob_lluvia")   if cna_manana else None,
                "man_precipitacion": cna_manana.get("precipitacion") if cna_manana else None,
                "man_viento":        cna_manana.get("viento")        if cna_manana else None,
                "man_rafagas":       cna_manana.get("rafagas")       if cna_manana else None,
                "man_dir_viento":    cna_manana.get("dir_viento")    if cna_manana else None,
                "man_cc":            cna_manana.get("cc")            if cna_manana else None,
            } if datos_conagua else None,

            # Sub-dict OWM: None si no respondió → bd.py no insertará en datos_owm
            "owm": owm,

            # Sub-dict Open-Meteo AQI: None si no respondió → bd.py no insertará en datos_openmeteo
            "aqi": aqi,
            # Sub-dict Open-Meteo Forecast: None si falló (evita insertar forecast_vacio en BD)
            "forecast": datos_met.get("forecast") if datos_met.get("disponible_fc") else None,

            # Sub-dict Fase Lunar (USNO)
            "lunar": datos_met.get("lunar") if datos_met.get("disponible_lunar") else None,
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
            if estado.alerta_sismica:
                print(f"[SISTEMA] - {estado.ts()} ⚠️  Alerta sísmica en curso. Se omite síntesis de audio.")
            else:
                print(f"[METEORÓLOGO] - {estado.ts()} Guion maestro redactado. Sintetizando voz ({config.VOZ_TTS})...")
                tts.sintetizar(texto_guion)
                # Gestión de ciclos de reporte de sismo
                if estado.sismo_activo:
                    if estado.sismo_intercalando:
                        estado.sismo_intercalando = False

                    # Persistir el guion de análisis generado en este ciclo de enriquecimiento
                    # → Se hace en hilo daemon para no bloquear el feed de Icecast/AUX
                    id_sismo = getattr(estado, "ultimo_id_sismo_bd", None)
                    if id_sismo and texto_guion:
                        campos_guion = {
                            "guion_analisis":  texto_guion,
                            "prompt_analisis": texto_prompt,
                            "modelo_ia_usado": modelo_usado,
                        }
                        def _persistir_guion_sismo(id_ev, campos):
                            bd.actualizar_condicion_especial(id_ev, campos)
                            bd.guardar_historial_condicion_especial(id_ev, campos)
                        threading.Thread(
                            target=_persistir_guion_sismo,
                            args=(id_sismo, campos_guion),
                            daemon=True,
                        ).start()

                    estado.ciclos_sismo_restantes -= 1
                    if estado.ciclos_sismo_restantes <= 0:
                        estado.sismo_activo = False
                        estado.datos_sismo = None
                        estado.ultimo_id_sismo_bd = None
                        print(f"[SISTEMA] - {estado.ts()} ✅ Evento sísmico finalizado. Volviendo a modo normal.")
                    else:
                        print(f"[SISTEMA] - {estado.ts()} ℹ️ Ciclos de enriquecimiento restantes: {estado.ciclos_sismo_restantes}")
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
    print("│          NOAA STREAM — ARRANQUE INTERACTIVO         │")
    print("├─────────────────────────────────────────────────────┤")
    print(f"│  Hora actual        : {hhmm_actual}                │")
    print(f"│  Próximo horario    : {proximo_str}                │")
    print(f"│  Tiempo de espera   : {espera_mins}m {espera_segs:02d}s       ")
    print("├─────────────────────────────────────────────────────┤")
    print("│  [1] Ejecutar reporte ahora                         │")
    print(f"│  [2] Esperar al próximo horario ({proximo_str})    │")
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
    salidas = f"Icecast + AUX → {config.FRECUENCIA_FM} MHz" if config.AUX_HABILITADO else "Icecast"
    print("=====================================================")
    print(f" INICIANDO RADIO NOAA STREAM — {config.CIUDAD}    ")
    print(f" Salidas: {salidas}                               ")
    print("=====================================================")

    # Crear carpetas necesarias si no existen
    if not os.path.exists(config.CARPETA_MUSICA):
        os.makedirs(config.CARPETA_MUSICA)

    # Verificar archivos de audio críticos al arranque
    for archivo, nombre in [(config.ARCHIVO_ALERTA_SISMICA, "Alarma sísmica"),
                            (config.ARCHIVO_SILENCIO, "Silencio")]:
        if not os.path.exists(archivo):
            print(f"[SISTEMA] - {estado.ts()} ⚠️  ADVERTENCIA: '{archivo}' ({nombre}) NO ENCONTRADO.")
        else:
            print(f"[SISTEMA] - {estado.ts()} ✅ {nombre}: {archivo}")

    # Inicializar el pipeline de audio
    dj.iniciar_o_reiniciar_stream()

    # Lanzar watchdog que detecta y recupera caídas silenciosas del pipeline
    dj.iniciar_watchdog(intervalo=15)

    # Iniciar el monitor de alertas sísmicas (SASSLA)
    sismo.iniciar_monitor()

    # Precarga única de estaciones solares (USNO) — resultado cacheado en estado.py
    print(f"[SISTEMA] - {estado.ts()} 🌍 Cargando eventos solares USNO...")
    meteorologo.obtener_estaciones_solares()

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
        # --- 1. MODO ALERTA SÍSMICA (ALTA PRIORIDAD) ---
        if estado.alerta_sismica:
            print(f"\n[DJ] - {estado.ts()} 🚨 MODO ALERTA SÍSMICA ACTIVADO 🚨")
            reps = config.REPETICIONES_SIMULACRO if estado.sismo_es_simulacro else config.REPETICIONES_SISMO_REAL

            # 1a. Reproducir la alerta sonora × N
            for i in range(reps):
                print(f"[DJ] - {estado.ts()} 🚨 Transmitiendo alarma sonora ({i+1}/{reps})...")
                dj.inyectar_audio_al_stream(config.ARCHIVO_ALERTA_SISMICA, es_espera=False, es_alarma=True)
                dj.transmitir_silencio(1.0, es_alarma=True)

            # 1b. Señalar que la alarma terminó (sismo_flujo.py espera esta señal)
            estado.alerta_sismica = False

            # 1c. SIMULACRO: simplemente volver a modo normal
            if estado.sismo_es_simulacro:
                print(f"\n[DJ] - {estado.ts()} ✅ Alarma de simulacro completada. Volviendo a modo normal.")
                # flujo_alerta_sismica() limpia las banderas en su hilo
                continue

            # 1d. SISMO REAL: bucle de espera dinámico y responsivo
            print(f"\n[DJ] - {estado.ts()} ⏳ Esperando reporte sísmico...")
            while not estado.sismo_guion_listo:
                # Reproducir audio de espera si existe (se interrumpirá inmediatamente si el guion queda listo)
                if os.path.exists(config.ARCHIVO_SISMO_ESPERA) and not estado.sismo_guion_listo:
                    dj.inyectar_audio_al_stream(config.ARCHIVO_SISMO_ESPERA, es_espera=True, es_alarma=True)
                
                # Transmitir silencio PCM (en memoria) en bloques dinámicos
                # Se interrumpe dentro de la misma función (máx 0.5s de latencia)
                # en cuanto estado.sismo_guion_listo sea True.
                if not estado.sismo_guion_listo:
                    dj.transmitir_silencio(5.0, es_espera=True, es_alarma=True)

            # 1e. Reporte sísmico listo → reproducir ×2
            print(f"\n[DJ] - {estado.ts()} 🎙️  Transmitiendo reporte sísmico inmediato (x2)")
            for _ in range(2):
                dj.inyectar_audio_al_stream(config.ARCHIVO_SISMO_REPORTE, es_alarma=True)
                dj.transmitir_silencio(1.0, es_alarma=True)

            # 1f. Limpiar flags de guion, mantener intercalado activo
            estado.sismo_guion_listo = False
            print(f"\n[DJ] - {estado.ts()} ✅ Transición a modo intercalado sismo↔clima.")
            continue

        # --- 2. AVISOS DEL SCHEDULER ---
        segundos_proximo = schedule.idle_seconds()
        if segundos_proximo is not None:
            if 0 <= segundos_proximo <= 120 and not aviso_previo_mostrado:
                mins = int(segundos_proximo // 60)
                segs = int(segundos_proximo % 60)
                print(f"\n[RELOJ] - {estado.ts()} ⏳ ¡Atención! El reporte actualizará en {mins}m y {segs}s.")
                aviso_previo_mostrado = True
            elif segundos_proximo > 120 or segundos_proximo < 0:
                aviso_previo_mostrado = False

        # --- 3. MODO ESPERA (GENERANDO REPORTE CLIMA) ---
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

        # --- 4. MODO NORMAL: REPORTES ---
        reporte_interrumpido = False
        for i in range(3):
            if estado.actualizando_clima or estado.alerta_sismica:
                reporte_interrumpido = True
                break

            # Intercalado sismo↔clima: pares=sismo, impares=clima
            if estado.sismo_intercalando and os.path.exists(config.ARCHIVO_SISMO_REPORTE) and i % 2 == 0:
                contador_reportes += 1
                print(
                    f"\n[DJ] - {estado.ts()} 🎙️  Transmitiendo Reporte Sísmico Intercalado "
                    f"(Ciclo {i + 1}/3 | Total histórico: #{contador_reportes})"
                )
                dj.inyectar_audio_al_stream(config.ARCHIVO_SISMO_REPORTE, es_alarma=True)
            else:
                contador_reportes += 1
                print(
                    f"\n[DJ] - {estado.ts()} 🎙️  Transmitiendo Reporte NOAA "
                    f"(Ciclo {i + 1}/3 | Total histórico: #{contador_reportes})"
                )
                dj.inyectar_audio_al_stream(config.ARCHIVO_CLIMA)

            dj.transmitir_silencio(1.0)

        if reporte_interrumpido:
            continue

        # --- 5. MODO NORMAL: CANCIONES ---
        for j in range(2):
            if estado.actualizando_clima or estado.alerta_sismica:
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