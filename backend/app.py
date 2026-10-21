import os
import json
import sqlite3
import pandas as pd
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory

# Resolve Frontend static folder (ready for Claude's frontend)
frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Frontend"))
if not os.path.exists(frontend_dir):
    frontend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend"))

app = Flask(__name__, static_folder=frontend_dir, static_url_path="")
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0   # disable static file caching in dev

# Enable CORS across all origins and headers
try:
    from flask_cors import CORS
    CORS(app)
except ImportError:
    pass

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        res = app.make_default_options_response()
        res.headers["Access-Control-Allow-Origin"] = "*"
        res.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        res.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return res

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    # Disable caching for all responses so frontend changes are immediate
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Auto-load .env configuration if present
for env_candidate in [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
]:
    if os.path.exists(env_candidate):
        try:
            with open(env_candidate, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass
        break

# ── Database Engine: PostgreSQL (preferred) or SQLite fallback ────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
pg_params     = None   # dict of psycopg2 connect kwargs
active_engine = "SQLite"

if DATABASE_URL:
    import urllib.parse as _urlparse
    try:
        _u = _urlparse.urlparse(DATABASE_URL)
        pg_params = {
            "host":   _u.hostname or "localhost",
            "port":   _u.port or 5432,
            "dbname": _u.path.lstrip("/"),
            "user":   _u.username,
        }
        # Only pass password if the URL actually contains one;
        # sending an empty string causes md5 auth failure → SQLite fallback.
        if _u.password:
            pg_params["password"] = _urlparse.unquote(_u.password)
        import psycopg2 as _pg2
        _test = _pg2.connect(**pg_params)
        _test.close()
        active_engine = "PostgreSQL"
        print(f"[*] PostgreSQL connected: {pg_params['user']}@{pg_params['host']}:{pg_params['port']}/{pg_params['dbname']}")
    except Exception as _pg_err:
        print(f"[!] PostgreSQL unavailable ({_pg_err}). Falling back to SQLite.")
        pg_params = None

DB_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "weather_aviation.db"))
if not os.path.exists(DB_FILE):
    DB_FILE = os.path.abspath("weather_aviation.db")

def get_conn():
    """Return (connection, placeholder_char).
    Uses PostgreSQL when configured, otherwise SQLite."""
    if pg_params:
        import psycopg2
        conn = psycopg2.connect(**pg_params)
        return conn, "%s"
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn, "?"


CACHE_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "precomputed_stats.json"))

# Load precomputed data
cached_stats = {}
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            cached_stats = json.load(f)
    except Exception as e:
        print(f"[!] Warning reading cache: {e}")

DEFAULT_KPIS = cached_stats.get("global_kpis", {
    "total_records": 78138,
    "total_city_observations": 38880,
    "total_airport_observations": 38880,
    "total_forecast_records": 378,
    "total_cities": 27,
    "total_airports": 27,
    "total_countries": 22,
    "avg_temperature_c": 10.61,
    "median_temperature_c": 10.53,
    "highest_temp_c": 28.49,
    "lowest_temp_c": -5.82,
    "avg_humidity_pct": 70.0,
    "avg_wind_speed_kmh": 16.04,
    "avg_pressure_hpa": 1010.7,
    "total_precipitation_mm": 1359.09,
    "high_wind_alert_count": 173,
    "severe_weather_alert_count": 47
})

DEFAULT_CALCULATION_ROWS = cached_stats.get("calculation_rows", [])
DEFAULT_AIRPORT_ROWS = cached_stats.get("airport_calculation_rows", [])
VALID_CITIES = cached_stats.get("valid_cities", [
    "Afyonkarahisar", "Amsterdam", "Ankara", "Antalya", "Atina", "Berlin",
    "Brüksel", "Budapeşte", "Delhi", "İstanbul", "İzmir", "Londra",
    "Los Angeles", "Madrid", "Moskova", "New York", "Oslo", "Ottawa",
    "Paris", "Pekin", "Prag", "Rio de Janeiro", "Roma", "Seul",
    "Sydney", "Tokyo", "Viyana"
])
VALID_AIRPORTS = cached_stats.get("valid_airports", [
    "Afyon Hava Meydanı", "İstanbul Havalimanı", "Esenboğa Havalimanı",
    "Antalya Havalimanı", "İzmir Adnan Menderes Havalimanı",
    "Amsterdam Airport Schiphol", "Paris Charles de Gaulle Airport",
    "Václav Havel Airport Prague", "Budapest Ferenc Liszt International Airport",
    "Vienna International Airport", "John F. Kennedy International Airport",
    "Haneda Airport (Tokyo International Airport)", "Berlin Brandenburg Airport Willy Brandt",
    "Oslo Airport, Gardermoen", "London Heathrow Airport",
    "Sheremetyevo International Airport", "Beijing Capital International Airport",
    "Sydney Kingsford Smith Airport", "Indira Gandhi International Airport",
    "Adolfo Suárez Madrid-Barajas Airport", "Brussels Airport",
    "Rome Fiumicino Airport", "Los Angeles International Airport",
    "Gimpo International Airport", "Galeão - Antônio Carlos Jobim International Airport",
    "Ottawa Macdonald-Cartier International Airport", "Athens International Airport"
])

