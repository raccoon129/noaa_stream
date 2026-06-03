-- Migration v18: Creación de la tabla datos_fase_lunar
CREATE TABLE IF NOT EXISTS `datos_fase_lunar` (
  `id`                     int(10) UNSIGNED NOT NULL AUTO_INCREMENT,
  `reporte_id`             int(10) UNSIGNED NOT NULL,
  `fase_nombre`            varchar(100)     DEFAULT NULL COMMENT 'Nombre de la fase en español',
  `fase_ingles`            varchar(100)     DEFAULT NULL COMMENT 'Nombre de la fase en inglés',
  `iluminacion_porcentaje` tinyint(3)       DEFAULT NULL COMMENT 'Porcentaje de iluminación (0-100)',
  `salida_luna`            time             DEFAULT NULL COMMENT 'Hora de salida de la luna',
  `ocaso_luna`             time             DEFAULT NULL COMMENT 'Hora de ocaso de la luna',
  `transito_luna`          time             DEFAULT NULL COMMENT 'Hora del cenit lunar',
  `visible_de_dia`         tinyint(1)       DEFAULT NULL COMMENT '1 si es visible de día, 0 si no',
  `fase_etiqueta`          varchar(255)     DEFAULT NULL COMMENT 'Descripción de la fase',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uq_reporte` (`reporte_id`),
  CONSTRAINT `fk_fase_lunar_reporte` FOREIGN KEY (`reporte_id`) REFERENCES `reportes_climatologicos` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Datos de astronomía y fase lunar por reporte climatológico';
