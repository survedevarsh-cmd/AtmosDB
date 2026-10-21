-- ==============================================================================
-- DATABASE ANALYTICAL QUERIES & TRANSACTIONAL OPERATIONS
-- Meteorological & Aviation Telemetry DBMS
-- Dialect: PostgreSQL 14+ & ANSI SQL (SQLite compatible equivalents provided)
-- Parent Tables: cities, airports
-- Child Tables: center_hourly_weather_data, airport_hourly_weather_data, daily_forecast_data
-- ==============================================================================

-- ==============================================================================
-- QUERY 1: PRIMARY RELATIONAL CALCULATION REPORT — CITY METEOROLOGY (27 Cities)
-- Multi-Table Joins, Nested Common Table Expressions (CTEs), Aggregates & Medians
-- Joins: cities (parent) + center_hourly_weather_data (child)
-- ==============================================================================
WITH city_medians AS (
    SELECT 
        c.city_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ch.temperature_c) AS median_temp_c,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ch.humidity_pct) AS median_humidity_pct,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ch.wind_speed_kmh) AS median_wind_kmh,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ch.sea_level_pressure_hpa) AS median_pressure_hpa
    FROM cities c
    INNER JOIN center_hourly_weather_data ch ON c.city_id = ch.city_id
    GROUP BY c.city_id
),
city_aggregates AS (
    SELECT 
        c.city_id,
        COUNT(ch.record_id) AS total_observations,
        ROUND(AVG(ch.temperature_c), 2) AS avg_temp_c,
        ROUND(MIN(ch.temperature_c), 2) AS min_temp_c,
        ROUND(MAX(ch.temperature_c), 2) AS max_temp_c,
        ROUND(AVG(ch.humidity_pct), 2) AS avg_humidity_pct,
        ROUND(AVG(ch.apparent_temp_c), 2) AS avg_apparent_temp_c,
        ROUND(AVG(ch.wind_speed_kmh), 2) AS avg_wind_speed_kmh,
        ROUND(AVG(ch.sea_level_pressure_hpa), 2) AS avg_pressure_hpa,
        ROUND(AVG(ch.cloud_cover_pct), 2) AS avg_cloud_cover_pct,
        ROUND(SUM(ch.precipitation_mm), 2) AS total_precipitation_mm,
        ROUND(SUM(ch.snowfall_cm), 2) AS total_snowfall_cm
    FROM cities c
    INNER JOIN center_hourly_weather_data ch ON c.city_id = ch.city_id
    GROUP BY c.city_id
)
SELECT 
    c.city_name,
    c.country,
    c.station_code,
    c.wmo_id,
    c.latitude,
    c.longitude,
    agg.total_observations,
    agg.avg_temp_c,
    ROUND(med.median_temp_c::NUMERIC, 2) AS median_temp_c,
    agg.min_temp_c,
    agg.max_temp_c,
    agg.avg_humidity_pct,
    ROUND(med.median_humidity_pct::NUMERIC, 2) AS median_humidity_pct,
    agg.avg_wind_speed_kmh,
    ROUND(med.median_wind_kmh::NUMERIC, 2) AS median_wind_kmh,
    agg.avg_pressure_hpa,
    ROUND(med.median_pressure_hpa::NUMERIC, 2) AS median_pressure_hpa,
    agg.avg_cloud_cover_pct,
    agg.total_precipitation_mm,
    agg.total_snowfall_cm
FROM cities c
INNER JOIN city_aggregates agg ON c.city_id = agg.city_id
INNER JOIN city_medians med ON c.city_id = med.city_id
ORDER BY c.country ASC, c.city_name ASC;

-- ==============================================================================
-- QUERY 2: AVIATION METEOROLOGY REPORT — AIRPORT TELEMETRY (27 Hubs)
-- Joins: airports (parent) + airport_hourly_weather_data (child)
-- Computes surface winds, dewpoint depression, and barometric altimeter pressure
-- ==============================================================================
WITH airport_medians AS (
    SELECT 
        a.airport_id,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ah.temperature_c) AS median_temp_c,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ah.wind_speed_kmh) AS median_wind_kmh,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ah.sea_level_pressure_hpa) AS median_qnh_hpa
    FROM airports a
    INNER JOIN airport_hourly_weather_data ah ON a.airport_id = ah.airport_id
    GROUP BY a.airport_id
)
SELECT 
    a.airport_name,
    a.country,
    a.station_code AS icao_code,
    a.wmo_id,
    COUNT(ah.record_id) AS flight_observations,
    ROUND(AVG(ah.temperature_c), 2) AS avg_temp_c,
    ROUND(med.median_temp_c::NUMERIC, 2) AS median_temp_c,
    ROUND(AVG(ah.dewpoint_c), 2) AS avg_dewpoint_c,
    ROUND(AVG(ah.temperature_c - ah.dewpoint_c), 2) AS avg_dewpoint_spread_c,
    ROUND(AVG(ah.humidity_pct), 2) AS avg_humidity_pct,
    ROUND(AVG(ah.wind_speed_kmh), 2) AS avg_surface_wind_kmh,
    ROUND(MAX(ah.wind_speed_kmh), 2) AS peak_wind_gust_kmh,
    ROUND(AVG(ah.sea_level_pressure_hpa), 2) AS avg_qnh_pressure_hpa,
    ROUND(SUM(ah.precipitation_mm), 2) AS total_runway_precip_mm