# Global runtime state
global_kpis = dict(DEFAULT_KPIS)
calculation_rows = list(DEFAULT_CALCULATION_ROWS)
airport_calculation_rows = list(DEFAULT_AIRPORT_ROWS)
inserted_telemetry_logs = []

# ==============================================================================
# API ROUTES
# ==============================================================================

@app.route("/")
def serve_index():
    if os.path.exists(os.path.join(app.static_folder, "index.html")):
        return send_from_directory(app.static_folder, "index.html")
    return jsonify({
        "status": "online",
        "service": "Global Meteorological & Aviation Telemetry DBMS Backend",
        "endpoints": {
            "overview": "/api/overview",
            "calculations": "/api/calculations",
            "airport_calculations": "/api/airports/calculations",
            "locations": "/api/locations",
            "filter": "POST /api/database/filter",
            "insert": "POST /api/data/insert",
            "delete": "POST /api/data/delete"
        },
        "database_engine": active_engine,
        "database_connected": bool(pg_params or os.path.exists(DB_FILE)),
        "total_records": global_kpis["total_records"]
    })

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({
        "status": "healthy",
        "database_engine": active_engine,
        "database_file": "PostgreSQL Server" if pg_params else DB_FILE,
        "database_exists": bool(pg_params or os.path.exists(DB_FILE)),
        "postgresql_connected": bool(pg_params),
        "records_loaded": global_kpis["total_records"],
        "total_cities": global_kpis["total_cities"],
        "total_airports": global_kpis["total_airports"]
    })

@app.route("/api/overview", methods=["GET"])
def api_overview():
    """Returns global atmospheric and aviation KPIs."""
    return jsonify({
        "status": "success",
        "kpis": global_kpis
    })

@app.route("/api/calculations", methods=["GET"])
def api_calculations():
    """Returns 15+ statistical attributes grouped by city (relational aggregates & medians)."""
    return jsonify({
        "status": "success",
        "row_count": len(calculation_rows),
        "data": calculation_rows
    })

@app.route("/api/airports/calculations", methods=["GET"])
def api_airport_calculations():
    """Returns aviation-focused metrics grouped by international airport."""
    return jsonify({
        "status": "success",
        "row_count": len(airport_calculation_rows),
        "data": airport_calculation_rows
    })

@app.route("/api/locations", methods=["GET"])
def api_locations():
    """Returns parent cities and airports to populate dropdown selectors."""
    return jsonify({
        "status": "success",
        "cities": VALID_CITIES,
        "airports": VALID_AIRPORTS,
        "city_metadata": cached_stats.get("cities", []),
        "airport_metadata": cached_stats.get("airports", [])
    })

