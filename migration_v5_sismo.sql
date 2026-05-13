-- ========================================================
-- MIGRACIÓN DE BD: NOAA Stream v4 -> v5 (Sismos y Alertas)
-- ========================================================

-- Crear tabla genérica para eventos especiales (sismos, simulacros, etc.)
CREATE TABLE IF NOT EXISTS condiciones_especiales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp_evento DATETIME NOT NULL,
    tipo VARCHAR(50) NOT NULL COMMENT 'Ej. SISMO, SIMULACRO, HURACAN',
    subtipo VARCHAR(100) COMMENT 'Ej. Magnitud 6.4, o Simulacro Nacional',
    descripcion TEXT COMMENT 'Breve descripción humana del evento',
    
    -- Ubicación (opcional)
    ubicacion VARCHAR(255),
    latitud DECIMAL(10,6),
    longitud DECIMAL(10,6),
    
    -- JSON Data
    datos_sassla JSON COMMENT 'Todos los datos recibidos de la alerta inicial',
    datos_ssn JSON COMMENT 'Datos del sismológico nacional (RSS)',
    datos_investigacion JSON COMMENT 'Datos post-evento de USGS, EMSC, IRIS y réplicas',
    
    -- Guiones y Prompts
    guion_inmediato TEXT COMMENT 'Texto del reporte generado al instante',
    prompt_inmediato TEXT COMMENT 'Prompt usado para el reporte inmediato',
    
    guion_analisis TEXT COMMENT 'Texto del reporte de investigación (35 mins después)',
    prompt_analisis TEXT COMMENT 'Prompt usado para el reporte de investigación',
    
    modelo_ia_usado VARCHAR(50) COMMENT 'Modelo usado para generar los textos'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Índices útiles para búsqueda rápida por tipo y fecha
CREATE INDEX idx_tipo ON condiciones_especiales(tipo);
CREATE INDEX idx_timestamp ON condiciones_especiales(timestamp_evento);
