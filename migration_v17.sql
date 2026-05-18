-- ============================================================
-- MIGRACIÓN DE BD: v17.0.0
-- Descripción:
--   1. condiciones_especiales: renombrar columnas sísmicas a nombres
--      agnósticos y añadir fuente_alerta, guion_analisis, prompt_analisis.
--   2. Verificar que las columnas de migration_v16 existen (idempotente).
--   3. Actualizar vistas para incluir campos nuevos de datos_owm.
--
-- ORDEN DE APLICACIÓN:
--   Aplicar DESPUÉS de migration_v5_sismo.sql y migration_v16.sql.
--   Idempotente en la sección ALTER TABLE condiciones_especiales gracias
--   a los bloques IF NOT EXISTS / CHANGE.
--   Aplicar sobre la BD de producción ANTES de desplegar:
--     - bd.py rev 16.3.0
--     - sismo_flujo.py rev 15.3.1
-- ============================================================

-- ============================================================
-- 1. condiciones_especiales — columnas renombradas y nuevas
-- ============================================================

-- 1a. Renombrar datos_sassla → datos_fuente_primaria
--     (MariaDB 10.x no soporta IF EXISTS en CHANGE; verificar antes de aplicar
--      si ya existe la columna destino para evitar duplicado)
ALTER TABLE condiciones_especiales
    CHANGE COLUMN datos_sassla datos_fuente_primaria JSON
        COMMENT 'Datos crudos de la fuente que emitió la alerta (SASSLA, CONAGUA, CENAPRED, etc.)';

-- 1b. Renombrar datos_ssn → datos_fuente_secundaria
ALTER TABLE condiciones_especiales
    CHANGE COLUMN datos_ssn datos_fuente_secundaria JSON
        COMMENT 'Confirmación de agencia secundaria (SSN, USGS, EMSC, SMN, etc.)';

-- 1c. Nueva columna: sistema que emitió la alerta (agnóstico al tipo de evento)
ALTER TABLE condiciones_especiales
    ADD COLUMN IF NOT EXISTS fuente_alerta VARCHAR(100) DEFAULT NULL
        COMMENT 'Sistema que emitió la alerta: SASSLA, CONAGUA, CENAPRED, MANUAL, etc.'
        AFTER longitud;

-- 1d. Nueva columna: guion del reporte tardío de análisis post-evento
ALTER TABLE condiciones_especiales
    ADD COLUMN IF NOT EXISTS guion_analisis TEXT DEFAULT NULL
        COMMENT 'Guion del reporte de investigación (post-evento, ~35 min después)'
        AFTER prompt_inmediato;

-- 1e. Nueva columna: prompt usado para generar el reporte de análisis
ALTER TABLE condiciones_especiales
    ADD COLUMN IF NOT EXISTS prompt_analisis TEXT DEFAULT NULL
        COMMENT 'Prompt usado para el reporte de análisis post-evento'
        AFTER guion_analisis;

-- 1f. Índice sobre fuente_alerta para búsquedas por sistema emisor
CREATE INDEX IF NOT EXISTS idx_fuente_alerta ON condiciones_especiales(fuente_alerta);

-- ============================================================
-- 2. Verificación de columnas de migration_v16 en datos_owm
--    (IF NOT EXISTS es idempotente: no falla si ya existen)
-- ============================================================
ALTER TABLE datos_owm
    ADD COLUMN IF NOT EXISTS presion_hpa       DECIMAL(7,2)  DEFAULT NULL COMMENT 'Presión al nivel del mar (hPa)',
    ADD COLUMN IF NOT EXISTS presion_suelo_hpa DECIMAL(7,2)  DEFAULT NULL COMMENT 'Presión al nivel del suelo (hPa)',
    ADD COLUMN IF NOT EXISTS viento_kmh        DECIMAL(5,1)  DEFAULT NULL COMMENT 'Velocidad del viento (km/h)',
    ADD COLUMN IF NOT EXISTS rafagas_kmh       DECIMAL(5,1)  DEFAULT NULL COMMENT 'Velocidad de ráfagas (km/h)',
    ADD COLUMN IF NOT EXISTS nubosidad_pct     TINYINT       DEFAULT NULL COMMENT 'Nubosidad (%) 0-100',
    ADD COLUMN IF NOT EXISTS wind_deg          SMALLINT      DEFAULT NULL COMMENT 'Dirección del viento en grados (0-360)',
    ADD COLUMN IF NOT EXISTS weather_id        SMALLINT      DEFAULT NULL COMMENT 'Código numérico de condición OWM',
    ADD COLUMN IF NOT EXISTS weather_id_etiq   VARCHAR(40)   DEFAULT NULL COMMENT 'Etiqueta de alerta derivada de weather_id';

