import sqlite3
import psycopg2
import psycopg2.extras
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
import os
import sys

# Locate weather_aviation.db in current folder or parent folder
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_DB = os.path.join(BASE_DIR, 'weather_aviation.db')
if not os.path.exists(SQLITE_DB):
    SQLITE_DB = os.path.abspath(os.path.join(BASE_DIR, '..', 'weather_aviation.db'))

PG_CONN = dict(
    host='localhost',
    port=5432,
    dbname='weather_aviation',
    user='postgres',
    password='Hello#23'
)

TABLES = [
    'cities',
    'airports',
    'center_hourly_weather_data',
    'airport_hourly_weather_data',
    'daily_forecast_data',
    'historical_weather',
]

DDL_STATEMENTS = """
CREATE TABLE IF NOT EXISTS public.cities (
    city_id SERIAL PRIMARY KEY,
    city_name VARCHAR(75) NOT NULL,
    country VARCHAR(75) NOT NULL,
    latitude NUMERIC(9,2) NOT NULL,
    longitude NUMERIC(9,2) NOT NULL,
    station_code VARCHAR(10),
    wmo_id VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS public.airports (
    airport_id SERIAL PRIMARY KEY,
    airport_name VARCHAR(100) NOT NULL,
    country VARCHAR(100),
    latitude NUMERIC(9,2),
    longitude NUMERIC(9,2),
    station_code VARCHAR(10),
    wmo_id VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS public.center_hourly_weather_data (
    record_id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES public.cities(city_id) ON DELETE CASCADE,
    record_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    temperature_c NUMERIC(5,2),
    humidity_pct NUMERIC(5,2),
    apparent_temp_c NUMERIC(5,2),
    precipitation_mm NUMERIC(5,2),
    rain_mm NUMERIC(5,2),
    snowfall_cm NUMERIC(5,2),
    weather_code INTEGER,
    cloud_cover_pct NUMERIC(5,2),
    sea_level_pressure_hpa NUMERIC(6,2),
    wind_speed_kmh NUMERIC(5,2),
    wind_direction_deg NUMERIC(5,2),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_city_record_time UNIQUE (city_id, record_time)
);

CREATE TABLE IF NOT EXISTS public.airport_hourly_weather_data (
    record_id SERIAL PRIMARY KEY,
    airport_id INTEGER REFERENCES public.airports(airport_id) ON DELETE CASCADE,
    record_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    temperature_c NUMERIC(5,2),
    dewpoint_c NUMERIC(5,2),
    humidity_pct NUMERIC(5,2),
    wind_speed_kmh NUMERIC(5,2),
    wind_direction_deg INTEGER,
    sea_level_pressure_hpa NUMERIC(6,2),
    precipitation_mm NUMERIC(5,2),
    wx_string VARCHAR(50),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_airport_record_time UNIQUE (airport_id, record_time)
);

CREATE TABLE IF NOT EXISTS public.daily_forecast_data (
    forecast_id SERIAL PRIMARY KEY,
    city_id INTEGER REFERENCES public.cities(city_id) ON DELETE CASCADE,
    forecast_date DATE NOT NULL,
    weather_code INTEGER,
    max_temp_c NUMERIC(5,2),
    min_temp_c NUMERIC(5,2),
    max_wind_speed_kmh NUMERIC(5,2),
    wind_direction_deg INTEGER,
    precipitation_sum_mm NUMERIC(5,2),
    rain_sum_mm NUMERIC(5,2),
    snowfall_sum_cm NUMERIC(5,2),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (city_id, forecast_date)
);

CREATE TABLE IF NOT EXISTS public.historical_weather (
    record_id SERIAL PRIMARY KEY,
    date TIMESTAMP WITHOUT TIME ZONE,
    tavg DOUBLE PRECISION,
    tmin DOUBLE PRECISION,
    tmax DOUBLE PRECISION,
    prcp DOUBLE PRECISION,
    snow DOUBLE PRECISION,
    wdir TEXT,
    wspd DOUBLE PRECISION,
    wpgt DOUBLE PRECISION,
    pres DOUBLE PRECISION,
    tsun DOUBLE PRECISION,
    city_name TEXT
);

ALTER TABLE public.historical_weather ADD COLUMN IF NOT EXISTS record_id SERIAL;
"""

