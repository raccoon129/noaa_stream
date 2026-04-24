-- phpMyAdmin SQL Dump
-- version 5.2.3
-- https://www.phpmyadmin.net/
--
-- Host: mysql-drift3.alwaysdata.net
-- Generation Time: Apr 22, 2026 at 09:15 PM
-- Server version: 10.11.15-MariaDB
-- PHP Version: 8.4.19

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
START TRANSACTION;
SET time_zone = "+00:00";


/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!40101 SET NAMES utf8mb4 */;

--
-- Database: `drift3_26noaa`
--

-- --------------------------------------------------------

--
-- Table structure for table `errores_recoleccion`
--

CREATE TABLE `errores_recoleccion` (
  `id` int(10) UNSIGNED NOT NULL,
  `timestamp_error` datetime NOT NULL DEFAULT current_timestamp(),
  `fuente` varchar(30) NOT NULL COMMENT 'CONAGUA | OWM | OPEN_METEO | GEMINI | AUDIO',
  `mensaje_error` text DEFAULT NULL,
  `reporte_id` int(10) UNSIGNED DEFAULT NULL COMMENT 'ID del reporte asociado si aplica'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Registro de errores de las APIs de datos meteorológicos';

-- --------------------------------------------------------

--
-- Table structure for table `prompt_reporte_climatologico`
--

CREATE TABLE `prompt_reporte_climatologico` (
  `id` int(10) UNSIGNED NOT NULL,
  `reporte_id` int(10) UNSIGNED DEFAULT NULL COMMENT 'ID del reporte climatológico asociado',
  `timestamp_prompt` datetime NOT NULL DEFAULT current_timestamp() COMMENT 'Momento de generación del prompt',
  `prompt_texto` mediumtext NOT NULL COMMENT 'Prompt exacto enviado a la API de Gemini'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Registro histórico de los prompts enviados a Gemini por reporte climatológico';

-- --------------------------------------------------------

--
-- Table structure for table `reportes_climatologicos`
--

CREATE TABLE `reportes_climatologicos` (
  `id` int(10) UNSIGNED NOT NULL,
  `fecha_reporte` date NOT NULL COMMENT 'Fecha del reporte (YYYY-MM-DD)',
  `hora_reporte` time NOT NULL COMMENT 'Hora de recolección de datos (HH:MM)',
  `timestamp_completo` datetime NOT NULL COMMENT 'Fecha y hora exacta del reporte',
  `ciudad` varchar(100) NOT NULL DEFAULT 'Huichapan, MX',
  `cna_disponible` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1 si CONAGUA respondió, 0 si falló',
  `cna_condicion` varchar(150) DEFAULT NULL COMMENT 'Descripción del cielo (desciel)',
  `cna_temp_max` decimal(5,2) DEFAULT NULL COMMENT 'Temperatura máxima pronosticada (°C)',
  `cna_temp_min` decimal(5,2) DEFAULT NULL COMMENT 'Temperatura mínima pronosticada (°C)',
  `cna_prob_lluvia` decimal(5,2) DEFAULT NULL COMMENT 'Probabilidad de precipitación (%)',
  `cna_precipitacion` decimal(6,2) DEFAULT NULL COMMENT 'Precipitación acumulada del día (mm)',
  `cna_viento` decimal(6,2) DEFAULT NULL COMMENT 'Velocidad del viento (km/h)',
  `cna_dir_viento` varchar(10) DEFAULT NULL COMMENT 'Dirección del viento (N, S, NE, etc.)',
  `cna_rafagas` decimal(6,2) DEFAULT NULL COMMENT 'Velocidad de ráfagas (km/h)',
  `cna_man_condicion` varchar(150) DEFAULT NULL COMMENT 'Condición de mañana (desciel)',
  `cna_man_temp_max` decimal(5,2) DEFAULT NULL COMMENT 'Temp. máxima de mañana (°C)',
  `cna_man_temp_min` decimal(5,2) DEFAULT NULL COMMENT 'Temp. mínima de mañana (°C)',
  `owm_disponible` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1 si OWM respondió, 0 si falló',
  `owm_temp_actual` decimal(5,2) DEFAULT NULL COMMENT 'Temperatura actual (°C)',
  `owm_sensacion` decimal(5,2) DEFAULT NULL COMMENT 'Sensación térmica (°C)',
  `owm_humedad` decimal(5,2) DEFAULT NULL COMMENT 'Humedad relativa (%)',
  `owm_condicion` varchar(150) DEFAULT NULL COMMENT 'Descripción del tiempo (weather[0].description)',
  `owm_visibilidad` decimal(6,2) DEFAULT NULL COMMENT 'Visibilidad (km)',
  `owm_lluvia_1h` decimal(6,2) DEFAULT NULL COMMENT 'Lluvia registrada en la última hora (mm)',
  `owm_amanecer` time DEFAULT NULL COMMENT 'Hora del amanecer',
  `owm_atardecer` time DEFAULT NULL COMMENT 'Hora del atardecer',
  `aqm_disponible` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1 si Open-Meteo respondió, 0 si falló',
  `aqm_aqi` decimal(6,2) DEFAULT NULL COMMENT 'Índice de Calidad del Aire (US AQI)',
  `aqm_pm10` decimal(7,3) DEFAULT NULL COMMENT 'Material particulado PM10 (μg/m³)',
  `aqm_pm25` decimal(7,3) DEFAULT NULL COMMENT 'Material particulado PM2.5 (μg/m³)',
  `aqm_uv_index` decimal(5,2) DEFAULT NULL COMMENT 'Índice UV',
  `aqm_co` decimal(9,3) DEFAULT NULL COMMENT 'Monóxido de carbono CO (μg/m³)',
  `aqm_no2` decimal(9,3) DEFAULT NULL COMMENT 'Dióxido de nitrógeno NO2 (μg/m³)',
  `aqm_so2` decimal(9,3) DEFAULT NULL COMMENT 'Dióxido de azufre SO2 (μg/m³)',
  `aqm_ozono` decimal(9,3) DEFAULT NULL COMMENT 'Ozono O3 (μg/m³)',
  `guion_texto` mediumtext DEFAULT NULL COMMENT 'Guion completo generado por Gemini',
  `modelo_ia_usado` varchar(80) DEFAULT NULL COMMENT 'Modelo de Gemini utilizado (principal o respaldo)',
  `guion_generado` tinyint(1) NOT NULL DEFAULT 0 COMMENT '1 si el guion fue generado exitosamente',
  `creado_en` datetime NOT NULL DEFAULT current_timestamp() COMMENT 'Momento exacto de inserción en BD'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Historial climatológico completo generado por la radio meteorológica automatizada';

-- --------------------------------------------------------

--
-- Table structure for table `resumen_reporte_clima`
--

CREATE TABLE `resumen_reporte_clima` (
  `id` int(10) UNSIGNED NOT NULL,
  `reporte_id` int(10) UNSIGNED DEFAULT NULL COMMENT 'ID del reporte climatológico asociado',
  `timestamp_log` datetime NOT NULL DEFAULT current_timestamp() COMMENT 'Momento del registro (Server time)',
  `temp` decimal(5,2) DEFAULT NULL COMMENT 'Temperatura actual OWM',
  `condicion` varchar(150) DEFAULT 'N/D' COMMENT 'Condición formateada en texto',
  `humedad` decimal(5,2) DEFAULT NULL COMMENT 'Humedad relativa ambiente',
  `viento` varchar(20) DEFAULT 'N/D' COMMENT 'Velocidad de viento o N/D',
  `aqi` varchar(20) DEFAULT 'N/D' COMMENT 'AQI (String para soportar N/D)',
  `pm25` varchar(20) DEFAULT 'N/D' COMMENT 'PM2.5 (String para soportar N/D)',
  `hora_actualizacion` varchar(10) DEFAULT NULL COMMENT 'Hora asignada en el tablero HH:MM'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Respaldo directo de los datos suministrados al front-end web (datos.json)';

-- --------------------------------------------------------

--
-- Stand-in structure for view `vista_estadisticas_diarias`
-- (See below for the actual view)
--
CREATE TABLE `vista_estadisticas_diarias` (
`fecha_reporte` date
,`total_reportes` bigint(21)
,`temp_promedio_c` decimal(6,2)
,`temp_maxima_c` decimal(5,2)
,`temp_minima_c` decimal(5,2)
,`humedad_promedio_pct` decimal(6,2)
,`lluvia_maxima_hora_mm` decimal(6,2)
,`lluvia_acumulada_dia_mm` decimal(28,2)
,`aqi_promedio` decimal(7,2)
,`uv_maximo_dia` decimal(5,2)
);

-- --------------------------------------------------------

--
-- Stand-in structure for view `vista_historial_resumido`
-- (See below for the actual view)
--
CREATE TABLE `vista_historial_resumido` (
`id` int(10) unsigned
,`timestamp_completo` datetime
,`ciudad` varchar(100)
,`temperatura_actual_c` decimal(5,2)
,`temp_max_c` decimal(5,2)
,`temp_min_c` decimal(5,2)
,`humedad_pct` decimal(5,2)
,`prob_lluvia_pct` decimal(5,2)
,`lluvia_ultima_hora_mm` decimal(6,2)
,`calidad_aire_aqi` decimal(6,2)
,`indice_uv` decimal(5,2)
,`cna_disponible` tinyint(1)
,`owm_disponible` tinyint(1)
,`aqm_disponible` tinyint(1)
,`guion_generado` tinyint(1)
,`modelo_ia_usado` varchar(80)
);

--
-- Indexes for dumped tables
--

--
-- Indexes for table `errores_recoleccion`
--
ALTER TABLE `errores_recoleccion`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_fuente` (`fuente`),
  ADD KEY `idx_timestamp` (`timestamp_error`),
  ADD KEY `fk_errores_reporte` (`reporte_id`);

--
-- Indexes for table `prompt_reporte_climatologico`
--
ALTER TABLE `prompt_reporte_climatologico`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_reporte_id` (`reporte_id`);

--
-- Indexes for table `reportes_climatologicos`
--
ALTER TABLE `reportes_climatologicos`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_fecha` (`fecha_reporte`),
  ADD KEY `idx_timestamp` (`timestamp_completo`),
  ADD KEY `idx_ciudad` (`ciudad`),
  ADD KEY `idx_temp_actual` (`owm_temp_actual`),
  ADD KEY `idx_aqi` (`aqm_aqi`);

--
-- Indexes for table `resumen_reporte_clima`
--
ALTER TABLE `resumen_reporte_clima`
  ADD PRIMARY KEY (`id`),
  ADD KEY `idx_reporte_id` (`reporte_id`);

--
-- AUTO_INCREMENT for dumped tables
--

--
-- AUTO_INCREMENT for table `errores_recoleccion`
--
ALTER TABLE `errores_recoleccion`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `prompt_reporte_climatologico`
--
ALTER TABLE `prompt_reporte_climatologico`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `reportes_climatologicos`
--
ALTER TABLE `reportes_climatologicos`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

--
-- AUTO_INCREMENT for table `resumen_reporte_clima`
--
ALTER TABLE `resumen_reporte_clima`
  MODIFY `id` int(10) UNSIGNED NOT NULL AUTO_INCREMENT;

-- --------------------------------------------------------

--
-- Structure for view `vista_estadisticas_diarias`
--
DROP TABLE IF EXISTS `vista_estadisticas_diarias`;

CREATE ALGORITHM=UNDEFINED DEFINER=`drift3`@`%` SQL SECURITY DEFINER VIEW `vista_estadisticas_diarias`  AS SELECT `reportes_climatologicos`.`fecha_reporte` AS `fecha_reporte`, count(0) AS `total_reportes`, round(avg(`reportes_climatologicos`.`owm_temp_actual`),2) AS `temp_promedio_c`, round(max(`reportes_climatologicos`.`owm_temp_actual`),2) AS `temp_maxima_c`, round(min(`reportes_climatologicos`.`owm_temp_actual`),2) AS `temp_minima_c`, round(avg(`reportes_climatologicos`.`owm_humedad`),2) AS `humedad_promedio_pct`, round(max(`reportes_climatologicos`.`owm_lluvia_1h`),2) AS `lluvia_maxima_hora_mm`, round(sum(`reportes_climatologicos`.`owm_lluvia_1h`),2) AS `lluvia_acumulada_dia_mm`, round(avg(`reportes_climatologicos`.`aqm_aqi`),2) AS `aqi_promedio`, round(max(`reportes_climatologicos`.`aqm_uv_index`),2) AS `uv_maximo_dia` FROM `reportes_climatologicos` GROUP BY `reportes_climatologicos`.`fecha_reporte` ORDER BY `reportes_climatologicos`.`fecha_reporte` DESC ;

-- --------------------------------------------------------

--
-- Structure for view `vista_historial_resumido`
--
DROP TABLE IF EXISTS `vista_historial_resumido`;

CREATE ALGORITHM=UNDEFINED DEFINER=`drift3`@`%` SQL SECURITY DEFINER VIEW `vista_historial_resumido`  AS SELECT `reportes_climatologicos`.`id` AS `id`, `reportes_climatologicos`.`timestamp_completo` AS `timestamp_completo`, `reportes_climatologicos`.`ciudad` AS `ciudad`, `reportes_climatologicos`.`owm_temp_actual` AS `temperatura_actual_c`, `reportes_climatologicos`.`cna_temp_max` AS `temp_max_c`, `reportes_climatologicos`.`cna_temp_min` AS `temp_min_c`, `reportes_climatologicos`.`owm_humedad` AS `humedad_pct`, `reportes_climatologicos`.`cna_prob_lluvia` AS `prob_lluvia_pct`, `reportes_climatologicos`.`owm_lluvia_1h` AS `lluvia_ultima_hora_mm`, `reportes_climatologicos`.`aqm_aqi` AS `calidad_aire_aqi`, `reportes_climatologicos`.`aqm_uv_index` AS `indice_uv`, `reportes_climatologicos`.`cna_disponible` AS `cna_disponible`, `reportes_climatologicos`.`owm_disponible` AS `owm_disponible`, `reportes_climatologicos`.`aqm_disponible` AS `aqm_disponible`, `reportes_climatologicos`.`guion_generado` AS `guion_generado`, `reportes_climatologicos`.`modelo_ia_usado` AS `modelo_ia_usado` FROM `reportes_climatologicos` ORDER BY `reportes_climatologicos`.`timestamp_completo` DESC ;

--
-- Constraints for dumped tables
--

--
-- Constraints for table `errores_recoleccion`
--
ALTER TABLE `errores_recoleccion`
  ADD CONSTRAINT `fk_errores_reporte` FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE SET NULL;

--
-- Constraints for table `prompt_reporte_climatologico`
--
ALTER TABLE `prompt_reporte_climatologico`
  ADD CONSTRAINT `fk_prompt_reporte` FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;

--
-- Constraints for table `resumen_reporte_clima`
--
ALTER TABLE `resumen_reporte_clima`
  ADD CONSTRAINT `fk_resumen_reporte` FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE;
COMMIT;

/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