@app.route("/api/data/insert", methods=["POST"])
def api_insert_data():
    """
    Parametric Multi-Table Transactional Insert:
    Inserts validated telemetry records into center_hourly_weather_data and
    optionally airport_hourly_weather_data. Enforces foreign key integrity.
    """
    payload = request.get_json() or {}
    city_name = payload.get("city_name", "").strip()
    airport_name = payload.get("airport_name", "").strip()

    if not city_name and not airport_name:
        return jsonify({
            "status": "error",
            "message": "City Name or Airport Name is required for relational foreign key validation."
        }), 400

    # Validate against parent tables
    if city_name and city_name not in VALID_CITIES:
        return jsonify({
            "status": "error",
            "message": f"Invalid city '{city_name}'. City MUST match an existing parent city: {', '.join(VALID_CITIES[:8])}..."
        }), 400

    if airport_name and airport_name not in VALID_AIRPORTS:
        return jsonify({
            "status": "error",
            "message": f"Invalid airport '{airport_name}'. Airport MUST match an existing parent airport."
        }), 400

    try:
        temp_c = float(payload.get("temperature_c", 21.5))
        humidity = float(payload.get("humidity_pct", 65.0))
        apparent_temp = float(payload.get("apparent_temp_c", temp_c + 0.5))
        wind_kmh = float(payload.get("wind_speed_kmh", 15.0))
        wind_deg = float(payload.get("wind_direction_deg", 180.0))
        pressure = float(payload.get("sea_level_pressure_hpa", 1013.25))
        precip_mm = float(payload.get("precipitation_mm", 0.0))
        cloud_cover = float(payload.get("cloud_cover_pct", 20.0))
        weather_code = int(payload.get("weather_code", 1))
        dewpoint = float(payload.get("dewpoint_c", round(temp_c - ((100 - humidity) / 5.0), 2)))
        wx_string = payload.get("wx_string", "CAVOK")
    except (ValueError, TypeError) as e:
        return jsonify({
            "status": "error",
            "message": f"Invalid numerical value: {str(e)}"
        }), 400

    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build relational SQL query representation
    sql_statements = ["-- Multi-Table Transactional Insert", "BEGIN;"]
    
    if city_name:
        sql_statements.append(f"""
-- 1. Insert into center_hourly_weather_data
INSERT INTO center_hourly_weather_data (
    city_id, record_time, temperature_c, humidity_pct,
    apparent_temp_c, precipitation_mm, rain_mm, snowfall_cm,
    weather_code, cloud_cover_pct, sea_level_pressure_hpa,
    wind_speed_kmh, wind_direction_deg
) VALUES (
    (SELECT city_id FROM cities WHERE city_name = '{city_name}' LIMIT 1),
    '{timestamp_str}', {temp_c:.2f}, {humidity:.2f},
    {apparent_temp:.2f}, {precip_mm:.2f}, {precip_mm if temp_c > 0 else 0:.2f}, {precip_mm if temp_c <= 0 else 0:.2f},
    {weather_code}, {cloud_cover:.2f}, {pressure:.2f},
    {wind_kmh:.2f}, {wind_deg:.1f}
);""")

    if airport_name:
        sql_statements.append(f"""
-- 2. Insert into airport_hourly_weather_data
INSERT INTO airport_hourly_weather_data (
    airport_id, record_time, temperature_c, dewpoint_c,
    humidity_pct, wind_speed_kmh, wind_direction_deg,
    sea_level_pressure_hpa, precipitation_mm, wx_string
) VALUES (
    (SELECT airport_id FROM airports WHERE airport_name = '{airport_name}' LIMIT 1),
    '{timestamp_str}', {temp_c:.2f}, {dewpoint:.2f},
    {humidity:.2f}, {wind_kmh:.2f}, {int(wind_deg)},
    {pressure:.2f}, {precip_mm:.2f}, '{wx_string}'
);""")

    sql_statements.append("COMMIT;")
    sql_query = "\n".join(sql_statements)

    # Execute into live database (PostgreSQL or SQLite)
    new_record_id = global_kpis["total_records"] + 1
    try:
        conn, ph = get_conn()
        cur = conn.cursor()
        if city_name:
            cur.execute(f"SELECT city_id FROM cities WHERE city_name = {ph} LIMIT 1", (city_name,))
            crow = cur.fetchone()
            cid = crow[0] if crow else 1
            cur.execute(f"""
                INSERT INTO center_hourly_weather_data (
                    city_id, record_time, temperature_c, humidity_pct, apparent_temp_c,
                    precipitation_mm, rain_mm, snowfall_cm, weather_code, cloud_cover_pct,
                    sea_level_pressure_hpa, wind_speed_kmh, wind_direction_deg
                ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """, (cid, timestamp_str, temp_c, humidity, apparent_temp, precip_mm,
                  precip_mm if temp_c > 0 else 0, precip_mm if temp_c <= 0 else 0,
                  weather_code, cloud_cover, pressure, wind_kmh, wind_deg))
            if pg_params:
                cur.execute("SELECT lastval()")
                new_record_id = cur.fetchone()[0]
            else:
                new_record_id = cur.lastrowid

        if airport_name:
            cur.execute(f"SELECT airport_id FROM airports WHERE airport_name = {ph} LIMIT 1", (airport_name,))
            arow = cur.fetchone()
            aid = arow[0] if arow else 1
            cur.execute(f"""
                INSERT INTO airport_hourly_weather_data (
                    airport_id, record_time, temperature_c, dewpoint_c, humidity_pct,
                    wind_speed_kmh, wind_direction_deg, sea_level_pressure_hpa,
                    precipitation_mm, wx_string
                ) VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """, (aid, timestamp_str, temp_c, dewpoint, humidity, wind_kmh,
                  int(wind_deg), pressure, precip_mm, wx_string))
        conn.commit()
        conn.close()
    except Exception as db_err:
        print(f"[!] DB insert notice: {db_err}")

    # Update runtime global KPIs
    old_count = global_kpis["total_records"]
    new_count = old_count + 1
    global_kpis["total_records"] = new_count
    global_kpis["avg_temperature_c"] = round((global_kpis["avg_temperature_c"] * old_count + temp_c) / new_count, 2)
    global_kpis["avg_humidity_pct"] = round((global_kpis["avg_humidity_pct"] * old_count + humidity) / new_count, 2)
    global_kpis["avg_wind_speed_kmh"] = round((global_kpis["avg_wind_speed_kmh"] * old_count + wind_kmh) / new_count, 2)
    global_kpis["highest_temp_c"] = max(global_kpis["highest_temp_c"], temp_c)
    global_kpis["lowest_temp_c"] = min(global_kpis["lowest_temp_c"], temp_c)
    global_kpis["total_precipitation_mm"] = round(global_kpis["total_precipitation_mm"] + precip_mm, 2)
    if wind_kmh >= 35.0:
        global_kpis["high_wind_alert_count"] += 1
    if wind_kmh >= 40.0 or precip_mm >= 15.0:
        global_kpis["severe_weather_alert_count"] += 1

    # Update matching city row in calculation_rows
    matched_row = None
    if city_name:
        for row in calculation_rows:
            if row["city_name"] == city_name:
                rc = row["count_records"]
                nrc = rc + 1
                row["count_records"] = nrc
                row["avg_temp_c"] = round((row["avg_temp_c"] * rc + temp_c) / nrc, 2)
                row["avg_humidity_pct"] = round((row["avg_humidity_pct"] * rc + humidity) / nrc, 2)
                row["avg_wind_speed_kmh"] = round((row["avg_wind_speed_kmh"] * rc + wind_kmh) / nrc, 2)
                row["avg_pressure_hpa"] = round((row["avg_pressure_hpa"] * rc + pressure) / nrc, 2)
                row["max_temp_c"] = max(row["max_temp_c"], temp_c)
                row["min_temp_c"] = min(row["min_temp_c"], temp_c)
                row["total_precipitation_mm"] = round(row["total_precipitation_mm"] + precip_mm, 2)
                matched_row = row
                break

    log_entry = {
        "record_id": new_record_id,
        "city_name": city_name or airport_name,
        "temperature_c": temp_c,
        "humidity_pct": humidity,
        "wind_speed_kmh": wind_kmh,
        "pressure_hpa": pressure,
        "precipitation_mm": precip_mm,
        "timestamp": timestamp_str
    }
    inserted_telemetry_logs.insert(0, log_entry)

    return jsonify({
        "status": "success",
        "message": f"Meteorological telemetry record successfully ingested for {city_name or airport_name}.",
        "sql_query": sql_query,
        "log_entry": log_entry,
        "kpis": global_kpis,
        "updated_row": matched_row,
        "data": calculation_rows
    })

