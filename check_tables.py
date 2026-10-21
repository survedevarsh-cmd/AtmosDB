import time, requests

time.sleep(3)

print('=== Full PostgreSQL Integration Test ===')
base = 'http://127.0.0.1:5000'

# 1. Health check
r = requests.get(f'{base}/api/health')
d = r.json()
print(f'\n[Health] engine={d.get("database_engine")} pg={d.get("postgresql_connected")} records={d.get("records_loaded")}')

# 2. SQL Explorer - run all 12 queries
queries = [
    'group_by_avg', 'inner_join_city_airport', 'aggregate_humidity',
    'having_precip', 'subquery_above_avg', 'wind_pressure_join',
    'window_rank', 'multi_agg_cloud', 'cross_join_country',
    'min_max_extremes', 'median_comparison', 'join_forecast'
]
print('\n[SQL Explorer - Live Queries]')
ok = 0
for q in queries:
    r = requests.post(f'{base}/api/sql/run', json={'query_id': q})
    d = r.json()
    status = d.get('status', '?')
    mark = 'OK' if status == 'success' else 'ERR'
    rows = d.get('row_count', d.get('message', '?'))
    ms = d.get('exec_ms', '?')
    print(f'  [{mark}] {q:<30} {str(rows):>4} rows  {str(ms):>7}ms')
    if status == 'success': ok += 1
print(f'  {ok}/12 queries OK')

# 3. Database Browser
r = requests.get(f'{base}/api/database/records?table=city&limit=3&offset=0&city_filter=')
d = r.json()
print(f'\n[DB Browser - City] total={d.get("total_count")} status={d.get("status")}')

r = requests.get(f'{base}/api/database/records?table=airport&limit=3&offset=0&city_filter=')
d = r.json()
print(f'[DB Browser - Airport] total={d.get("total_count")} status={d.get("status")}')

print('\nDone!')
