-- ============================================================
-- NOAA Stream — Esquema completo de base de datos
-- Base: drift3_26noaa.sql (dump 2026-05-03)
-- Incluye: migration_v5_sismo + migration_v16 + migration_v17 + migration_v18 + migration_v19
-- Versión final: v19.0.0
-- Fecha de consolidación: 2026-06-04
--
-- ORDEN DE CONTENIDO:
--   0. Configuración de sesión
--   1. Tablas base (schema original)
--   2. condiciones_especiales (v5 + renombres/adiciones v17, forma final)
--   3. Columnas adicionales: datos_owm, datos_conagua, datos_openmeteo (v16/v17)
--   4. datos_forecast_openmeteo (v16/v17)
--   5. Índices y llaves primarias / AUTO_INCREMENT
--   6. Foreign keys
--   7. Vistas (definición final v17)
--   8. ────────────────────────────────────────────
--      CONSULTAS DE ESTADÍSTICAS — USO DE MODELOS IA
--      ────────────────────────────────────────────
-- ============================================================

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;


-- ============================================================
-- 1. TABLAS BASE
-- ============================================================

-- ------------------------------------------------------------
-- datos_conagua
-- Columnas originales + columnas v16 directamente en CREATE
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `datos_conagua` (
  `id`                int(10) UNSIGNED NOT NULL,
  `reporte_id`        int(10) UNSIGNED NOT NULL     COMMENT 'FK → reportes_climatologicos.id',

  -- Columnas originales (hoy)
  `condicion`         varchar(150)     DEFAULT NULL  COMMENT 'Descripción del cielo (desciel)',
  `temp_max`          decimal(5,2)     DEFAULT NULL  COMMENT 'Temperatura máxima pronosticada (°C)',
  `temp_min`          decimal(5,2)     DEFAULT NULL  COMMENT 'Temperatura mínima pronosticada (°C)',
  `prob_lluvia`       decimal(5,2)     DEFAULT NULL  COMMENT 'Probabilidad de precipitación (%)',
  `precipitacion`     decimal(6,2)     DEFAULT NULL  COMMENT 'Precipitación acumulada del día (mm)',
  `viento`            decimal(6,2)     DEFAULT NULL  COMMENT 'Velocidad del viento (km/h)',
  `dir_viento`        varchar(10)      DEFAULT NULL  COMMENT 'Dirección del viento (N, S, NE, etc.)',
  `rafagas`           decimal(6,2)     DEFAULT NULL  COMMENT 'Velocidad de ráfagas (km/h)',

  -- Columnas originales (mañana — parciales)
  `man_condicion`     varchar(150)     DEFAULT NULL  COMMENT 'Condición de mañana (desciel)',
  `man_temp_max`      decimal(5,2)     DEFAULT NULL  COMMENT 'Temp. máxima de mañana (°C)',
  `man_temp_min`      decimal(5,2)     DEFAULT NULL  COMMENT 'Temp. mínima de mañana (°C)',

  -- Columnas nuevas v16: hoy (complemento)
  `cc_pct`            decimal(5,2)     DEFAULT NULL  COMMENT 'Nubosidad diaria % (CONAGUA cc)',
  `dirvieng`          decimal(6,2)     DEFAULT NULL  COMMENT 'Dirección del viento en grados',
  `dloc`              varchar(20)      DEFAULT NULL  COMMENT 'Timestamp de referencia del pronóstico CONAGUA',

  -- Columnas nuevas v16: mañana (completo)
  `man_prob_lluvia`   decimal(5,1)     DEFAULT NULL  COMMENT 'Prob. lluvia mañana (%)',
  `man_precipitacion` decimal(6,1)     DEFAULT NULL  COMMENT 'Precipitación proyectada mañana (mm)',
  `man_viento`        decimal(5,1)     DEFAULT NULL  COMMENT 'Viento proyectado mañana (km/h)',
  `man_rafagas`       decimal(5,1)     DEFAULT NULL  COMMENT 'Ráfagas proyectadas mañana (km/h)',
  `man_dir_viento`    varchar(20)      DEFAULT NULL  COMMENT 'Dirección del viento mañana (cardinal)',
  `man_cc`            decimal(5,2)     DEFAULT NULL  COMMENT 'Nubosidad mañana (%)'

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Datos de pronóstico CONAGUA/SMN por reporte climatológico';

-- ------------------------------------------------------------
-- datos_openmeteo
-- Columnas originales + aod (v16)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `datos_openmeteo` (
  `id`         int(10) UNSIGNED NOT NULL,
  `reporte_id` int(10) UNSIGNED NOT NULL  COMMENT 'FK → reportes_climatologicos.id',
  `aqi`        decimal(6,2)  DEFAULT NULL COMMENT 'Índice de Calidad del Aire (US AQI)',
  `pm10`       decimal(7,3)  DEFAULT NULL COMMENT 'Material particulado PM10 (μg/m³)',
  `pm25`       decimal(7,3)  DEFAULT NULL COMMENT 'Material particulado PM2.5 (μg/m³)',
  `uv_index`   decimal(5,2)  DEFAULT NULL COMMENT 'Índice UV',
  `co`         decimal(9,3)  DEFAULT NULL COMMENT 'Monóxido de carbono CO (μg/m³)',
  `no2`        decimal(9,3)  DEFAULT NULL COMMENT 'Dióxido de nitrógeno NO2 (μg/m³)',
  `so2`        decimal(9,3)  DEFAULT NULL COMMENT 'Dióxido de azufre SO2 (μg/m³)',
  `ozono`      decimal(9,3)  DEFAULT NULL COMMENT 'Ozono O3 (μg/m³)',
  -- v16
  `aod`        decimal(6,3)  DEFAULT NULL COMMENT 'Aerosol Optical Depth'
  -- v20
  ,`dust`       decimal(7,3)  DEFAULT NULL COMMENT 'Polvo en suspensión (dust, μg/m³) — Open-Meteo AQI'

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Datos de calidad del aire e índice UV Open-Meteo por reporte climatológico';

-- ------------------------------------------------------------
-- datos_owm
-- Columnas originales + columnas v16
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `datos_owm` (
  `id`                int(10) UNSIGNED NOT NULL,
  `reporte_id`        int(10) UNSIGNED NOT NULL  COMMENT 'FK → reportes_climatologicos.id',

  -- Columnas originales
  `temp_actual`       decimal(5,2)  DEFAULT NULL  COMMENT 'Temperatura actual (°C)',
  `sensacion`         decimal(5,2)  DEFAULT NULL  COMMENT 'Sensación térmica (°C)',
  `humedad`           decimal(5,2)  DEFAULT NULL  COMMENT 'Humedad relativa (%)',
  `condicion`         varchar(150)  DEFAULT NULL  COMMENT 'Descripción del tiempo (weather[0].description)',
  `visibilidad`       decimal(6,2)  DEFAULT NULL  COMMENT 'Visibilidad (km)',
  `lluvia_1h`         decimal(6,2)  DEFAULT NULL  COMMENT 'Lluvia registrada en la última hora (mm)',
  `amanecer`          time          DEFAULT NULL  COMMENT 'Hora del amanecer',
  `atardecer`         time          DEFAULT NULL  COMMENT 'Hora del atardecer',

  -- Columnas nuevas v16
  `presion_hpa`       decimal(7,2)  DEFAULT NULL  COMMENT 'Presión al nivel del mar (hPa)',
  `presion_suelo_hpa` decimal(7,2)  DEFAULT NULL  COMMENT 'Presión al nivel del suelo (hPa) — más precisa a 2108 m',
  `viento_kmh`        decimal(5,1)  DEFAULT NULL  COMMENT 'Velocidad del viento (km/h)',
  `rafagas_kmh`       decimal(5,1)  DEFAULT NULL  COMMENT 'Velocidad de ráfagas (km/h)',
  `nubosidad_pct`     tinyint       DEFAULT NULL  COMMENT 'Nubosidad (%) 0-100',
  `wind_deg`          smallint      DEFAULT NULL  COMMENT 'Dirección del viento en grados (0-360)',
  `weather_id`        smallint      DEFAULT NULL  COMMENT 'Código numérico de condición OWM (weather[0].id)',
  `weather_id_etiq`   varchar(40)   DEFAULT NULL  COMMENT 'Etiqueta de alerta derivada de weather_id'

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Datos de condiciones actuales OpenWeatherMap por reporte climatológico';

-- ------------------------------------------------------------
-- errores_recoleccion
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `errores_recoleccion` (
  `id`              int(10) UNSIGNED NOT NULL,
  `timestamp_error` datetime         NOT NULL DEFAULT current_timestamp(),
  `fuente`          varchar(30)      NOT NULL  COMMENT 'CONAGUA | OWM | OPEN_METEO | GEMINI | AUDIO',
  `mensaje_error`   text             DEFAULT NULL,
  `reporte_id`      int(10) UNSIGNED DEFAULT NULL COMMENT 'ID del reporte asociado si aplica'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Registro de errores de las APIs de datos meteorológicos';

-- ------------------------------------------------------------
-- prompt_reporte_climatologico
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `prompt_reporte_climatologico` (
  `id`               int(10) UNSIGNED NOT NULL,
  `reporte_id`       int(10) UNSIGNED DEFAULT NULL COMMENT 'ID del reporte climatológico asociado',
  `timestamp_prompt` datetime         NOT NULL DEFAULT current_timestamp() COMMENT 'Momento de generación del prompt',
  `prompt_texto`     mediumtext       NOT NULL  COMMENT 'Prompt exacto enviado a la API de Gemini'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Registro histórico de los prompts enviados a Gemini por reporte climatológico';

-- ------------------------------------------------------------
-- reportes_climatologicos
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `reportes_climatologicos` (
  `id`                 int(10) UNSIGNED NOT NULL,
  `fecha_reporte`      date             NOT NULL  COMMENT 'Fecha del reporte (YYYY-MM-DD)',
  `hora_reporte`       time             NOT NULL  COMMENT 'Hora de recolección de datos (HH:MM)',
  `timestamp_completo` datetime         NOT NULL  COMMENT 'Fecha y hora exacta del reporte',
  `ciudad`             varchar(100)     NOT NULL DEFAULT 'Huichapan, MX',
  `guion_texto`        mediumtext       DEFAULT NULL COMMENT 'Guion completo generado por Gemini',
  `modelo_ia_usado`    varchar(80)      DEFAULT NULL COMMENT 'Modelo de Gemini utilizado (principal o respaldo)',
  `guion_generado`     tinyint(1)       NOT NULL DEFAULT 0 COMMENT '1 si el guion fue generado exitosamente',
  `creado_en`          datetime         NOT NULL DEFAULT current_timestamp() COMMENT 'Momento exacto de inserción en BD'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Historial climatológico completo generado por la radio meteorológica automatizada';

-- ------------------------------------------------------------
-- resumen_reporte_clima
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `resumen_reporte_clima` (
  `id`                int(10) UNSIGNED NOT NULL,
  `reporte_id`        int(10) UNSIGNED DEFAULT NULL COMMENT 'ID del reporte climatológico asociado',
  `timestamp_log`     datetime         NOT NULL DEFAULT current_timestamp() COMMENT 'Momento del registro (Server time)',
  `temp`              decimal(5,2)     DEFAULT NULL  COMMENT 'Temperatura actual OWM',
  `condicion`         varchar(150)     DEFAULT 'N/D' COMMENT 'Condición formateada en texto',
  `humedad`           decimal(5,2)     DEFAULT NULL  COMMENT 'Humedad relativa ambiente',
  `viento`            varchar(20)      DEFAULT 'N/D' COMMENT 'Velocidad de viento o N/D',
  `aqi`               varchar(20)      DEFAULT 'N/D' COMMENT 'AQI (String para soportar N/D)',
  `pm25`              varchar(20)      DEFAULT 'N/D' COMMENT 'PM2.5 (String para soportar N/D)',
  `hora_actualizacion` varchar(10)     DEFAULT NULL  COMMENT 'Hora asignada en el tablero HH:MM'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Respaldo directo de los datos suministrados al front-end web (datos.json)';

-- ------------------------------------------------------------
-- webcam_capturas
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `webcam_capturas` (
  `id`         int(10) UNSIGNED    NOT NULL,
  `fecha_hora` datetime            NOT NULL COMMENT 'Timestamp del disparo programado',
  `url`        varchar(512)        NOT NULL COMMENT 'URL HTTPS de Cloudinary',
  `public_id`  varchar(255)        NOT NULL COMMENT 'Identificador dentro de Cloudinary',
  `tamano_kb`  smallint(5) UNSIGNED NOT NULL DEFAULT 0 COMMENT 'Peso de la imagen en KB'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='Capturas periodicas de webcam NOAA Stream';


-- ============================================================
-- 2. condiciones_especiales
--    Creada directamente en su forma final (v5 + cambios v17):
--    - datos_fuente_primaria   (antes datos_sassla)
--    - datos_fuente_secundaria (antes datos_ssn)
--    - fuente_alerta, guion_analisis, prompt_analisis añadidos
-- ============================================================
CREATE TABLE IF NOT EXISTS `condiciones_especiales` (
  `id`                      int          NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `timestamp_evento`        datetime     NOT NULL,
  `tipo`                    varchar(50)  NOT NULL   COMMENT 'Ej. SISMO, SIMULACRO, HURACAN',
  `subtipo`                 varchar(100) DEFAULT NULL COMMENT 'Ej. Magnitud 6.4, Simulacro Nacional',
  `descripcion`             text         DEFAULT NULL COMMENT 'Breve descripción humana del evento',

  -- Ubicación (opcional)
  `ubicacion`               varchar(255) DEFAULT NULL,
  `latitud`                 decimal(10,6) DEFAULT NULL,
  `longitud`                decimal(10,6) DEFAULT NULL,

  -- Sistema emisor de la alerta (v17)
  `fuente_alerta`           varchar(100) DEFAULT NULL
    COMMENT 'Sistema que emitió la alerta: SASSLA, CONAGUA, CENAPRED, MANUAL, etc.',

  -- JSON Data (nombres agnósticos desde v17)
  `datos_fuente_primaria`   JSON         DEFAULT NULL
    COMMENT 'Datos crudos de la fuente que emitió la alerta (SASSLA, CONAGUA, CENAPRED, etc.)',
  `datos_fuente_secundaria` JSON         DEFAULT NULL
    COMMENT 'Confirmación de agencia secundaria (SSN, USGS, EMSC, SMN, etc.)',
  `datos_investigacion`     JSON         DEFAULT NULL
    COMMENT 'Datos post-evento de USGS, EMSC, IRIS y réplicas',

  -- Guiones y Prompts (reporte inmediato)
  `guion_inmediato`         text         DEFAULT NULL COMMENT 'Texto del reporte generado al instante',
  `prompt_inmediato`        text         DEFAULT NULL COMMENT 'Prompt usado para el reporte inmediato',

  -- Guiones y Prompts (análisis post-evento, v17)
  `guion_analisis`          text         DEFAULT NULL
    COMMENT 'Guion del reporte de investigación (post-evento, ~35 min después)',
  `prompt_analisis`         text         DEFAULT NULL
    COMMENT 'Prompt usado para el reporte de análisis post-evento',

  `modelo_ia_usado`         varchar(50)  DEFAULT NULL
    COMMENT 'Modelo usado para generar los textos'

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 2b. historial_condiciones_especiales (v21.0.0)
--     FK → condiciones_especiales.id  |  ON DELETE CASCADE
-- ============================================================
CREATE TABLE IF NOT EXISTS `historial_condiciones_especiales` (
  `id`                      int          NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `condicion_especial_id`   int          NOT NULL COMMENT 'FK → condiciones_especiales.id',
  `timestamp_actualizacion` datetime     NOT NULL DEFAULT current_timestamp(),
  
  -- Datos descriptivos y geográficos en esta iteración
  `subtipo`                 varchar(100) DEFAULT NULL,
  `descripcion`             text         DEFAULT NULL,
  `ubicacion`               varchar(255) DEFAULT NULL,
  `latitud`                 decimal(10,6) DEFAULT NULL,
  `longitud`                decimal(10,6) DEFAULT NULL,
  
  -- Snapshots de datos en formato JSON de este ciclo de enriquecimiento
  `datos_fuente_primaria`   JSON         DEFAULT NULL,
  `datos_fuente_secundaria` JSON         DEFAULT NULL,
  `datos_investigacion`     JSON         DEFAULT NULL,
  
  -- Guiones opcionales generados en este punto
  `guion_analisis`          text         DEFAULT NULL,
  `prompt_analisis`         text         DEFAULT NULL,
  `modelo_ia_usado`         varchar(50)  DEFAULT NULL,

  CONSTRAINT `fk_historial_condicion` 
    FOREIGN KEY (`condicion_especial_id`) 
    REFERENCES `condiciones_especiales` (`id`) 
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX IF NOT EXISTS `idx_historial_condicion_id` ON `historial_condiciones_especiales`(`condicion_especial_id`);


-- ============================================================
-- 3. datos_forecast_openmeteo (v16/v17, forma final)
--    FK → datos_openmeteo.id  |  ON DELETE CASCADE
-- ============================================================
CREATE TABLE IF NOT EXISTS `datos_forecast_openmeteo` (
  `id`                INT UNSIGNED  NOT NULL AUTO_INCREMENT PRIMARY KEY,
  `openmeteo_id`      INT UNSIGNED  NOT NULL  COMMENT 'FK a datos_openmeteo.id',
  `prob_lluvia_max`   decimal(5,1)  DEFAULT NULL COMMENT 'Prob. lluvia máxima en ventana 6h (%)',
  `hora_pico_lluvia`  tinyint       DEFAULT NULL COMMENT 'Hora (0-23) del pico de lluvia',
  `prec_total`        decimal(6,2)  DEFAULT NULL COMMENT 'Precipitación total proyectada en ventana (mm)',
  `viento_actual`     decimal(5,1)  DEFAULT NULL COMMENT 'Viento hora actual (km/h)',
  `viento_max`        decimal(5,1)  DEFAULT NULL COMMENT 'Viento máximo en ventana (km/h)',
  `hora_viento_max`   tinyint       DEFAULT NULL COMMENT 'Hora del viento máximo',
  `cape_max`          decimal(8,1)  DEFAULT NULL COMMENT 'CAPE máximo en ventana (J/kg)',
  `hora_cape_max`     tinyint       DEFAULT NULL COMMENT 'Hora del CAPE máximo',
  `cape_etiqueta`     varchar(80)   DEFAULT NULL
    COMMENT 'Etiqueta interpretativa del CAPE (solo si lluvia_relevante)',
  `dew_point`         decimal(5,1)  DEFAULT NULL COMMENT 'Punto de rocío promedio en ventana (°C)',
  `freezing_level_m`  decimal(8,1)  DEFAULT NULL COMMENT 'Isoterma 0°C mínima en ventana (m)',
  `helada_etiqueta`   varchar(40)   DEFAULT NULL COMMENT 'Etiqueta de alerta de helada',
  -- v20
  `shortwave_pico`    decimal(8,1)  DEFAULT NULL COMMENT 'Radiación solar máxima proyectada próximas 24h (W/m²)',
  CONSTRAINT `fk_forecast_openmeteo`
    FOREIGN KEY (`openmeteo_id`) REFERENCES `datos_openmeteo`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 4. datos_fase_lunar (v18 + v19)
-- ============================================================
-- Migration v18: Creación de la tabla datos_fase_lunar
-- Migration v19: Añade crepúsculo civil, mediodía solar, día de semana
--               y fase lunar más cercana (todos desde USNO)
CREATE TABLE IF NOT EXISTS `datos_fase_lunar` (
  `id`                     int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `reporte_id`             int(10) UNSIGNED NOT NULL,

  -- Campos base (v18) — recuperados desde USNO
  `fase_nombre`            varchar(100)     DEFAULT NULL COMMENT 'Nombre de la fase en español — USNO curphase',
  `fase_ingles`            varchar(100)     DEFAULT NULL COMMENT 'Nombre de la fase en inglés — USNO curphase',
  `iluminacion_porcentaje` tinyint(3)       DEFAULT NULL COMMENT 'Porcentaje de iluminación (0-100) — USNO fracillum',
  `salida_luna`            time             DEFAULT NULL COMMENT 'Hora de salida de la luna — USNO moondata Rise',
  `ocaso_luna`             time             DEFAULT NULL COMMENT 'Hora de ocaso de la luna — USNO moondata Set',
  `transito_luna`          time             DEFAULT NULL COMMENT 'Hora del cénit lunar — USNO moondata Upper Transit',
  `visible_de_dia`         tinyint(1)       DEFAULT NULL COMMENT '1 si es visible de día, 0 si no — calculado en Python',
  `fase_etiqueta`          varchar(255)     DEFAULT NULL COMMENT 'Descripción narrativa de la fase — mapa interno Python',

  -- Campos nuevos (v19) — recuperados desde USNO
  `crepusculo_inicio`      time             DEFAULT NULL COMMENT 'Inicio del crepúsculo civil — USNO sundata "Begin Civil Twilight"',
  `crepusculo_fin`         time             DEFAULT NULL COMMENT 'Fin del crepúsculo civil — USNO sundata "End Civil Twilight"',
  `mediodia_solar`         time             DEFAULT NULL COMMENT 'Mediodía solar (tránsito superior del sol) — USNO sundata "Upper Transit"',
  `dia_semana`             varchar(20)      DEFAULT NULL COMMENT 'Día de la semana en inglés — USNO data.day_of_week',
  `fase_cercana_nombre`    varchar(60)      DEFAULT NULL COMMENT 'Nombre en español de la fase lunar más próxima — USNO closestphase.phase',
  `fase_cercana_fecha`     date             DEFAULT NULL COMMENT 'Fecha exacta de la fase más próxima — USNO closestphase day/month/year',
  `fase_cercana_hora`      time             DEFAULT NULL COMMENT 'Hora de la fase más próxima — USNO closestphase.time',
  `fase_cercana_dias`      smallint         DEFAULT NULL COMMENT 'Días hasta la fase (negativo = ya ocurrió, 0 = hoy) — calculado en Python',

  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_reporte` (`reporte_id`),
  CONSTRAINT `fk_fase_lunar_reporte` FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Datos de astronomía y fase lunar por reporte climatológico — Fuente: USNO (aa.usno.navy.mil)';


-- ============================================================
-- 5. ÍNDICES, LLAVES PRIMARIAS Y AUTO_INCREMENT
-- ============================================================

ALTER TABLE `datos_conagua`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_reporte` (`reporte_id`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `datos_openmeteo`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_reporte` (`reporte_id`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `datos_owm`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_reporte` (`reporte_id`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `errores_recoleccion`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_fuente` (`fuente`),
  ADD KEY `idx_timestamp` (`timestamp_error`),
  ADD KEY `fk_errores_reporte` (`reporte_id`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `prompt_reporte_climatologico`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_reporte_id` (`reporte_id`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `reportes_climatologicos`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_fecha` (`fecha_reporte`),
  ADD KEY `idx_timestamp` (`timestamp_completo`),
  ADD KEY `idx_ciudad` (`ciudad`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `resumen_reporte_clima`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_reporte_id` (`reporte_id`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

ALTER TABLE `webcam_capturas`
  ADD PRIMARY KEY (`id`),
  ADD UNIQUE KEY `uq_fecha_hora` (`fecha_hora`),
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

-- Índices de condiciones_especiales (v5 + v17)
CREATE INDEX IF NOT EXISTS `idx_tipo`          ON `condiciones_especiales`(`tipo`);
CREATE INDEX IF NOT EXISTS `idx_timestamp`     ON `condiciones_especiales`(`timestamp_evento`);
CREATE INDEX IF NOT EXISTS `idx_fuente_alerta` ON `condiciones_especiales`(`fuente_alerta`);


-- ============================================================
-- 5. FOREIGN KEYS (tablas base)
-- ============================================================

ALTER TABLE `datos_conagua`
  ADD CONSTRAINT `fk_conagua_reporte`
    FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;

ALTER TABLE `datos_openmeteo`
  ADD CONSTRAINT `fk_openmeteo_reporte`
    FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;

ALTER TABLE `datos_owm`
  ADD CONSTRAINT `fk_owm_reporte`
    FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;

ALTER TABLE `errores_recoleccion`
  ADD CONSTRAINT `fk_errores_reporte`
    FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE SET NULL;

ALTER TABLE `prompt_reporte_climatologico`
  ADD CONSTRAINT `fk_prompt_reporte`
    FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;

ALTER TABLE `resumen_reporte_clima`
  ADD CONSTRAINT `fk_resumen_reporte`
    FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;


-- ============================================================
-- 6. VISTAS (definición final v17)
-- ============================================================

-- ------------------------------------------------------------
-- vista_estadisticas_diarias
-- (sin cambios desde el schema original)
-- ------------------------------------------------------------
DROP VIEW IF EXISTS `vista_estadisticas_diarias`;

CREATE VIEW `vista_estadisticas_diarias` AS
SELECT
    r.fecha_reporte                         AS fecha_reporte,
    COUNT(r.id)                             AS total_reportes,
    ROUND(AVG(o.temp_actual),  2)           AS temp_promedio_c,
    ROUND(MAX(o.temp_actual),  2)           AS temp_maxima_c,
    ROUND(MIN(o.temp_actual),  2)           AS temp_minima_c,
    ROUND(AVG(o.humedad),      2)           AS humedad_promedio_pct,
    ROUND(MAX(o.lluvia_1h),    2)           AS lluvia_maxima_hora_mm,
    ROUND(SUM(o.lluvia_1h),    2)           AS lluvia_acumulada_dia_mm,
    ROUND(AVG(m.aqi),          2)           AS aqi_promedio,
    ROUND(MAX(m.uv_index),     2)           AS uv_maximo_dia
FROM reportes_climatologicos r
LEFT JOIN datos_owm       o ON o.reporte_id = r.id
LEFT JOIN datos_openmeteo m ON m.reporte_id = r.id
GROUP BY r.fecha_reporte
ORDER BY r.fecha_reporte DESC;

-- ------------------------------------------------------------
-- vista_historial_resumido (actualizada en v17)
-- Agrega: viento_kmh, alerta_fenomeno, modelo_ia_usado
-- ------------------------------------------------------------
DROP VIEW IF EXISTS `vista_historial_resumido`;

CREATE VIEW `vista_historial_resumido` AS
SELECT
    r.id                                        AS id,
    r.timestamp_completo                        AS timestamp_completo,
    r.ciudad                                    AS ciudad,
    o.temp_actual                               AS temperatura_actual_c,
    c.temp_max                                  AS temp_max_c,
    c.temp_min                                  AS temp_min_c,
    o.humedad                                   AS humedad_pct,
    c.prob_lluvia                               AS prob_lluvia_pct,
    o.lluvia_1h                                 AS lluvia_ultima_hora_mm,
    o.viento_kmh                                AS viento_kmh,
    o.weather_id_etiq                           AS alerta_fenomeno,
    m.aqi                                       AS calidad_aire_aqi,
    m.uv_index                                  AS indice_uv,
    IF(c.reporte_id IS NOT NULL, 1, 0)          AS cna_disponible,
    IF(o.reporte_id IS NOT NULL, 1, 0)          AS owm_disponible,
    IF(m.reporte_id IS NOT NULL, 1, 0)          AS aqm_disponible,
    r.guion_generado                            AS guion_generado,
    r.modelo_ia_usado                           AS modelo_ia_usado
FROM reportes_climatologicos r
LEFT JOIN datos_conagua   c ON c.reporte_id = r.id
LEFT JOIN datos_owm       o ON o.reporte_id = r.id
LEFT JOIN datos_openmeteo m ON m.reporte_id = r.id
ORDER BY r.timestamp_completo DESC;


COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;


-- ============================================================
-- Migración v20.0.0 (comentario informativo — sin DDL adicional)
-- Fecha: 2026-06-18
-- Módulo: ssn_rss.py — Detección de sismos HGO via SSN RSS
-- ============================================================
-- El módulo ssn_rss.py reutiliza la tabla condiciones_especiales existente
-- (introducida en v5, forma final en v17) para registrar sismos detectados
-- en el estado de Hidalgo a través del feed RSS del SSN.
--
-- Valores fijos usados por ssn_rss.py:
--   tipo          = 'SISMO_SSN_HIDALGO'
--   fuente_alerta = 'SSN_RSS'
--   subtipo       = 'M X.X' (magnitud del sismo principal del grupo)
--   datos_fuente_primaria = JSON array con los sismos del grupo detectado
--
-- No se requieren columnas nuevas. El índice idx_tipo existente
-- (sobre condiciones_especiales.tipo) cubre las consultas por tipo.
-- ============================================================