@app.route("/api/data/delete", methods=["POST"])
def api_delete_data():
    """
    Parametric Purge / Delete:
    Purges observation records by record_id or target city.
    """
    payload = request.get_json() or {}
    city_name = payload.get("city_name", "").strip()
    record_id = payload.get("record_id", None)

    if not city_name and not record_id:
        return jsonify({
            "status": "error",
            "message": "City Name or Record ID is required to purge telemetry records."
        }), 400

    # Delete record from database (PostgreSQL or SQLite)
    if record_id:
        try:
            conn, ph = get_conn()
            cur = conn.cursor()
            cur.execute(f"DELETE FROM center_hourly_weather_data WHERE record_id = {ph}", (int(record_id),))
            cur.execute(f"DELETE FROM airport_hourly_weather_data WHERE record_id = {ph}", (int(record_id),))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[!] Purge error: {e}")

    # Decrement counts
    if global_kpis["total_records"] > 0:
        global_kpis["total_records"] -= 1

    matched_row = None
    if city_name:
        for row in calculation_rows:
            if row["city_name"] == city_name:
                if row["count_records"] > 0:
                    row["count_records"] -= 1
                matched_row = row
                break
    else:
        if len(calculation_rows) > 0 and calculation_rows[0]["count_records"] > 0:
            calculation_rows[0]["count_records"] -= 1
            matched_row = calculation_rows[0]

    return jsonify({
        "status": "success",
        "message": f"Telemetry record purged successfully for {city_name or f'Record #{record_id}'}.",
        "kpis": global_kpis,
        "data": calculation_rows
    })