FROM airports a
INNER JOIN airport_hourly_weather_data ah ON a.airport_id = ah.airport_id
INNER JOIN airport_medians med ON a.airport_id = med.airport_id
GROUP BY a.airport_name, a.country, a.station_code, a.wmo_id, med.median_temp_c, med.median_wind_kmh, med.median_qnh_hpa
ORDER BY avg_surface_wind_kmh DESC;

-- ==============================================================================
-- QUERY 3: OVERALL PLANETARY & AVIATION KPIS (Single Aggregate Row)
-- ==============================================================================
SELECT 
    (SELECT COUNT(*) FROM center_hourly_weather_data) AS total_city_observations,
    (SELECT COUNT(*) FROM airport_hourly_weather_data) AS total_airport_observations,
    (SELECT COUNT(*) FROM daily_forecast_data) AS total_forecast_days,
    (SELECT COUNT(DISTINCT country) FROM cities) AS total_monitored_countries,
    (SELECT COUNT(*) FROM cities) AS total_urban_centers,
    (SELECT COUNT(*) FROM airports) AS total_international_airports,
    ROUND(AVG(ch.temperature_c), 2) AS global_avg_temperature_c,
    ROUND(MIN(ch.temperature_c), 2) AS global_min_temperature_c,
    ROUND(MAX(ch.temperature_c), 2) AS global_max_temperature_c,
    ROUND(AVG(ch.humidity_pct), 2) AS global_avg_humidity_pct,
    ROUND(AVG(ch.wind_speed_kmh), 2) AS global_avg_wind_speed_kmh,
    ROUND(AVG(ch.sea_level_pressure_hpa), 2) AS global_avg_pressure_hpa,
    ROUND(SUM(ch.precipitation_mm), 2) AS global_total_precipitation_mm
FROM center_hourly_weather_data ch;

-- ==============================================================================
-- QUERY 4: FLIGHT RISK & SEVERE WEATHER EXTREMES PROFILING
-- Identifies high-wind turbulence, low-visibility fog, and thermal ceilings
-- ==============================================================================
SELECT 
    c.country,
    c.city_name,
    COUNT(CASE WHEN ch.wind_speed_kmh >= 35.0 THEN 1 END) AS high_wind_alert_count,
    COUNT(CASE WHEN ch.temperature_c >= 35.0 THEN 1 END) AS extreme_heat_alert_count,
    COUNT(CASE WHEN ch.temperature_c <= 0.0 THEN 1 END) AS freezing_frost_alert_count,
    COUNT(CASE WHEN ch.precipitation_mm >= 15.0 THEN 1 END) AS heavy_rain_alert_count,
    ROUND(MAX(ch.wind_speed_kmh), 1) AS peak_wind_speed_kmh,
    ROUND(MIN(ch.sea_level_pressure_hpa), 1) AS lowest_barometric_pressure_hpa
FROM cities c
INNER JOIN center_hourly_weather_data ch ON c.city_id = ch.city_id
GROUP BY c.country, c.city_name
ORDER BY high_wind_alert_count DESC, extreme_heat_alert_count DESC;

-- ==============================================================================
-- QUERY 5: PARAMETRIC MULTI-TABLE DATA INSERTION (Parent FK Validated)
-- Inserts a validated urban weather observation and synchronizes daily forecast.
-- Enforces foreign key constraint: city must exist in cities parent table.
-- ==============================================================================
BEGIN;

-- Step 1: Insert into center_hourly_weather_data
INSERT INTO center_hourly_weather_data (
    city_id, record_time, temperature_c, humidity_pct,
    apparent_temp_c, precipitation_mm, rain_mm, snowfall_cm,
    weather_code, cloud_cover_pct, sea_level_pressure_hpa,
    wind_speed_kmh, wind_direction_deg
) VALUES (
    (SELECT city_id FROM cities WHERE city_name = 'İstanbul' LIMIT 1),
    CURRENT_TIMESTAMP,
    21.50,
    64.00,
    22.10,
    0.00,
    0.00,
    0.00,
    1,
    20.00,
    1015.20,
    18.50,
    45.0
);

-- Step 2: Insert matching airport hourly telemetry if applicable
INSERT INTO airport_hourly_weather_data (
    airport_id, record_time, temperature_c, dewpoint_c,
    humidity_pct, wind_speed_kmh, wind_direction_deg,
    sea_level_pressure_hpa, precipitation_mm, wx_string
) VALUES (
    (SELECT airport_id FROM airports WHERE airport_name LIKE '%İstanbul Havalimanı%' LIMIT 1),
    CURRENT_TIMESTAMP,
    21.00,
    14.20,
    65.00,
    20.40,
    50,
    1015.00,
    0.00,
    'FEW025 SCT100'
);

COMMIT;

-- ==============================================================================
-- QUERY 6: PARAMETRIC TELEMETRY PURGE / DELETE (Cascading Delete)
-- Purges records by observation record_id or target city
-- ==============================================================================
BEGIN;
DELETE FROM center_hourly_weather_data
WHERE record_id = 100001;
COMMIT;
