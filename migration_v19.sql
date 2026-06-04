-- ============================================================
-- NOAA Stream — Migración v19
-- Fecha: 2026-06-04
-- Descripción:
--   Amplía la tabla datos_fase_lunar con datos adicionales
--   obtenidos desde la API del Observatorio Naval de los
--   Estados Unidos (USNO / aa.usno.navy.mil).
--
--   Nuevas columnas:
--     crepusculo_inicio   — Inicio del crepúsculo civil (USNO sundata "Begin Civil Twilight")
--     crepusculo_fin      — Fin del crepúsculo civil    (USNO sundata "End Civil Twilight")
--     mediodia_solar      — Mediodía solar / tránsito superior del sol (USNO sundata "Upper Transit")
--     dia_semana          — Día de la semana en inglés  (USNO data.day_of_week)
--     fase_cercana_nombre — Nombre en español de la fase lunar más próxima (USNO closestphase)
--     fase_cercana_fecha  — Fecha exacta de la fase más próxima (USNO closestphase day/month/year)
--     fase_cercana_hora   — Hora de la fase más próxima (USNO closestphase time)
--     fase_cercana_dias   — Días hasta la fase (negativo = ya ocurrió, 0 = hoy)
-- ============================================================

ALTER TABLE `datos_fase_lunar`
  ADD COLUMN `crepusculo_inicio`   TIME        DEFAULT NULL
    COMMENT 'Inicio del crepúsculo civil — USNO sundata "Begin Civil Twilight"',
  ADD COLUMN `crepusculo_fin`      TIME        DEFAULT NULL
    COMMENT 'Fin del crepúsculo civil — USNO sundata "End Civil Twilight"',
  ADD COLUMN `mediodia_solar`      TIME        DEFAULT NULL
    COMMENT 'Hora del mediodía solar (tránsito superior del sol) — USNO sundata "Upper Transit"',
  ADD COLUMN `dia_semana`          VARCHAR(20) DEFAULT NULL
    COMMENT 'Día de la semana en inglés — USNO data.day_of_week',
  ADD COLUMN `fase_cercana_nombre` VARCHAR(60) DEFAULT NULL
    COMMENT 'Nombre en español de la fase lunar más próxima — USNO closestphase.phase',
  ADD COLUMN `fase_cercana_fecha`  DATE        DEFAULT NULL
    COMMENT 'Fecha exacta de la fase más próxima — USNO closestphase day/month/year',
  ADD COLUMN `fase_cercana_hora`   TIME        DEFAULT NULL
    COMMENT 'Hora de la fase más próxima — USNO closestphase.time',
  ADD COLUMN `fase_cercana_dias`   SMALLINT    DEFAULT NULL
    COMMENT 'Días hasta la fase (negativo = ya ocurrió, 0 = hoy) — calculado en Python';