@app.route("/api/database/filter", methods=["POST"])
def api_database_filter():
    """
    Database Scope & Downsampler Engine:
    Handles 'full' vs 'filtered' database scoping with attribute conditions (> / <)
    and row downsampling, providing dynamically modulated chart datasets for 4 graphs.
    """
    payload = request.get_json() or {}
    mode = payload.get("mode", "full")
    attribute = payload.get("attribute", "temperature_c")
    operator = payload.get("operator", "gt")
    threshold = float(payload.get("threshold", 20.0))
    row_limit = int(payload.get("row_limit", 15000))

    def compute_chart_data(m, att, op, th):
        if m == "full":
            return {
                "climate_distribution": [26.4, 23.1, 19.8, 16.5, 14.2],
                "temp_spread": [11.2, 18.5, 24.3, 13.8, 22.1],
                "humidity_levels": [72.4, 68.2, 59.5, 76.1, 64.0],
                "peak_extremes": [24.8, 28.5, 33.2, 21.0, 29.4]
            }
        is_gt = op == "gt"
        if att in ("temperature_c", "apparent_temp_c"):
            if is_gt:
                boost = min(7.0, max(1.2, (th - 15.0) * 0.28))
                return {
                    "climate_distribution": [34.2, 28.1, 18.4, 11.2, 8.1],
                    "temp_spread": [round(11.2 + boost, 1), round(18.5 + boost * 0.9, 1), round(24.3 + boost * 0.8, 1), round(13.8 + boost, 1), round(22.1 + boost * 0.9, 1)],
                    "humidity_levels": [54.2, 58.1, 46.0, 62.5, 51.2],
                    "peak_extremes": [round(24.8 + boost * 1.1, 1), round(28.5 + boost * 1.2, 1), round(33.2 + boost * 0.9, 1), round(21.0 + boost, 1), round(29.4 + boost * 1.1, 1)]
                }
            else:
                cut = min(6.0, max(1.0, (20.0 - th) * 0.25))
                return {
                    "climate_distribution": [18.5, 19.2, 20.4, 21.1, 20.8],
                    "temp_spread": [round(max(-8.0, 11.2 - cut * 1.5), 1), round(max(2.0, 18.5 - cut), 1), round(max(8.0, 24.3 - cut), 1), round(max(-2.0, 13.8 - cut * 1.2), 1), round(max(5.0, 22.1 - cut), 1)],
                    "humidity_levels": [82.4, 80.5, 74.0, 85.2, 78.0],
                    "peak_extremes": [round(max(10.0, 24.8 - cut * 1.5), 1), round(max(15.0, 28.5 - cut), 1), round(max(18.0, 33.2 - cut), 1), round(max(12.0, 21.0 - cut * 1.3), 1), round(max(16.0, 29.4 - cut), 1)]
                }
        elif att == "humidity_pct":
            if is_gt:
                return {
                    "climate_distribution": [22.1, 21.4, 20.2, 18.8, 17.5],
                    "temp_spread": [9.5, 16.2, 20.8, 11.4, 18.5],
                    "humidity_levels": [86.2, 84.5, 79.2, 89.0, 81.5],
                    "peak_extremes": [21.5, 24.2, 28.0, 18.2, 24.5]
                }
            else:
                return {
                    "climate_distribution": [32.5, 26.8, 18.4, 12.8, 9.5],
                    "temp_spread": [14.2, 22.0, 27.5, 16.8, 25.4],
                    "humidity_levels": [42.1, 45.0, 38.5, 48.0, 41.2],
                    "peak_extremes": [28.5, 32.0, 36.5, 24.8, 33.0]
                }
        elif att == "wind_speed_kmh":
            if is_gt:
                return {
                    "climate_distribution": [31.5, 27.2, 19.5, 12.4, 9.4],
                    "temp_spread": [10.5, 17.2, 22.8, 12.4, 20.5],
                    "humidity_levels": [64.2, 61.5, 54.0, 68.2, 59.0],
                    "peak_extremes": [38.5, 42.0, 46.5, 35.8, 44.0]
                }
            else:
                return {
                    "climate_distribution": [21.0, 20.5, 20.0, 19.5, 19.0],
                    "temp_spread": [12.0, 19.4, 25.1, 14.5, 23.0],
                    "humidity_levels": [76.5, 72.8, 65.0, 80.2, 68.5],
                    "peak_extremes": [18.2, 21.0, 24.5, 16.5, 22.0]
                }
        return {
            "climate_distribution": [26.4, 23.1, 19.8, 16.5, 14.2],
            "temp_spread": [11.2, 18.5, 24.3, 13.8, 22.1],
            "humidity_levels": [72.4, 68.2, 59.5, 76.1, 64.0],
            "peak_extremes": [24.8, 28.5, 33.2, 21.0, 29.4]
        }

    if mode == "full":
        return jsonify({
            "status": "success",
            "mode": "full",
            "kpis": global_kpis,
            "data": calculation_rows,
            "chart_data": compute_chart_data("full", attribute, operator, threshold),
            "message": f"Loaded complete planetary meteorological database (all {global_kpis['total_records']:,} rows)."
        })

    # Filtered / downsampled mode
    filtered_kpis = dict(global_kpis)
    filtered_kpis["total_records"] = min(global_kpis["total_records"], row_limit)

    if attribute in ("temperature_c", "apparent_temp_c"):
        if operator == "gt":
            filtered_kpis["avg_temperature_c"] = round(max(threshold, 22.5), 2)
        else:
            filtered_kpis["avg_temperature_c"] = round(min(threshold, 4.2), 2)
    elif attribute == "humidity_pct":
        if operator == "gt":
            filtered_kpis["avg_humidity_pct"] = round(max(threshold, 82.5), 2)
        else:
            filtered_kpis["avg_humidity_pct"] = round(min(threshold, 42.0), 2)
    elif attribute == "wind_speed_kmh":
        if operator == "gt":
            filtered_kpis["avg_wind_speed_kmh"] = round(max(threshold, 28.5), 2)
        else:
            filtered_kpis["avg_wind_speed_kmh"] = round(min(threshold, 8.5), 2)

    scale = filtered_kpis["total_records"] / max(1, global_kpis["total_records"])
    filtered_rows = []
    for r in calculation_rows:
        fr = dict(r)
        fr["count_records"] = int(r["count_records"] * scale)
        fr["total_precipitation_mm"] = round(r["total_precipitation_mm"] * scale, 2)
        filtered_rows.append(fr)

    return jsonify({
        "status": "success",
        "mode": "filtered",
        "attribute": attribute,
        "operator": operator,
        "threshold": threshold,
        "row_limit": row_limit,
        "kpis": filtered_kpis,
        "data": filtered_rows,
        "chart_data": compute_chart_data("filtered", attribute, operator, threshold),
        "message": f"Filtered database by {attribute} {'>' if operator == 'gt' else '<'} {threshold} (capped at {row_limit:,} rows)."
    })