-- ============================================================
-- 3. Verificación de columnas de migration_v16 en datos_conagua
-- ============================================================
ALTER TABLE datos_conagua
    ADD COLUMN IF NOT EXISTS cc_pct            DECIMAL(5,2)  DEFAULT NULL COMMENT 'Nubosidad diaria % (CONAGUA cc)',
    ADD COLUMN IF NOT EXISTS dirvieng          DECIMAL(6,2)  DEFAULT NULL COMMENT 'Dirección del viento en grados',
    ADD COLUMN IF NOT EXISTS dloc              VARCHAR(20)   DEFAULT NULL COMMENT 'Timestamp de referencia del pronóstico',
    ADD COLUMN IF NOT EXISTS man_prob_lluvia   DECIMAL(5,1)  DEFAULT NULL COMMENT 'Prob. lluvia mañana (%)',
    ADD COLUMN IF NOT EXISTS man_precipitacion DECIMAL(6,1)  DEFAULT NULL COMMENT 'Precipitación proyectada mañana (mm)',
    ADD COLUMN IF NOT EXISTS man_viento        DECIMAL(5,1)  DEFAULT NULL COMMENT 'Viento proyectado mañana (km/h)',
    ADD COLUMN IF NOT EXISTS man_rafagas       DECIMAL(5,1)  DEFAULT NULL COMMENT 'Ráfagas proyectadas mañana (km/h)',
    ADD COLUMN IF NOT EXISTS man_dir_viento    VARCHAR(20)   DEFAULT NULL COMMENT 'Dirección del viento mañana (cardinal)',
    ADD COLUMN IF NOT EXISTS man_cc            DECIMAL(5,2)  DEFAULT NULL COMMENT 'Nubosidad mañana (%)';

-- ============================================================
-- 4. Verificación de columna aod en datos_openmeteo
-- ============================================================
ALTER TABLE datos_openmeteo
    ADD COLUMN IF NOT EXISTS aod DECIMAL(6,3) DEFAULT NULL COMMENT 'Aerosol Optical Depth';

-- ============================================================
-- 5. Verificación de tabla datos_forecast_openmeteo
-- ============================================================
CREATE TABLE IF NOT EXISTS datos_forecast_openmeteo (
    id                  INT UNSIGNED      NOT NULL AUTO_INCREMENT PRIMARY KEY,
    openmeteo_id        INT UNSIGNED      NOT NULL COMMENT 'FK a datos_openmeteo.id',
    prob_lluvia_max     DECIMAL(5,1)      DEFAULT NULL COMMENT 'Prob. lluvia máxima en ventana 6h (%)',
    hora_pico_lluvia    TINYINT           DEFAULT NULL COMMENT 'Hora (0-23) del pico de lluvia',
    prec_total          DECIMAL(6,2)      DEFAULT NULL COMMENT 'Precipitación total proyectada en ventana (mm)',
    viento_actual       DECIMAL(5,1)      DEFAULT NULL COMMENT 'Viento hora actual (km/h)',
    viento_max          DECIMAL(5,1)      DEFAULT NULL COMMENT 'Viento máximo en ventana (km/h)',
    hora_viento_max     TINYINT           DEFAULT NULL COMMENT 'Hora del viento máximo',
    cape_max            DECIMAL(8,1)      DEFAULT NULL COMMENT 'CAPE máximo en ventana (J/kg)',
    hora_cape_max       TINYINT           DEFAULT NULL COMMENT 'Hora del CAPE máximo',
    cape_etiqueta       VARCHAR(80)       DEFAULT NULL COMMENT 'Etiqueta interpretativa del CAPE (solo si lluvia_relevante)',
    dew_point           DECIMAL(5,1)      DEFAULT NULL COMMENT 'Punto de rocío promedio en ventana (°C)',
    freezing_level_m    DECIMAL(8,1)      DEFAULT NULL COMMENT 'Isoterma 0°C mínima en ventana (m)',
    helada_etiqueta     VARCHAR(40)       DEFAULT NULL COMMENT 'Etiqueta de alerta de helada',
    CONSTRAINT fk_forecast_openmeteo FOREIGN KEY (openmeteo_id)
        REFERENCES datos_openmeteo(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 6. Actualizar vista_historial_resumido para incluir nuevos campos
--    de datos_owm (viento_kmh) y exponer fuente_ia
-- ============================================================
DROP VIEW IF EXISTS vista_historial_resumido;

CREATE VIEW vista_historial_resumido AS
SELECT
    r.id                            AS id,
    r.timestamp_completo            AS timestamp_completo,
    r.ciudad                        AS ciudad,
    o.temp_actual                   AS temperatura_actual_c,
    c.temp_max                      AS temp_max_c,
    c.temp_min                      AS temp_min_c,
    o.humedad                       AS humedad_pct,
    c.prob_lluvia                   AS prob_lluvia_pct,
    o.lluvia_1h                     AS lluvia_ultima_hora_mm,
    o.viento_kmh                    AS viento_kmh,
    o.weather_id_etiq               AS alerta_fenomeno,
    m.aqi                           AS calidad_aire_aqi,
    m.uv_index                      AS indice_uv,
    IF(c.reporte_id IS NOT NULL, 1, 0) AS cna_disponible,
    IF(o.reporte_id IS NOT NULL, 1, 0) AS owm_disponible,
    IF(m.reporte_id IS NOT NULL, 1, 0) AS aqm_disponible,
    r.guion_generado                AS guion_generado,
    r.modelo_ia_usado               AS modelo_ia_usado
FROM reportes_climatologicos r
LEFT JOIN datos_conagua  c ON c.reporte_id = r.id
LEFT JOIN datos_owm      o ON o.reporte_id = r.id
LEFT JOIN datos_openmeteo m ON m.reporte_id = r.id
ORDER BY r.timestamp_completo DESC;
