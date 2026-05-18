-- migration_v16.sql
-- Migración: v16.2.0 — Expansión de datos meteorológicos
-- Nota v16.2.0: datos_forecast renombrada a datos_forecast_openmeteo. FK
--               cambia de reportes_climatologicos → datos_openmeteo, reflejando
--               que ambas tablas provienen de la misma fuente (Open-Meteo).
--               El forecast solo se persiste cuando datos_openmeteo existe.
-- Nota v16.1.0: Se retira datos_conagua_horario (CONAGUA method=3 suspendido).
-- Aplicar sobre la BD de producción antes de desplegar noaa_str.py v16.2.0

-- =============================================
-- 1. datos_owm — columnas nuevas
-- =============================================
ALTER TABLE datos_owm
    ADD COLUMN presion_hpa       DECIMAL(7,2)  DEFAULT NULL COMMENT 'Presión al nivel del mar (hPa)',
    ADD COLUMN presion_suelo_hpa DECIMAL(7,2)  DEFAULT NULL COMMENT 'Presión al nivel del suelo (hPa) — más precisa a 2108 m',
    ADD COLUMN viento_kmh        DECIMAL(5,1)  DEFAULT NULL COMMENT 'Velocidad del viento (km/h)',
    ADD COLUMN rafagas_kmh       DECIMAL(5,1)  DEFAULT NULL COMMENT 'Velocidad de ráfagas (km/h)',
    ADD COLUMN nubosidad_pct     TINYINT       DEFAULT NULL COMMENT 'Nubosidad (%) 0-100',
    ADD COLUMN wind_deg          SMALLINT      DEFAULT NULL COMMENT 'Dirección del viento en grados (0-360)',
    ADD COLUMN weather_id        SMALLINT      DEFAULT NULL COMMENT 'Código numérico de condición OWM (weather[0].id)',
    ADD COLUMN weather_id_etiq   VARCHAR(40)   DEFAULT NULL COMMENT 'Etiqueta de alerta derivada de weather_id';

-- =============================================
-- 2. datos_conagua — columnas nuevas (hoy y mañana completo)
-- =============================================
ALTER TABLE datos_conagua
    ADD COLUMN cc_pct            DECIMAL(5,2)  DEFAULT NULL COMMENT 'Nubosidad diaria % (CONAGUA cc)',
    ADD COLUMN dirvieng          DECIMAL(6,2)  DEFAULT NULL COMMENT 'Dirección del viento en grados',
    ADD COLUMN dloc              VARCHAR(20)   DEFAULT NULL COMMENT 'Timestamp de referencia del pronóstico CONAGUA',
    ADD COLUMN man_prob_lluvia   DECIMAL(5,1)  DEFAULT NULL COMMENT 'Prob. lluvia mañana (%)',
    ADD COLUMN man_precipitacion DECIMAL(6,1)  DEFAULT NULL COMMENT 'Precipitación proyectada mañana (mm)',
    ADD COLUMN man_viento        DECIMAL(5,1)  DEFAULT NULL COMMENT 'Viento proyectado mañana (km/h)',
    ADD COLUMN man_rafagas       DECIMAL(5,1)  DEFAULT NULL COMMENT 'Ráfagas proyectadas mañana (km/h)',
    ADD COLUMN man_dir_viento    VARCHAR(20)   DEFAULT NULL COMMENT 'Dirección del viento mañana (cardinal)',
    ADD COLUMN man_cc            DECIMAL(5,2)  DEFAULT NULL COMMENT 'Nubosidad mañana (%)';

-- =============================================
-- 3. datos_openmeteo — columnas nuevas
-- =============================================
ALTER TABLE datos_openmeteo
    ADD COLUMN aod               DECIMAL(6,3)  DEFAULT NULL COMMENT 'Aerosol Optical Depth';

-- =============================================
-- 4. datos_forecast_openmeteo — tabla nueva (Open-Meteo Forecast horario, ventana 6h)
--    Subtabla de datos_openmeteo: solo existe si el registro AQI existe.
--    FK: datos_forecast_openmeteo.openmeteo_id → datos_openmeteo.id
-- =============================================
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
    cape_etiqueta       VARCHAR(40)       DEFAULT NULL COMMENT 'Etiqueta interpretativa del CAPE',
    dew_point           DECIMAL(5,1)      DEFAULT NULL COMMENT 'Punto de rocío promedio en ventana (°C)',
    freezing_level_m    DECIMAL(8,1)      DEFAULT NULL COMMENT 'Isoterma 0°C mínima en ventana (m)',
    helada_etiqueta     VARCHAR(40)       DEFAULT NULL COMMENT 'Etiqueta de alerta de helada',
    CONSTRAINT fk_forecast_openmeteo FOREIGN KEY (openmeteo_id)
        REFERENCES datos_openmeteo(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