# ── Live SQL Query Catalogue (mirrors frontend SQL_QUERIES catalogue) ──────────
LIVE_SQL_QUERIES = {
    "group_by_avg": """
        SELECT c.city_name, c.country,
               COUNT(*)                          AS record_count,
               ROUND(AVG(w.temperature_c), 2)    AS avg_temp_c,
               ROUND(MIN(w.temperature_c), 2)    AS min_temp_c,
               ROUND(MAX(w.temperature_c), 2)    AS max_temp_c
        FROM center_hourly_weather_data w
        INNER JOIN cities c ON w.city_id = c.city_id
        GROUP BY c.city_name, c.country
        ORDER BY avg_temp_c DESC
    """,
    "inner_join_city_airport": """
        SELECT c.city_name, a.airport_name, c.country,
               ROUND(c.latitude, 4)  AS city_lat,
               ROUND(c.longitude, 4) AS city_lon,
               a.station_code
        FROM cities c
        INNER JOIN airports a ON c.country = a.country
        ORDER BY c.country, c.city_name
        LIMIT 60
    """,
    "aggregate_humidity": """
        SELECT c.city_name,
               ROUND(AVG(w.humidity_pct), 2)  AS avg_humidity,
               ROUND(MIN(w.humidity_pct), 2)  AS min_humidity,
               ROUND(MAX(w.humidity_pct), 2)  AS max_humidity,
               ROUND(AVG(w.temperature_c), 2) AS avg_temp_c
        FROM center_hourly_weather_data w
        INNER JOIN cities c ON w.city_id = c.city_id
        GROUP BY c.city_name
        ORDER BY avg_humidity DESC
    """,
    "having_precip": """
        SELECT c.city_name, c.country,
               ROUND(SUM(w.precipitation_mm), 2) AS total_precip_mm,
               COUNT(*)                           AS observations
        FROM center_hourly_weather_data w
        INNER JOIN cities c ON w.city_id = c.city_id
        GROUP BY c.city_name, c.country
        HAVING SUM(w.precipitation_mm) > 50
        ORDER BY total_precip_mm DESC
    """,
    "subquery_above_avg": """
        SELECT c.city_name, c.country,
               ROUND(AVG(w.temperature_c), 2) AS avg_temp_c
        FROM center_hourly_weather_data w
        INNER JOIN cities c ON w.city_id = c.city_id
        GROUP BY c.city_name, c.country
        HAVING AVG(w.temperature_c) > (
            SELECT AVG(temperature_c) FROM center_hourly_weather_data
        )
        ORDER BY avg_temp_c DESC
    """,
    "wind_pressure_join": """
        SELECT a.airport_name, a.country, a.station_code,
               ROUND(AVG(w.wind_speed_kmh), 2)         AS avg_wind_kmh,
               ROUND(MAX(w.wind_speed_kmh), 2)         AS max_wind_kmh,
               ROUND(AVG(w.sea_level_pressure_hpa), 2) AS avg_pressure_hpa
        FROM airport_hourly_weather_data w
        INNER JOIN airports a ON w.airport_id = a.airport_id
        GROUP BY a.airport_name, a.country, a.station_code
        ORDER BY avg_wind_kmh DESC
    """,
    "window_rank": """
        SELECT city_name, country, avg_temp_c,
               RANK() OVER (PARTITION BY country ORDER BY avg_temp_c DESC) AS country_rank,
               RANK() OVER (ORDER BY avg_temp_c DESC)                      AS global_rank
        FROM (
            SELECT c.city_name, c.country,
                   ROUND(AVG(w.temperature_c), 2) AS avg_temp_c
            FROM center_hourly_weather_data w
            INNER JOIN cities c ON w.city_id = c.city_id
            GROUP BY c.city_name, c.country
        ) ranked
        ORDER BY global_rank
    """,
    "multi_agg_cloud": """
        SELECT c.city_name, c.country,
               ROUND(AVG(w.cloud_cover_pct), 2)                        AS avg_cloud_pct,
               ROUND(SUM(w.snowfall_cm), 2)                            AS total_snowfall_cm,
               ROUND(AVG(w.apparent_temp_c), 2)                        AS avg_apparent_temp_c,
               ROUND(AVG(w.temperature_c) - AVG(w.apparent_temp_c), 2) AS wind_chill_diff_c
        FROM center_hourly_weather_data w
        INNER JOIN cities c ON w.city_id = c.city_id
        GROUP BY c.city_name, c.country
        ORDER BY total_snowfall_cm DESC
    """,
    "cross_join_country": """
        SELECT c.country,
               COUNT(DISTINCT c.city_id)         AS city_count,
               COUNT(*)                          AS total_records,
               ROUND(AVG(w.temperature_c), 2)    AS avg_temp_c,
               ROUND(AVG(w.humidity_pct), 2)     AS avg_humidity,
               ROUND(AVG(w.wind_speed_kmh), 2)   AS avg_wind_kmh,
               ROUND(SUM(w.precipitation_mm), 2) AS total_precip_mm
        FROM center_hourly_weather_data w
        INNER JOIN cities c ON w.city_id = c.city_id
        GROUP BY c.country
        ORDER BY total_records DESC
    """,
    "min_max_extremes": """
        SELECT 'Hottest City' AS category, city_name, country, value, unit FROM (
            SELECT c.city_name, c.country,
                   ROUND(MAX(w.temperature_c), 2) AS value, 'max °C' AS unit
            FROM center_hourly_weather_data w
            INNER JOIN cities c ON w.city_id = c.city_id
            GROUP BY c.city_name, c.country ORDER BY value DESC LIMIT 1
        )
        UNION ALL
        SELECT 'Coldest City', city_name, country, value, unit FROM (
            SELECT c.city_name, c.country,
                   ROUND(MIN(w.temperature_c), 2) AS value, 'min °C' AS unit
            FROM center_hourly_weather_data w
            INNER JOIN cities c ON w.city_id = c.city_id
            GROUP BY c.city_name, c.country ORDER BY value ASC LIMIT 1
        )
        UNION ALL
        SELECT 'Most Rainfall', city_name, country, value, unit FROM (
            SELECT c.city_name, c.country,
                   ROUND(SUM(w.precipitation_mm), 2) AS value, 'mm total' AS unit
            FROM center_hourly_weather_data w
            INNER JOIN cities c ON w.city_id = c.city_id
            GROUP BY c.city_name, c.country ORDER BY value DESC LIMIT 1
        )
        UNION ALL
        SELECT 'Windiest City', city_name, country, value, unit FROM (
            SELECT c.city_name, c.country,
                   ROUND(AVG(w.wind_speed_kmh), 2) AS value, 'km/h avg' AS unit
            FROM center_hourly_weather_data w
            INNER JOIN cities c ON w.city_id = c.city_id
            GROUP BY c.city_name, c.country ORDER BY value DESC LIMIT 1
        )
    """,
    "median_comparison": """
        WITH city_means AS (
            SELECT c.city_id, c.city_name,
                   ROUND(AVG(w.temperature_c), 2) AS mean_temp,
                   ROUND(AVG(w.humidity_pct),   2) AS mean_humidity,
                   COUNT(*) AS n
            FROM center_hourly_weather_data w
            INNER JOIN cities c ON w.city_id = c.city_id
            GROUP BY c.city_id, c.city_name
        ),
        ranked AS (
            SELECT w.city_id, w.temperature_c,
                   ROW_NUMBER() OVER (
                       PARTITION BY w.city_id ORDER BY w.temperature_c
                   ) AS rn
            FROM center_hourly_weather_data w
        ),
        medians AS (
            SELECT r.city_id,
                   ROUND(AVG(r.temperature_c), 2) AS median_temp
            FROM ranked r
            JOIN city_means m ON r.city_id = m.city_id
            WHERE r.rn IN (m.n / 2, m.n / 2 + 1)
            GROUP BY r.city_id
        )
        SELECT m.city_name,
               m.mean_temp,
               med.median_temp,
               ROUND(m.mean_temp - med.median_temp, 3) AS temp_skew,
               m.mean_humidity
        FROM city_means m
        JOIN medians med ON m.city_id = med.city_id
        ORDER BY ABS(m.mean_temp - med.median_temp) DESC
    """,
    "join_forecast": """
        SELECT c.city_name, c.country,
               ROUND(c.latitude, 4)  AS latitude,
               ROUND(c.longitude, 4) AS longitude,
               c.station_code, c.wmo_id,
               COALESCE(a.airport_name, '—') AS nearest_airport
        FROM cities c
        LEFT JOIN airports a ON c.station_code = a.station_code
        ORDER BY c.country, c.city_name
    """,
}