def ensure_database_exists():
    """Connects to default 'postgres' DB and creates 'weather_aviation' if missing."""
    admin_params = dict(PG_CONN, dbname='postgres')
    conn = psycopg2.connect(**admin_params)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (PG_CONN['dbname'],))
    if not cur.fetchone():
        print(f"[*] Creating PostgreSQL database '{PG_CONN['dbname']}'...")
        cur.execute(f'CREATE DATABASE "{PG_CONN["dbname"]}"')
        print(f"[OK] Database '{PG_CONN['dbname']}' created.")
    else:
        print(f"[OK] Database '{PG_CONN['dbname']}' already exists.")
    cur.close()
    conn.close()

def get_columns(sqlite_cur, table):
    sqlite_cur.execute(f'PRAGMA table_info({table})')
    return [row[1] for row in sqlite_cur.fetchall()]

def migrate_table(sqlite_cur, pg_cur, table, batch_size=2000):
    cols = get_columns(sqlite_cur, table)
    col_list = ', '.join(f'"{c}"' for c in cols)

    sqlite_cur.execute(f'SELECT COUNT(*) FROM {table}')
    total = sqlite_cur.fetchone()[0]
    print(f'\n[{table}] SQLite rows: {total:,}')

    if total == 0:
        print('  -> Skipping (empty in SQLite)')
        return

    sqlite_cur.execute(f'SELECT {col_list} FROM {table}')
    inserted = 0
    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break
        psycopg2.extras.execute_values(
            pg_cur,
            f'INSERT INTO {table} ({col_list}) VALUES %s ON CONFLICT DO NOTHING',
            rows
        )
        inserted += len(rows)
        print(f'  -> Processed {inserted:,}/{total:,}', end='\r')

    print(f'  -> Done: {inserted:,} rows migrated')

def main():
    print('=== SQLite -> PostgreSQL Migration ===')
    print(f'Source: {SQLITE_DB}')
    print(f'Target: PostgreSQL {PG_CONN["host"]}:{PG_CONN["port"]}/{PG_CONN["dbname"]}')

    if not os.path.exists(SQLITE_DB):
        print(f'ERROR: SQLite DB not found at {SQLITE_DB}')
        sys.exit(1)

    try:
        ensure_database_exists()
    except Exception as e:
        print(f'\n[ERROR] Could not connect to PostgreSQL server: {e}')
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SQLITE_DB)
    sqlite_cur  = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(**PG_CONN)
    pg_cur  = pg_conn.cursor()

    print('\n[*] Ensuring PostgreSQL schema & tables exist...')
    pg_cur.execute(DDL_STATEMENTS)
    pg_conn.commit()
    print('[OK] Tables verified.')

    for table in TABLES:
        try:
            migrate_table(sqlite_cur, pg_cur, table)
            pg_conn.commit()
        except Exception as e:
            pg_conn.rollback()
            print(f'\nFAILED on {table}: {e}')

    print('\nSyncing sequences...')
    seq_tables = {
        'cities': ('city_id', 'cities_city_id_seq'),
        'airports': ('airport_id', 'airports_airport_id_seq'),
        'center_hourly_weather_data': ('record_id', 'center_hourly_weather_data_record_id_seq'),
        'airport_hourly_weather_data': ('record_id', 'airport_hourly_weather_data_record_id_seq'),
        'daily_forecast_data': ('forecast_id', 'daily_forecast_data_forecast_id_seq'),
        'historical_weather': ('record_id', 'historical_weather_record_id_seq'),
    }
    for table, (col, seq) in seq_tables.items():
        try:
            pg_cur.execute(f"SELECT setval('{seq}', COALESCE((SELECT MAX({col}) FROM {table}), 1));")
            pg_conn.commit()
            print(f'  Sequence {seq} synced')
        except Exception as e:
            pg_conn.rollback()
            print(f'  Sequence {seq} skipped: {e}')

    sqlite_conn.close()
    pg_conn.close()
    print('\n=== Migration complete! ===')

if __name__ == '__main__':
    main()