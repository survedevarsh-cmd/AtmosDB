import os
import sys
import re
import json
import sqlite3
import argparse
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Fix Windows console encoding if needed
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def parse_seed_sql(seed_path):
    """Parses airports and cities from seed.sql."""
    airports = []
    cities = []
    
    if not os.path.exists(seed_path):
        print(f"[!] Warning: seed.sql not found at {seed_path}")
        return airports, cities

    with open(seed_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Parse airports INSERT statements
    airport_matches = re.findall(
        r"INSERT INTO public\.airports\s*\([^)]*\)\s*VALUES\s*\(([^;]+)\);",
        content,
        re.IGNORECASE
    )
    for m in airport_matches:
        parts = [p.strip().strip("'") for p in re.split(r",\s*(?=(?:[^']*'[^']*')*[^']*$)", m)]
        if len(parts) >= 7:
            try:
                airports.append({
                    "airport_id": int(parts[0]),
                    "airport_name": parts[1],
                    "country": parts[2],
                    "latitude": float(parts[3]),
                    "longitude": float(parts[4]),
                    "station_code": parts[5],
                    "wmo_id": parts[6]
                })
            except Exception as e:
                print(f"[!] Error parsing airport row: {e}")

    # Parse cities INSERT statements
    city_matches = re.findall(
        r"INSERT INTO public\.cities\s*\([^)]*\)\s*VALUES\s*\(([^;]+)\);",
        content,
        re.IGNORECASE
    )
    for m in city_matches:
        parts = [p.strip().strip("'") for p in re.split(r",\s*(?=(?:[^']*'[^']*')*[^']*$)", m)]
        if len(parts) >= 7:
            try:
                cities.append({
                    "city_id": int(parts[0]),
                    "city_name": parts[1],
                    "country": parts[2],
                    "latitude": float(parts[3]),
                    "longitude": float(parts[4]),
                    "station_code": parts[5],
                    "wmo_id": parts[6]
                })
            except Exception as e:
                print(f"[!] Error parsing city row: {e}")

    return airports, cities

def create_sqlite_schema(conn):
    """Creates the normalized SQLite schema with primary keys, foreign keys, and indexes."""
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS cities (
        city_id INTEGER PRIMARY KEY,
        city_name TEXT NOT NULL,
        country TEXT NOT NULL,
        latitude REAL NOT NULL,
        longitude REAL NOT NULL,
        station_code TEXT,
        wmo_id TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS airports (
        airport_id INTEGER PRIMARY KEY,
        airport_name TEXT NOT NULL,
        country TEXT,
        latitude REAL,
        longitude REAL,
        station_code TEXT,
        wmo_id TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS center_hourly_weather_data (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        city_id INTEGER NOT NULL,
        record_time TEXT NOT NULL,
        temperature_c REAL,
        humidity_pct REAL,
        apparent_temp_c REAL,
        precipitation_mm REAL,
        rain_mm REAL,
        snowfall_cm REAL,
        weather_code INTEGER,
        cloud_cover_pct REAL,
        sea_level_pressure_hpa REAL,
        wind_speed_kmh REAL,
        wind_direction_deg REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (city_id) REFERENCES cities(city_id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS airport_hourly_weather_data (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        airport_id INTEGER NOT NULL,
        record_time TEXT NOT NULL,
        temperature_c REAL,
        dewpoint_c REAL,
        humidity_pct REAL,
        wind_speed_kmh REAL,
        wind_direction_deg INTEGER,
        sea_level_pressure_hpa REAL,
        precipitation_mm REAL,
        wx_string TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (airport_id) REFERENCES airports(airport_id) ON DELETE CASCADE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_forecast_data (
        forecast_id INTEGER PRIMARY KEY AUTOINCREMENT,
        city_id INTEGER NOT NULL,
        forecast_date TEXT NOT NULL,
        weather_code INTEGER,
        max_temp_c REAL,
        min_temp_c REAL,
        max_wind_speed_kmh REAL,
        wind_direction_deg INTEGER,
        precipitation_sum_mm REAL,
        rain_sum_mm REAL,
        snowfall_sum_cm REAL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (city_id) REFERENCES cities(city_id) ON DELETE CASCADE,
        UNIQUE (city_id, forecast_date)
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS historical_weather (
        record_id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        tavg REAL,
        tmin REAL,
        tmax REAL,
        prcp REAL,
        snow REAL,
        wdir TEXT,
        wspd REAL,
        wpgt REAL,
        pres REAL,
        tsun REAL,
        city_name TEXT
    );
    """)

    # Performance B-Tree Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_center_city_id ON center_hourly_weather_data(city_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_center_time ON center_hourly_weather_data(record_time);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_airport_airport_id ON airport_hourly_weather_data(airport_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_airport_time ON airport_hourly_weather_data(record_time);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_forecast_city_id ON daily_forecast_data(city_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_historical_city ON historical_weather(city_name);")

    conn.commit()

def generate_telemetry_dataset(cities, airports, days=60):
    """
    Synthesizes physically realistic, high-fidelity meteorological time-series records.
    - Diurnal temperature curves (warmer in afternoon, cooler pre-dawn)
    - Latitude-correlated climate baselines (tropical vs temperate vs polar)
    - Mathematically coupled dewpoint and relative humidity
    - Barometric sea level pressures
    - Realistic weather codes (WMO standard) and METAR strings
    """
    np.random.seed(42)
    end_date = datetime.now().replace(minute=0, second=0, microsecond=0)
    start_date = end_date - timedelta(days=days)
    hours_total = days * 24

    center_records = []
    airport_records = []
    forecast_records = []
    historical_records = []

    print(f"[*] Generating {hours_total} hourly records across {len(cities)} cities and {len(airports)} airports...")

    # Weather condition descriptors mapped to WMO codes
    WMO_METAR = {
        0: ("Clear sky", "CAVOK"),
        1: ("Mainly clear", "FEW040"),
        2: ("Partly cloudy", "SCT035"),
        3: ("Overcast", "BKN020"),
        45: ("Foggy", "FG VV002"),
        51: ("Light drizzle", "-DZ SCT015"),
        61: ("Slight rain", "-RA BKN025"),
        63: ("Moderate rain", "RA OVC020"),
        65: ("Heavy rain", "+RA OVC010"),
        71: ("Slight snow", "-SN BKN015"),
        73: ("Moderate snow", "SN OVC010"),
        75: ("Heavy snow", "+SN VV003"),
        95: ("Thunderstorm", "TSRA BKN015CB")
    }

    # Generate City Center Hourly Data
    for city in cities:
        cid = city["city_id"]
        cname = city["city_name"]
        lat = city["latitude"]

        # Base temperature inversely proportional to absolute latitude
        base_temp = 32.0 - (abs(lat) * 0.42) + (np.sin(lat) * 2.0)
        base_pressure = 1014.0 + (np.cos(lat * 0.1) * 3.0)

        for h in range(hours_total):
            cur_time = start_date + timedelta(hours=h)
            time_str = cur_time.strftime("%Y-%m-%d %H:%M:%S")
            hour_of_day = cur_time.hour
            day_of_year = cur_time.timetuple().tm_yday

            # Diurnal cycle (peak at 14:00, trough at 05:00)
            diurnal = 5.5 * np.sin((hour_of_day - 8) * (np.pi / 12.0))
            # Seasonal variation
            seasonal = 4.0 * np.sin(day_of_year * (2 * np.pi / 365.0))
            # Random weather noise
            noise = np.random.normal(0, 1.2)

            temp = round(base_temp + diurnal + seasonal + noise, 2)
            
            # Humidity roughly anti-correlated with temperature
            humidity = round(float(np.clip(70.0 - (diurnal * 2.5) + np.random.normal(0, 5), 18.0, 99.0)), 2)

            # Wind speed (diurnal breezes)
            wind = round(float(np.clip(12.0 + (diurnal * 0.8) + np.random.exponential(4.0), 1.0, 75.0)), 2)
            wind_deg = int((np.random.uniform(0, 360) + (h * 5)) % 360)

            # Barometric pressure
            pressure = round(float(base_pressure - (wind * 0.15) + np.random.normal(0, 2.0)), 2)

            # Cloud cover & precipitation
            cloud = round(float(np.clip((humidity - 40.0) * 1.5 + np.random.normal(0, 10), 0.0, 100.0)), 2)
            has_precip = humidity > 82.0 and cloud > 70.0 and np.random.random() < 0.28
            precip = round(float(np.random.exponential(1.8) if has_precip else 0.0), 2)
            
            rain = precip if temp > 1.5 else 0.0
            snow = round(precip * 0.8, 2) if temp <= 1.5 and precip > 0 else 0.0

            # Apparent temperature (simplified formula)
            apparent_temp = round(temp + (0.33 * (humidity / 100.0 * 6.105 * np.exp((17.27 * temp) / (237.7 + temp)))) - (0.7 * (wind / 3.6)) - 4.0, 2)

            # Weather code
            if snow > 0:
                wcode = 75 if snow > 3.0 else (73 if snow > 1.0 else 71)
            elif rain > 0:
                wcode = 95 if wind > 45.0 else (65 if rain > 5.0 else (63 if rain > 1.5 else 61))
            elif cloud > 80.0:
                wcode = 3
            elif cloud > 40.0:
                wcode = 2
            elif cloud > 15.0:
                wcode = 1
            else:
                wcode = 0

            center_records.append((
                cid, time_str, temp, humidity, apparent_temp, precip, rain, snow,
                wcode, cloud, pressure, wind, float(wind_deg)
            ))

        # Generate 14-day daily forecasts for the city
        for d in range(14):
            f_date = (end_date + timedelta(days=d)).strftime("%Y-%m-%d")
            f_max_temp = round(base_temp + 6.0 + np.random.normal(0, 1.5), 2)
            f_min_temp = round(base_temp - 5.0 + np.random.normal(0, 1.5), 2)
            f_max_wind = round(float(np.clip(15.0 + np.random.exponential(6.0), 5.0, 65.0)), 2)
            f_precip_sum = round(float(np.random.exponential(3.0) if np.random.random() < 0.3 else 0.0), 2)
            f_rain_sum = f_precip_sum if f_min_temp > 0.0 else 0.0
            f_snow_sum = round(f_precip_sum * 0.8, 2) if f_min_temp <= 0.0 and f_precip_sum > 0 else 0.0
            f_wcode = 63 if f_precip_sum > 2.0 else (2 if np.random.random() < 0.5 else 1)
            forecast_records.append((
                cid, f_date, f_wcode, f_max_temp, f_min_temp, f_max_wind,
                int(np.random.uniform(0, 360)), f_precip_sum, f_rain_sum, f_snow_sum
            ))

        # Generate Historical Weather Benchmarks (30 days)
        for d in range(30):
            h_date = (start_date - timedelta(days=d)).strftime("%Y-%m-%d")
            h_tavg = round(base_temp + np.random.normal(0, 2.0), 2)
            h_tmin = round(h_tavg - 5.5 + np.random.normal(0, 1.0), 2)
            h_tmax = round(h_tavg + 6.0 + np.random.normal(0, 1.0), 2)
            h_prcp = round(float(np.random.exponential(2.2) if np.random.random() < 0.25 else 0.0), 2)
            h_snow = round(h_prcp * 0.8, 2) if h_tmin < 0.0 and h_prcp > 0 else 0.0
            h_wspd = round(float(np.clip(14.0 + np.random.exponential(4.0), 3.0, 55.0)), 2)
            h_pres = round(float(base_pressure + np.random.normal(0, 3.0)), 2)
            h_tsun = round(float(np.clip(np.random.uniform(4.0, 12.0), 0.0, 14.0)), 2)
            historical_records.append((
                h_date, h_tavg, h_tmin, h_tmax, h_prcp, h_snow,
                "NW", h_wspd, h_wspd * 1.4, h_pres, h_tsun, cname
            ))

    # Generate Airport Hourly Aviation Data
    for airport in airports:
        aid = airport["airport_id"]
        lat = airport["latitude"]
        base_temp = 31.5 - (abs(lat) * 0.42) + (np.sin(lat) * 2.0)
        base_pressure = 1013.25 + (np.cos(lat * 0.1) * 3.0)

        for h in range(hours_total):
            cur_time = start_date + timedelta(hours=h)
            time_str = cur_time.strftime("%Y-%m-%d %H:%M:%S")
            hour_of_day = cur_time.hour

            diurnal = 5.2 * np.sin((hour_of_day - 8) * (np.pi / 12.0))
            temp = round(base_temp + diurnal + np.random.normal(0, 1.1), 2)
            humidity = round(float(np.clip(68.0 - (diurnal * 2.2) + np.random.normal(0, 4.5), 15.0, 98.0)), 2)
            
            # Dewpoint approximation (Magnus-Tetens)
            dewpoint = round(temp - ((100.0 - humidity) / 5.0), 2)
            
            # Aviation runway winds (often slightly higher in open airfield)
            wind = round(float(np.clip(14.0 + (diurnal * 1.1) + np.random.exponential(5.0), 0.0, 85.0)), 2)
            wind_deg = int((np.random.uniform(0, 360) + (h * 7)) % 360)
            pressure = round(float(base_pressure - (wind * 0.12) + np.random.normal(0, 1.8)), 2)

            precip = round(float(np.random.exponential(2.2) if humidity > 85.0 and np.random.random() < 0.2 else 0.0), 2)
            
            # METAR wx string
            if precip > 4.0:
                wx_str = "+RA OVC010 1800m"
            elif precip > 0.5:
                wx_str = "RA BKN020 4000m"
            elif humidity > 92.0 and wind < 8.0:
                wx_str = "FG VV002 0400m"
            elif wind > 40.0:
                wx_str = f"SCT030 G{int(wind * 1.3)}KT"
            elif temp < 0.0 and precip > 0.0:
                wx_str = "SN OVC015 2500m"
            else:
                wx_str = "CAVOK"

            airport_records.append((
                aid, time_str, temp, dewpoint, humidity, wind, wind_deg,
                pressure, precip, wx_str
            ))

    return center_records, airport_records, forecast_records, historical_records

def compute_and_cache_statistics(cities, airports, center_records, airport_records, forecast_records, output_json_path):
    """Computes exact medians, aggregates, and statistical indicators for lightning-fast API responses."""
    print("[*] Computing statistical aggregates, medians, and KPIs...")

    # Convert city center records to DataFrame
    df_center = pd.DataFrame(center_records, columns=[
        "city_id", "record_time", "temperature_c", "humidity_pct", "apparent_temp_c",
        "precipitation_mm", "rain_mm", "snowfall_cm", "weather_code", "cloud_cover_pct",
        "sea_level_pressure_hpa", "wind_speed_kmh", "wind_direction_deg"
    ])

    # Convert airport records to DataFrame
    df_airport = pd.DataFrame(airport_records, columns=[
        "airport_id", "record_time", "temperature_c", "dewpoint_c", "humidity_pct",
        "wind_speed_kmh", "wind_direction_deg", "sea_level_pressure_hpa", "precipitation_mm", "wx_string"
    ])

    city_lookup = {c["city_id"]: c for c in cities}
    airport_lookup = {a["airport_id"]: a for a in airports}

    # Grouped calculation rows for Cities (Primary View 4 Data Table)
    city_calculation_rows = []
    for cid, group in df_center.groupby("city_id"):
        cmeta = city_lookup.get(cid, {})
        city_calculation_rows.append({
            "city_id": cid,
            "city_name": cmeta.get("city_name", f"City #{cid}"),
            "country": cmeta.get("country", "Unknown"),
            "station_code": cmeta.get("station_code", "-"),
            "wmo_id": cmeta.get("wmo_id", "-"),
            "latitude": cmeta.get("latitude", 0.0),
            "longitude": cmeta.get("longitude", 0.0),
            "count_records": int(len(group)),
            "avg_temp_c": round(float(group["temperature_c"].mean()), 2),
            "median_temp_c": round(float(group["temperature_c"].median()), 2),
            "min_temp_c": round(float(group["temperature_c"].min()), 2),
            "max_temp_c": round(float(group["temperature_c"].max()), 2),
            "avg_humidity_pct": round(float(group["humidity_pct"].mean()), 2),
            "median_humidity_pct": round(float(group["humidity_pct"].median()), 2),
            "avg_apparent_temp_c": round(float(group["apparent_temp_c"].mean()), 2),
            "avg_wind_speed_kmh": round(float(group["wind_speed_kmh"].mean()), 2),
            "median_wind_kmh": round(float(group["wind_speed_kmh"].median()), 2),
            "avg_pressure_hpa": round(float(group["sea_level_pressure_hpa"].mean()), 2),
            "median_pressure_hpa": round(float(group["sea_level_pressure_hpa"].median()), 2),
            "avg_cloud_cover_pct": round(float(group["cloud_cover_pct"].mean()), 2),
            "total_precipitation_mm": round(float(group["precipitation_mm"].sum()), 2),
            "total_snowfall_cm": round(float(group["snowfall_cm"].sum()), 2)
        })

    # Sort alphabetically by country, then city
    city_calculation_rows.sort(key=lambda x: (x["country"], x["city_name"]))

    # Grouped calculation rows for Airports (Aviation Telemetry Table)
    airport_calculation_rows = []
    for aid, group in df_airport.groupby("airport_id"):
        ameta = airport_lookup.get(aid, {})
        airport_calculation_rows.append({
            "airport_id": aid,
            "airport_name": ameta.get("airport_name", f"Airport #{aid}"),
            "country": ameta.get("country", "Unknown"),
            "icao_code": ameta.get("station_code", "-"),
            "wmo_id": ameta.get("wmo_id", "-"),
            "count_records": int(len(group)),
            "avg_temp_c": round(float(group["temperature_c"].mean()), 2),
            "median_temp_c": round(float(group["temperature_c"].median()), 2),
            "avg_dewpoint_c": round(float(group["dewpoint_c"].mean()), 2),
            "avg_dewpoint_spread_c": round(float((group["temperature_c"] - group["dewpoint_c"]).mean()), 2),
            "avg_humidity_pct": round(float(group["humidity_pct"].mean()), 2),
            "avg_surface_wind_kmh": round(float(group["wind_speed_kmh"].mean()), 2),
            "median_wind_kmh": round(float(group["wind_speed_kmh"].median()), 2),
            "peak_wind_gust_kmh": round(float(group["wind_speed_kmh"].max()), 2),
            "avg_qnh_pressure_hpa": round(float(group["sea_level_pressure_hpa"].mean()), 2),
            "total_runway_precip_mm": round(float(group["precipitation_mm"].sum()), 2)
        })

    airport_calculation_rows.sort(key=lambda x: x["avg_surface_wind_kmh"], reverse=True)

    # Global KPI summary
    total_recs = len(df_center) + len(df_airport) + len(forecast_records)
    global_kpis = {
        "total_records": int(total_recs),
        "total_city_observations": int(len(df_center)),
        "total_airport_observations": int(len(df_airport)),
        "total_forecast_records": int(len(forecast_records)),
        "total_cities": int(len(cities)),
        "total_airports": int(len(airports)),
        "total_countries": int(len(set(c["country"] for c in cities))),
        "avg_temperature_c": round(float(df_center["temperature_c"].mean()), 2),
        "median_temperature_c": round(float(df_center["temperature_c"].median()), 2),
        "highest_temp_c": round(float(df_center["temperature_c"].max()), 2),
        "lowest_temp_c": round(float(df_center["temperature_c"].min()), 2),
        "avg_humidity_pct": round(float(df_center["humidity_pct"].mean()), 2),
        "avg_wind_speed_kmh": round(float(df_center["wind_speed_kmh"].mean()), 2),
        "avg_pressure_hpa": round(float(df_center["sea_level_pressure_hpa"].mean()), 2),
        "total_precipitation_mm": round(float(df_center["precipitation_mm"].sum()), 2),
        "high_wind_alert_count": int((df_center["wind_speed_kmh"] >= 35.0).sum()),
        "severe_weather_alert_count": int(((df_center["wind_speed_kmh"] >= 40.0) | (df_center["precipitation_mm"] >= 15.0)).sum())
    }

    cache_payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "global_kpis": global_kpis,
        "cities": cities,
        "airports": airports,
        "valid_cities": [c["city_name"] for c in cities],
        "valid_airports": [a["airport_name"] for a in airports],
        "calculation_rows": city_calculation_rows,
        "airport_calculation_rows": airport_calculation_rows
    }

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(cache_payload, f, indent=2, ensure_ascii=False)

    print(f"[OK] Cached stats written to {output_json_path}")
    print(f"[OK] Global KPIs: {json.dumps(global_kpis, indent=2)}")
    return cache_payload

def run_etl(db_path="weather_aviation.db", seed_path=None):
    print("=" * 65)
    print("METEOROLOGICAL & AVIATION TELEMETRY ETL PIPELINE")
    print("=" * 65)

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if seed_path is None:
        seed_path = os.path.join(base_dir, "database", "seed.sql")

    if not os.path.isabs(db_path):
        db_path = os.path.join(base_dir, db_path)

    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precomputed_stats.json")

    print(f"[*] Reading seeds from: {seed_path}")
    airports, cities = parse_seed_sql(seed_path)
    print(f"[OK] Extracted {len(cities)} cities and {len(airports)} airports.")

    if not cities or not airports:
        print("[!] Error: No cities or airports found in seed.sql!")
        return False

    print(f"[*] Initializing SQLite database at: {db_path}")
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
            print("[*] Replaced existing database file.")
        except Exception as e:
            print(f"[!] Note: {e}")

    conn = sqlite3.connect(db_path)
    create_sqlite_schema(conn)
    cur = conn.cursor()

    # Insert Cities
    print(f"[*] Seeding {len(cities)} cities...")
    for c in cities:
        cur.execute("""
        INSERT INTO cities (city_id, city_name, country, latitude, longitude, station_code, wmo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (c["city_id"], c["city_name"], c["country"], c["latitude"], c["longitude"], c["station_code"], c["wmo_id"]))

    # Insert Airports
    print(f"[*] Seeding {len(airports)} airports...")
    for a in airports:
        cur.execute("""
        INSERT INTO airports (airport_id, airport_name, country, latitude, longitude, station_code, wmo_id)
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """, (a["airport_id"], a["airport_name"], a["country"], a["latitude"], a["longitude"], a["station_code"], a["wmo_id"]))

    conn.commit()

    # Generate synthetic telemetry observations
    center_recs, airport_recs, forecast_recs, hist_recs = generate_telemetry_dataset(cities, airports, days=60)

    # Bulk insert center hourly data
    print(f"[*] Ingesting {len(center_recs):,} city hourly weather observations...")
    cur.executemany("""
    INSERT INTO center_hourly_weather_data (
        city_id, record_time, temperature_c, humidity_pct, apparent_temp_c,
        precipitation_mm, rain_mm, snowfall_cm, weather_code, cloud_cover_pct,
        sea_level_pressure_hpa, wind_speed_kmh, wind_direction_deg
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, center_recs)

    # Bulk insert airport hourly data
    print(f"[*] Ingesting {len(airport_recs):,} airport aviation observations...")
    cur.executemany("""
    INSERT INTO airport_hourly_weather_data (
        airport_id, record_time, temperature_c, dewpoint_c, humidity_pct,
        wind_speed_kmh, wind_direction_deg, sea_level_pressure_hpa, precipitation_mm, wx_string
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, airport_recs)

    # Bulk insert forecast data
    print(f"[*] Ingesting {len(forecast_recs):,} daily forecast records...")
    cur.executemany("""
    INSERT OR REPLACE INTO daily_forecast_data (
        city_id, forecast_date, weather_code, max_temp_c, min_temp_c,
        max_wind_speed_kmh, wind_direction_deg, precipitation_sum_mm, rain_sum_mm, snowfall_sum_cm
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, forecast_recs)

    # Bulk insert historical data
    print(f"[*] Ingesting {len(hist_recs):,} historical climate records...")
    cur.executemany("""
    INSERT INTO historical_weather (
        date, tavg, tmin, tmax, prcp, snow, wdir, wspd, wpgt, pres, tsun, city_name
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
    """, hist_recs)

    conn.commit()
    conn.close()
    print("[OK] Local SQLite database population complete.")

    # Compute and cache statistics
    compute_and_cache_statistics(cities, airports, center_recs, airport_recs, forecast_recs, cache_path)

    print("\n[OK] ETL Pipeline Completed Successfully!")
    return True

def run_pg_etl(pg_url, seed_path=None):
    """Loads schema, seeds, and generated telemetry directly into a PostgreSQL database."""
    print("=" * 65)
    print(f"POSTGRESQL INGESTION: {pg_url.split('@')[-1]}")
    print("=" * 65)

    # Normalize driver if plain postgresql:// provided
    if pg_url.startswith("postgresql://"):
        try:
            import psycopg
            # psycopg (v3) is available
        except ImportError:
            pg_url = pg_url.replace("postgresql://", "postgresql+psycopg2://", 1)

    from sqlalchemy import create_engine, text
    engine = create_engine(pg_url)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if seed_path is None:
        seed_path = os.path.join(base_dir, "database", "seed.sql")
    schema_path = os.path.join(base_dir, "database", "schema.sql")
    cache_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "precomputed_stats.json")

    airports, cities = parse_seed_sql(seed_path)
    print(f"[OK] Extracted {len(cities)} cities and {len(airports)} airports.")

    with engine.begin() as conn:
        print("[*] Testing PostgreSQL connection...")
        conn.execute(text("SELECT 1;"))
        print("[OK] PostgreSQL connection verified.")

        if os.path.exists(schema_path):
            print(f"[*] Executing schema definitions from {schema_path}...")
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
            # Clean psql dump meta commands like \restrict, \unrestrict
            clean_lines = [l for l in schema_sql.splitlines() if not l.strip().startswith("\\")]
            clean_schema = "\n".join(clean_lines)
            
            # Execute statement by statement
            statements = [s.strip() for s in clean_schema.split(";") if s.strip()]
            for stmt in statements:
                try:
                    conn.execute(text(stmt + ";"))
                except Exception as stmt_err:
                    # Ignore table already exists or harmless warnings
                    pass
            print("[OK] Schema executed in PostgreSQL.")

        if os.path.exists(seed_path):
            print(f"[*] Executing seed data from {seed_path}...")
            with open(seed_path, "r", encoding="utf-8") as f:
                seed_sql = f.read()
            clean_seed_lines = [l for l in seed_sql.splitlines() if not l.strip().startswith("\\")]
            clean_seed = "\n".join(clean_seed_lines)
            seed_statements = [s.strip() for s in clean_seed.split(";") if s.strip()]
            for stmt in seed_statements:
                try:
                    conn.execute(text(stmt + ";"))
                except Exception:
                    pass
            print("[OK] Seed data inserted into PostgreSQL.")

    # Generate telemetry dataset
    center_recs, airport_recs, forecast_recs, hist_recs = generate_telemetry_dataset(cities, airports, days=60)

    # Ingest telemetry into PostgreSQL
    print(f"[*] Ingesting {len(center_recs):,} city observations into PostgreSQL...")
    df_center = pd.DataFrame(center_recs, columns=[
        "city_id", "record_time", "temperature_c", "humidity_pct", "apparent_temp_c",
        "precipitation_mm", "rain_mm", "snowfall_cm", "weather_code", "cloud_cover_pct",
        "sea_level_pressure_hpa", "wind_speed_kmh", "wind_direction_deg"
    ])
    df_center.to_sql("center_hourly_weather_data", engine, if_exists="append", index=False, chunksize=5000)

    print(f"[*] Ingesting {len(airport_recs):,} airport observations into PostgreSQL...")
    df_airport = pd.DataFrame(airport_recs, columns=[
        "airport_id", "record_time", "temperature_c", "dewpoint_c", "humidity_pct",
        "wind_speed_kmh", "wind_direction_deg", "sea_level_pressure_hpa", "precipitation_mm", "wx_string"
    ])
    df_airport.to_sql("airport_hourly_weather_data", engine, if_exists="append", index=False, chunksize=5000)

    print(f"[*] Ingesting {len(forecast_recs):,} forecast records into PostgreSQL...")
    df_forecast = pd.DataFrame(forecast_recs, columns=[
        "city_id", "forecast_date", "weather_code", "max_temp_c", "min_temp_c",
        "max_wind_speed_kmh", "wind_direction_deg", "precipitation_sum_mm", "rain_sum_mm", "snowfall_sum_cm"
    ])
    df_forecast.to_sql("daily_forecast_data", engine, if_exists="append", index=False, chunksize=5000)

    # Compute and cache statistics
    compute_and_cache_statistics(cities, airports, center_recs, airport_recs, forecast_recs, cache_path)

    print("\n[OK] Full PostgreSQL Ingestion & Precomputing Complete!")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ETL Pipeline for Meteorological DBMS")
    parser.add_argument("--db", default="weather_aviation.db", help="Path to SQLite database file")
    parser.add_argument("--seed", default=None, help="Path to seed.sql")
    parser.add_argument("--pg-url", default=None, help="PostgreSQL connection string (e.g. postgresql://postgres:password@localhost:5432/weather_db)")
    args = parser.parse_args()

    if args.pg_url:
        run_pg_etl(pg_url=args.pg_url, seed_path=args.seed)
    else:
        run_etl(db_path=args.db, seed_path=args.seed)