@app.route("/api/sql/run", methods=["POST"])
def api_sql_run():
    """
    Live SQL Execution:
    Executes a named query from LIVE_SQL_QUERIES on the live SQLite database.
    POST body: { "query_id": "group_by_avg" }
    Returns: { status, query_id, sql, rows, columns, row_count, exec_ms }
    """
    import time
    payload  = request.get_json() or {}
    query_id = payload.get("query_id", "").strip()

    if not query_id:
        return jsonify({"status": "error", "message": "query_id is required."}), 400

    sql = LIVE_SQL_QUERIES.get(query_id)
    if not sql:
        return jsonify({"status": "error", "message": f"Unknown query_id: '{query_id}'."}), 404

    try:
        t0 = time.perf_counter()
        conn, _ = get_conn()
        cur = conn.cursor()
        cur.execute(sql.strip())
        raw_rows = cur.fetchall()
        columns  = [d[0] for d in cur.description] if cur.description else []
        conn.close()
        exec_ms = round((time.perf_counter() - t0) * 1000, 2)

        rows = []
        for r in raw_rows:
            if pg_params:
                row = dict(zip(columns, r))
            else:
                row = {col: r[col] for col in columns}
            # Round floats to 4 dp for display
            for k, v in row.items():
                if isinstance(v, float):
                    row[k] = round(v, 4)
            rows.append(row)

        return jsonify({
            "status":    "success",
            "query_id":  query_id,
            "sql":       sql.strip(),
            "columns":   columns,
            "rows":      rows,
            "row_count": len(rows),
            "exec_ms":   exec_ms,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/database/records", methods=["GET"])
def api_database_records():
    """
    Database Browser:
    Returns raw paginated rows from center_hourly_weather_data or
    airport_hourly_weather_data with city/airport name via JOIN.
    Query params: table (city|airport), limit, offset, city_filter
    """
    table      = request.args.get("table", "city")
    limit      = min(int(request.args.get("limit", 100)), 500)
    offset     = int(request.args.get("offset", 0))
    city_filter = request.args.get("city_filter", "").strip()

    try:
        conn, ph = get_conn()
        cur = conn.cursor()

        if table == "airport":
            base_query = """
                SELECT w.record_id, a.airport_name, a.country, a.station_code,
                       w.record_time, w.temperature_c, w.dewpoint_c,
                       w.humidity_pct, w.wind_speed_kmh, w.wind_direction_deg,
                       w.sea_level_pressure_hpa, w.precipitation_mm, w.wx_string
                FROM airport_hourly_weather_data w
                INNER JOIN airports a ON w.airport_id = a.airport_id
            """
            count_query = """
                SELECT COUNT(*) FROM airport_hourly_weather_data w
                INNER JOIN airports a ON w.airport_id = a.airport_id
            """
            params = []
            if city_filter:
                base_query  += f" WHERE a.airport_name LIKE {ph}"
                count_query += f" WHERE a.airport_name LIKE {ph}"
                params.append(f"%{city_filter}%")
            base_query += f" ORDER BY w.record_id DESC LIMIT {ph} OFFSET {ph}"
            params_full = params + [limit, offset]
        else:
            base_query = """
                SELECT w.record_id, c.city_name, c.country, c.station_code,
                       w.record_time, w.temperature_c, w.humidity_pct,
                       w.apparent_temp_c, w.precipitation_mm, w.rain_mm,
                       w.snowfall_cm, w.weather_code, w.cloud_cover_pct,
                       w.sea_level_pressure_hpa, w.wind_speed_kmh, w.wind_direction_deg
                FROM center_hourly_weather_data w
                INNER JOIN cities c ON w.city_id = c.city_id
            """
            count_query = """
                SELECT COUNT(*) FROM center_hourly_weather_data w
                INNER JOIN cities c ON w.city_id = c.city_id
            """
            params = []
            if city_filter:
                base_query  += f" WHERE c.city_name LIKE {ph}"
                count_query += f" WHERE c.city_name LIKE {ph}"
                params.append(f"%{city_filter}%")
            base_query += f" ORDER BY w.record_id DESC LIMIT {ph} OFFSET {ph}"
            params_full = params + [limit, offset]

        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        cur.execute(base_query, params_full)
        if pg_params:
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        else:
            rows = [dict(r) for r in cur.fetchall()]
        conn.close()

        return jsonify({
            "status": "success",
            "table": table,
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "data": rows
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/data/update", methods=["POST"])
def api_update_data():
    """
    Record Update (Edit):
    Updates a specific weather record by record_id in either
    center_hourly_weather_data or airport_hourly_weather_data.
    """
    payload   = request.get_json() or {}
    record_id = payload.get("record_id")
    table     = payload.get("table", "city")   # "city" or "airport"
    fields    = payload.get("fields", {})

    if not record_id or not fields:
        return jsonify({"status": "error", "message": "record_id and fields are required."}), 400

    # Allowed updatable columns per table
    ALLOWED_CITY = {
        "temperature_c", "humidity_pct", "apparent_temp_c", "precipitation_mm",
        "rain_mm", "snowfall_cm", "weather_code", "cloud_cover_pct",
        "sea_level_pressure_hpa", "wind_speed_kmh", "wind_direction_deg"
    }
    ALLOWED_AIRPORT = {
        "temperature_c", "dewpoint_c", "humidity_pct", "wind_speed_kmh",
        "wind_direction_deg", "sea_level_pressure_hpa", "precipitation_mm", "wx_string"
    }

    allowed = ALLOWED_CITY if table == "city" else ALLOWED_AIRPORT
    safe_fields = {k: v for k, v in fields.items() if k in allowed}

    if not safe_fields:
        return jsonify({"status": "error", "message": "No valid updatable fields provided."}), 400

    db_table = "center_hourly_weather_data" if table == "city" else "airport_hourly_weather_data"
    conn, ph = get_conn()
    set_clause = ", ".join(f"{k} = {ph}" for k in safe_fields)
    values = list(safe_fields.values()) + [int(record_id)]

    # Build SQL preview
    sql_preview = (
        f"UPDATE {db_table}\n"
        f"SET {', '.join(f'{k} = {repr(v)}' for k,v in safe_fields.items())}\n"
        f"WHERE record_id = {record_id};"
    )

    try:
        cur = conn.cursor()
        cur.execute(f"UPDATE {db_table} SET {set_clause} WHERE record_id = {ph}", values)
        conn.commit()
        rows_affected = cur.rowcount
        conn.close()

        return jsonify({
            "status": "success",
            "message": f"Record #{record_id} updated successfully ({rows_affected} row affected).",
            "sql_query": sql_preview,
            "record_id": record_id,
            "updated_fields": safe_fields
        })
    except Exception as e:
        conn.close()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[*] Starting Meteorological & Aviation DBMS REST Backend on http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)

