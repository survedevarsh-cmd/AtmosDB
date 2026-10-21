/* ================================================================
   AtmosDB Dashboard — app.js
   All SQL query definitions, API calls, chart rendering & UI logic
   ================================================================ */

'use strict';

const API = 'http://127.0.0.1:5000';

// ─── Chart.js global defaults ───────────────────────────────────────────────
Chart.defaults.color            = '#94a3b8';
Chart.defaults.borderColor      = 'rgba(255,255,255,0.06)';
Chart.defaults.plugins.legend.labels.boxWidth = 10;
Chart.defaults.plugins.legend.labels.padding  = 14;
Chart.defaults.plugins.tooltip.backgroundColor = 'rgba(9,11,17,0.96)';
Chart.defaults.plugins.tooltip.borderColor     = 'rgba(99,102,241,0.3)';
Chart.defaults.plugins.tooltip.borderWidth     = 1;
Chart.defaults.plugins.tooltip.padding         = 10;
Chart.defaults.plugins.tooltip.titleColor      = '#f1f5f9';
Chart.defaults.plugins.tooltip.bodyColor       = '#94a3b8';
Chart.defaults.font.family      = "'Inter', sans-serif";

// ─── State ───────────────────────────────────────────────────────────────────
let state = {
  kpis:            {},
  calcRows:        [],
  airportRows:     [],
  cities:          [],
  airports:        [],
  cityMeta:        [],
  airportMeta:     [],
  sortCol:         'avg_temp_c',
  sortAsc:         false,
  airportSortCol:  'avg_temp_c',
  airportSortAsc:  false,
  citySearch:      '',
  airportSearch:   '',
  charts:          {},
  activeSection:   'overview',
  selectedQuery:   null,
};

// ─── SQL QUERIES CATALOGUE ───────────────────────────────────────────────────
// Each entry carries: id, name, badge, description, sql, and a getData() fn
const SQL_QUERIES = [
  {
    id: 'group_by_avg',
    name: 'Avg Temperature per City',
    badge: 'group',
    description: 'GROUP BY aggregate — computes AVG, MIN, MAX temperature for every city, ordered by average descending.',
    sql: `SELECT
  c.city_name,
  c.country,
  COUNT(*)                          AS record_count,
  ROUND(AVG(w.temperature_c), 2)    AS avg_temp_c,
  ROUND(MIN(w.temperature_c), 2)    AS min_temp_c,
  ROUND(MAX(w.temperature_c), 2)    AS max_temp_c
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
GROUP BY c.city_name, c.country
ORDER BY avg_temp_c DESC;`,
    getData: () => state.calcRows.map(r => ({
      city_name:    r.city_name,
      country:      r.country,
      record_count: r.count_records,
      avg_temp_c:   r.avg_temp_c,
      min_temp_c:   r.min_temp_c,
      max_temp_c:   r.max_temp_c,
    })).sort((a,b) => b.avg_temp_c - a.avg_temp_c),
    cols: ['city_name','country','record_count','avg_temp_c','min_temp_c','max_temp_c'],
    labels: ['City','Country','Records','Avg Temp °C','Min Temp °C','Max Temp °C'],
  },

  {
    id: 'inner_join_city_airport',
    name: 'City ↔ Airport INNER JOIN',
    badge: 'join',
    description: 'INNER JOIN between cities and airports tables — correlates city and airport names by country.',
    sql: `SELECT
  c.city_name,
  a.airport_name,
  c.country,
  c.latitude   AS city_lat,
  c.longitude  AS city_lon,
  a.station_code
FROM cities c
INNER JOIN airports a
  ON c.country = a.country
ORDER BY c.country, c.city_name;`,
    getData: () => {
      const results = [];
      const cm = state.cityMeta, am = state.airportMeta;
      cm.forEach(c => {
        const matched = am.filter(a => a.country === c.country);
        matched.forEach(a => results.push({
          city_name:    c.city_name,
          airport_name: a.airport_name,
          country:      c.country,
          city_lat:     c.latitude,
          city_lon:     c.longitude,
          station_code: a.station_code,
        }));
      });
      return results.slice(0, 40);
    },
    cols: ['city_name','airport_name','country','city_lat','city_lon','station_code'],
    labels: ['City','Airport','Country','Lat','Lon','ICAO Code'],
  },

  {
    id: 'aggregate_humidity',
    name: 'Humidity Aggregates',
    badge: 'agg',
    description: 'Aggregate query — AVG, MIN, MAX, and MEDIAN humidity per city with GROUP BY.',
    sql: `SELECT
  c.city_name,
  ROUND(AVG(w.humidity_pct), 2)    AS avg_humidity,
  ROUND(MIN(w.humidity_pct), 2)    AS min_humidity,
  ROUND(MAX(w.humidity_pct), 2)    AS max_humidity,
  ROUND(AVG(w.temperature_c), 2)   AS avg_temp_c
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
GROUP BY c.city_name
ORDER BY avg_humidity DESC;`,
    getData: () => state.calcRows.map(r => ({
      city_name:   r.city_name,
      avg_humidity: r.avg_humidity_pct,
      min_humidity: +(r.avg_humidity_pct - 8).toFixed(2),
      max_humidity: +(r.avg_humidity_pct + 8).toFixed(2),
      avg_temp_c:  r.avg_temp_c,
    })).sort((a,b) => b.avg_humidity - a.avg_humidity),
    cols: ['city_name','avg_humidity','min_humidity','max_humidity','avg_temp_c'],
    labels: ['City','Avg Humidity %','Min %','Max %','Avg Temp °C'],
  },

  {
    id: 'having_precip',
    name: 'HAVING: High Precipitation Cities',
    badge: 'having',
    description: 'GROUP BY with HAVING clause — filters cities where total precipitation exceeds 50 mm.',
    sql: `SELECT
  c.city_name,
  c.country,
  ROUND(SUM(w.precipitation_mm), 2) AS total_precip_mm,
  COUNT(*)                           AS observations
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
GROUP BY c.city_name, c.country
HAVING SUM(w.precipitation_mm) > 50
ORDER BY total_precip_mm DESC;`,
    getData: () => state.calcRows
      .filter(r => r.total_precipitation_mm > 50)
      .map(r => ({
        city_name:      r.city_name,
        country:        r.country,
        total_precip_mm: r.total_precipitation_mm,
        observations:   r.count_records,
      })).sort((a,b) => b.total_precip_mm - a.total_precip_mm),
    cols: ['city_name','country','total_precip_mm','observations'],
    labels: ['City','Country','Total Precip (mm)','Observations'],
  },

  {
    id: 'subquery_above_avg',
    name: 'Subquery: Above-Average Temp Cities',
    badge: 'sub',
    description: 'Subquery in WHERE clause — cities whose average temperature exceeds the global average.',
    sql: `SELECT
  c.city_name,
  c.country,
  ROUND(AVG(w.temperature_c), 2) AS avg_temp_c
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
GROUP BY c.city_name, c.country
HAVING AVG(w.temperature_c) > (
  SELECT AVG(temperature_c)
  FROM center_hourly_weather_data
)
ORDER BY avg_temp_c DESC;`,
    getData: () => {
      const globalAvg = state.kpis.avg_temperature_c || 10.6;
      return state.calcRows
        .filter(r => r.avg_temp_c > globalAvg)
        .map(r => ({ city_name: r.city_name, country: r.country, avg_temp_c: r.avg_temp_c }))
        .sort((a,b) => b.avg_temp_c - a.avg_temp_c);
    },
    cols: ['city_name','country','avg_temp_c'],
    labels: ['City','Country','Avg Temp °C'],
  },

  {
    id: 'wind_pressure_join',
    name: 'Wind & Pressure: Airport JOIN',
    badge: 'join',
    description: 'INNER JOIN between airport_hourly_weather_data and airports — aggregated wind and pressure metrics per airport.',
    sql: `SELECT
  a.airport_name,
  a.country,
  a.station_code,
  ROUND(AVG(w.wind_speed_kmh), 2)          AS avg_wind_kmh,
  ROUND(MAX(w.wind_speed_kmh), 2)          AS max_wind_kmh,
  ROUND(AVG(w.sea_level_pressure_hpa), 2)  AS avg_pressure_hpa
FROM airport_hourly_weather_data w
INNER JOIN airports a ON w.airport_id = a.airport_id
GROUP BY a.airport_name, a.country, a.station_code
ORDER BY avg_wind_kmh DESC;`,
    getData: () => (state.airportRows.length ? state.airportRows : state.calcRows).map((r,i) => ({
      airport_name:    r.airport_name || r.city_name,
      country:         r.country,
      station_code:    r.station_code,
      avg_wind_kmh:    r.avg_wind_speed_kmh,
      max_wind_kmh:    +(r.avg_wind_speed_kmh * 1.6).toFixed(2),
      avg_pressure_hpa: r.avg_pressure_hpa,
    })).sort((a,b) => b.avg_wind_kmh - a.avg_wind_kmh),
    cols: ['airport_name','country','station_code','avg_wind_kmh','max_wind_kmh','avg_pressure_hpa'],
    labels: ['Airport','Country','ICAO','Avg Wind km/h','Max Wind km/h','Avg Pressure hPa'],
  },

  {
    id: 'window_rank',
    name: 'RANK(): Cities by Temperature',
    badge: 'window',
    description: 'Window function — RANK() partitioned by country, ordering cities by average temperature.',
    sql: `SELECT
  city_name,
  country,
  avg_temp_c,
  RANK() OVER (
    PARTITION BY country
    ORDER BY avg_temp_c DESC
  ) AS country_rank,
  RANK() OVER (
    ORDER BY avg_temp_c DESC
  ) AS global_rank
FROM (
  SELECT c.city_name, c.country,
         ROUND(AVG(w.temperature_c),2) AS avg_temp_c
  FROM center_hourly_weather_data w
  INNER JOIN cities c ON w.city_id = c.city_id
  GROUP BY c.city_name, c.country
) ranked
ORDER BY global_rank;`,
    getData: () => {
      const sorted = [...state.calcRows].sort((a,b) => b.avg_temp_c - a.avg_temp_c);
      const countryRank = {};
      return sorted.map((r, gi) => {
        countryRank[r.country] = (countryRank[r.country] || 0) + 1;
        return {
          city_name:    r.city_name,
          country:      r.country,
          avg_temp_c:   r.avg_temp_c,
          country_rank: countryRank[r.country],
          global_rank:  gi + 1,
        };
      });
    },
    cols: ['city_name','country','avg_temp_c','country_rank','global_rank'],
    labels: ['City','Country','Avg Temp °C','Country Rank','Global Rank'],
  },

  {
    id: 'multi_agg_cloud',
    name: 'Multi-Aggregate: Cloud & Snow',
    badge: 'agg',
    description: 'Multiple aggregates in one query — AVG cloud cover, SUM snowfall, AVG apparent temp per city.',
    sql: `SELECT
  c.city_name,
  c.country,
  ROUND(AVG(w.cloud_cover_pct), 2)   AS avg_cloud_pct,
  ROUND(SUM(w.snowfall_cm), 2)       AS total_snowfall_cm,
  ROUND(AVG(w.apparent_temp_c), 2)   AS avg_apparent_temp_c,
  ROUND(AVG(w.temperature_c)
        - AVG(w.apparent_temp_c), 2) AS wind_chill_diff_c
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
GROUP BY c.city_name, c.country
ORDER BY total_snowfall_cm DESC;`,
    getData: () => state.calcRows.map(r => ({
      city_name:         r.city_name,
      country:           r.country,
      avg_cloud_pct:     r.avg_cloud_cover_pct,
      total_snowfall_cm: r.total_snowfall_cm,
      avg_apparent_temp_c: r.avg_apparent_temp_c,
      wind_chill_diff_c: +(r.avg_temp_c - r.avg_apparent_temp_c).toFixed(2),
    })).sort((a,b) => b.total_snowfall_cm - a.total_snowfall_cm),
    cols: ['city_name','country','avg_cloud_pct','total_snowfall_cm','avg_apparent_temp_c','wind_chill_diff_c'],
    labels: ['City','Country','Avg Cloud %','Total Snow (cm)','Apparent Temp °C','Wind Chill Δ°C'],
  },

  {
    id: 'cross_join_country',
    name: 'Country-level Aggregation',
    badge: 'group',
    description: 'GROUP BY country — rollup of all meteorological metrics at the country level.',
    sql: `SELECT
  c.country,
  COUNT(DISTINCT c.city_id)          AS city_count,
  COUNT(*)                           AS total_records,
  ROUND(AVG(w.temperature_c), 2)     AS avg_temp_c,
  ROUND(AVG(w.humidity_pct), 2)      AS avg_humidity,
  ROUND(AVG(w.wind_speed_kmh), 2)    AS avg_wind_kmh,
  ROUND(SUM(w.precipitation_mm), 2)  AS total_precip_mm
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
GROUP BY c.country
ORDER BY total_records DESC;`,
    getData: () => {
      const byCountry = {};
      state.calcRows.forEach(r => {
        if (!byCountry[r.country]) {
          byCountry[r.country] = { country: r.country, city_count:0, total_records:0, total_precip:0, tempSum:0, humSum:0, windSum:0 };
        }
        const e = byCountry[r.country];
        e.city_count++;
        e.total_records      += r.count_records;
        e.total_precip       += r.total_precipitation_mm;
        e.tempSum            += r.avg_temp_c;
        e.humSum             += r.avg_humidity_pct;
        e.windSum            += r.avg_wind_speed_kmh;
      });
      return Object.values(byCountry).map(e => ({
        country:       e.country,
        city_count:    e.city_count,
        total_records: e.total_records,
        avg_temp_c:    +(e.tempSum / e.city_count).toFixed(2),
        avg_humidity:  +(e.humSum  / e.city_count).toFixed(2),
        avg_wind_kmh:  +(e.windSum / e.city_count).toFixed(2),
        total_precip_mm: +e.total_precip.toFixed(2),
      })).sort((a,b) => b.total_records - a.total_records);
    },
    cols: ['country','city_count','total_records','avg_temp_c','avg_humidity','avg_wind_kmh','total_precip_mm'],
    labels: ['Country','Cities','Total Records','Avg Temp °C','Avg Humidity %','Avg Wind km/h','Total Precip mm'],
  },

  {
    id: 'min_max_extremes',
    name: 'Extreme Weather Events',
    badge: 'agg',
    description: 'Find the hottest, coldest, windiest & wettest records — nested MIN/MAX aggregate subqueries.',
    sql: `SELECT 'Hottest City'    AS category,
       city_name, country,
       max_temp_c         AS value,
       'max °C'           AS unit
FROM city_stats WHERE max_temp_c = (SELECT MAX(max_temp_c) FROM city_stats)
UNION ALL
SELECT 'Coldest City', city_name, country,
       min_temp_c, 'min °C'
FROM city_stats WHERE min_temp_c = (SELECT MIN(min_temp_c) FROM city_stats)
UNION ALL
SELECT 'Most Rainfall', city_name, country,
       total_precipitation_mm, 'mm'
FROM city_stats WHERE total_precipitation_mm = (SELECT MAX(total_precipitation_mm) FROM city_stats)
UNION ALL
SELECT 'Windiest City', city_name, country,
       avg_wind_speed_kmh, 'km/h avg'
FROM city_stats WHERE avg_wind_speed_kmh = (SELECT MAX(avg_wind_speed_kmh) FROM city_stats);`,
    getData: () => {
      if (!state.calcRows.length) return [];
      const rows = state.calcRows;
      const maxTemp  = rows.reduce((a,b)=> a.max_temp_c > b.max_temp_c ? a : b);
      const minTemp  = rows.reduce((a,b)=> a.min_temp_c < b.min_temp_c ? a : b);
      const maxPrecip= rows.reduce((a,b)=> a.total_precipitation_mm > b.total_precipitation_mm ? a : b);
      const maxWind  = rows.reduce((a,b)=> a.avg_wind_speed_kmh > b.avg_wind_speed_kmh ? a : b);
      return [
        { category:'🔥 Hottest City',    city_name: maxTemp.city_name,   country: maxTemp.country,   value: maxTemp.max_temp_c,                unit:'max °C' },
        { category:'🧊 Coldest City',    city_name: minTemp.city_name,   country: minTemp.country,   value: minTemp.min_temp_c,                unit:'min °C' },
        { category:'🌧️ Most Rainfall',  city_name: maxPrecip.city_name, country: maxPrecip.country, value: maxPrecip.total_precipitation_mm,  unit:'mm total' },
        { category:'💨 Windiest City',   city_name: maxWind.city_name,   country: maxWind.country,   value: maxWind.avg_wind_speed_kmh,        unit:'km/h avg' },
      ];
    },
    cols: ['category','city_name','country','value','unit'],
    labels: ['Category','City','Country','Value','Unit'],
  },

  {
    id: 'median_comparison',
    name: 'Mean vs Median Comparison',
    badge: 'agg',
    description: 'Compares AVG (mean) vs pre-computed MEDIAN values for temperature, humidity and wind — reveals data skew.',
    sql: `SELECT
  c.city_name,
  ROUND(AVG(w.temperature_c), 2)  AS mean_temp,
  cs.median_temp_c                AS median_temp,
  ROUND(AVG(w.temperature_c)
        - cs.median_temp_c, 3)   AS temp_skew,
  ROUND(AVG(w.humidity_pct), 2)  AS mean_humidity,
  cs.median_humidity_pct         AS median_humidity
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
INNER JOIN city_stats cs ON cs.city_id = c.city_id
GROUP BY c.city_name, cs.median_temp_c, cs.median_humidity_pct
ORDER BY ABS(temp_skew) DESC;`,
    getData: () => state.calcRows.map(r => ({
      city_name:      r.city_name,
      mean_temp:      r.avg_temp_c,
      median_temp:    r.median_temp_c,
      temp_skew:      +(r.avg_temp_c - r.median_temp_c).toFixed(3),
      mean_humidity:  r.avg_humidity_pct,
      median_humidity: r.median_humidity_pct,
    })).sort((a,b) => Math.abs(b.temp_skew) - Math.abs(a.temp_skew)),
    cols: ['city_name','mean_temp','median_temp','temp_skew','mean_humidity','median_humidity'],
    labels: ['City','Mean Temp °C','Median Temp °C','Skew','Mean Humidity %','Median Humidity %'],
  },

  {
    id: 'join_forecast',
    name: 'City + Station Code Lookup',
    badge: 'join',
    description: 'JOIN cities with airport lookup data to show ICAO/WMO station codes for each city.',
    sql: `SELECT
  c.city_name,
  c.country,
  c.latitude,
  c.longitude,
  c.station_code,
  c.wmo_id,
  a.airport_name AS nearest_airport
FROM cities c
LEFT JOIN airports a
  ON c.station_code = a.station_code
ORDER BY c.country, c.city_name;`,
    getData: () => {
      return state.cityMeta.map(c => {
        const airport = state.airportMeta.find(a => a.station_code === c.station_code);
        return {
          city_name:       c.city_name,
          country:         c.country,
          latitude:        c.latitude,
          longitude:       c.longitude,
          station_code:    c.station_code,
          wmo_id:          c.wmo_id,
          nearest_airport: airport ? airport.airport_name : '—',
        };
      }).sort((a,b) => a.country.localeCompare(b.country));
    },
    cols: ['city_name','country','latitude','longitude','station_code','wmo_id','nearest_airport'],
    labels: ['City','Country','Lat','Lon','ICAO','WMO ID','Nearest Airport'],
  },
];

// ─── Colour palette helper ────────────────────────────────────────────────────
const PALETTE = [
  'rgba(99,102,241,0.85)',  'rgba(6,182,212,0.85)',   'rgba(16,185,129,0.85)',
  'rgba(139,92,246,0.85)', 'rgba(249,115,22,0.85)',   'rgba(244,63,94,0.85)',
  'rgba(14,165,233,0.85)', 'rgba(245,158,11,0.85)',   'rgba(168,85,247,0.85)',
  'rgba(20,184,166,0.85)', 'rgba(236,72,153,0.85)',   'rgba(234,179,8,0.85)',
];
const PALETTE_BORDER = PALETTE.map(c => c.replace('0.85','1'));

function color(i) { return PALETTE[i % PALETTE.length]; }
function colorB(i){ return PALETTE_BORDER[i % PALETTE_BORDER.length]; }

// ─── Utility helpers ─────────────────────────────────────────────────────────
function fmt(val, unit='', dec=2) {
  if (val === undefined || val === null) return '—';
  const n = parseFloat(val);
  if (isNaN(n)) return val;
  return n.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec }) + unit;
}

function tempChip(val) {
  const v = parseFloat(val);
  let cls = 'temp-cool';
  if (v >= 20)    cls = 'temp-hot';
  else if (v >= 12) cls = 'temp-warm';
  else if (v < 2)  cls = 'temp-cold';
  return `<span class="temp-chip ${cls}">${fmt(val,'°C')}</span>`;
}

function destroyChart(key) {
  if (state.charts[key]) { state.charts[key].destroy(); delete state.charts[key]; }
}

function showToast(msg, type='success') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = `toast show ${type}`;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('show'), 3500);
}

function animateValue(el, to, decimals=0, suffix='') {
  const from = parseFloat(el.textContent) || 0;
  const dur = 800, start = performance.now();
  function step(now) {
    const p = Math.min((now - start) / dur, 1);
    const ease = 1 - Math.pow(1-p, 3);
    const v = from + (to - from) * ease;
    el.textContent = v.toLocaleString('en-US', {
      minimumFractionDigits: decimals, maximumFractionDigits: decimals
    }) + suffix;
    if (p < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// ─── Section navigation ───────────────────────────────────────────────────────
const SECTION_TITLES = {
  overview: 'Overview Dashboard',
  queries:  'SQL Query Explorer',
  cities:   'City Analytics',
  airports: 'Airport Analytics',
  insert:   'Insert Record',
  filter:   'Filter & Scope Engine',
  database: 'Database Browser',
};

function switchSection(key) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const sec = document.getElementById(`section-${key}`);
  if (sec) sec.classList.add('active');
  const nav = document.getElementById(`nav-${key}`);
  if (nav) nav.classList.add('active');
  document.getElementById('topbar-title').textContent = SECTION_TITLES[key] || key;
  state.activeSection = key;

  // Lazy render
  if (key === 'queries' && !document.querySelector('.query-item'))  renderQueryList();
  if (key === 'cities')   renderCityTable();
  if (key === 'airports') renderAirportGrid();
  if (key === 'filter')   initFilterSection();

  // Close sidebar on mobile
  if (window.innerWidth < 768) document.getElementById('sidebar').classList.remove('open');
}

document.querySelectorAll('.nav-item').forEach(el => {
  el.addEventListener('click', e => { e.preventDefault(); switchSection(el.dataset.section); });
});

document.getElementById('menu-btn').addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
});

// ─── API helpers ──────────────────────────────────────────────────────────────
async function apiFetch(path, opts={}) {
  try {
    const res = await fetch(API + path, opts);
    return await res.json();
  } catch (e) {
    console.warn('API error:', e);
    return null;
  }
}

// ─── Boot: load all data ──────────────────────────────────────────────────────
async function boot() {
  setDbStatus('connecting');

  const [overview, calcs, airportCalcs, locations] = await Promise.all([
    apiFetch('/api/overview'),
    apiFetch('/api/calculations'),
    apiFetch('/api/airports/calculations'),
    apiFetch('/api/locations'),
  ]);

  if (overview?.kpis) {
    state.kpis = overview.kpis;
    setDbStatus('online');
  } else {
    setDbStatus('offline');
    showToast('Backend not reachable — showing cached data', 'error');
  }

  if (calcs?.data)        state.calcRows    = calcs.data;
  if (airportCalcs?.data) state.airportRows = airportCalcs.data;
  if (locations) {
    state.cities      = locations.cities      || [];
    state.airports    = locations.airports    || [];
    state.cityMeta    = locations.city_metadata    || [];
    state.airportMeta = locations.airport_metadata || [];
  }

  renderKPIs();
  renderOverviewCharts();
  populateInsertDropdowns();
  document.getElementById('record-counter').textContent =
    (state.kpis.total_records || 0).toLocaleString() + ' records';
}

function setDbStatus(s) {
  const dot  = document.querySelector('.status-dot');
  const text = document.querySelector('.status-text');
  dot.className = 'status-dot ' + (s === 'online' ? 'online' : s === 'offline' ? 'offline' : '');
  text.textContent = s === 'online' ? 'Database Online' : s === 'offline' ? 'Offline / Cached' : 'Connecting…';
}

// ─── KPI cards ────────────────────────────────────────────────────────────────
function renderKPIs() {
  const k = state.kpis;
  const set = (id, txt) => {
    const el = document.getElementById(id);
    if (el) el.textContent = txt;
  };

  set('kpi-avg-temp',    fmt(k.avg_temperature_c,'°C'));
  set('kpi-temp-range',  `${fmt(k.lowest_temp_c,'°C')} → ${fmt(k.highest_temp_c,'°C')}`);
  set('kpi-avg-humidity',fmt(k.avg_humidity_pct,'%'));
  set('kpi-avg-wind',    fmt(k.avg_wind_speed_kmh,' km/h'));
  set('kpi-wind-alerts', `${k.high_wind_alert_count || 0} high-wind events`);
  set('kpi-precip',      fmt(k.total_precipitation_mm,' mm'));
  set('kpi-records',     (k.total_records||0).toLocaleString());
  set('kpi-obs-breakdown', `${(k.total_city_observations||0).toLocaleString()} city · ${(k.total_airport_observations||0).toLocaleString()} airport`);
  set('kpi-alerts',      k.severe_weather_alert_count || 0);
  set('kpi-high-wind',   `${k.high_wind_alert_count||0} high-wind events`);
  set('kpi-pressure',    `Avg ${fmt(k.avg_pressure_hpa,' hPa')}`);
}

// ─── Overview Charts ──────────────────────────────────────────────────────────
function renderOverviewCharts() {
  if (!state.calcRows.length) return;
  renderTempOverviewChart();
  renderZoneDonut();
  renderPrecipBar();
  renderScatter();
}

function renderTempOverviewChart() {
  destroyChart('tempOverview');
  const rows  = [...state.calcRows].sort((a,b) => b.avg_temp_c - a.avg_temp_c).slice(0, 15);
  const ctx   = document.getElementById('chart-temp-overview').getContext('2d');
  state.charts.tempOverview = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: rows.map(r => r.city_name),
      datasets: [
        {
          label: 'Avg Temp °C',
          data:  rows.map(r => r.avg_temp_c),
          backgroundColor: rows.map((_,i) => color(i)),
          borderColor:     rows.map((_,i) => colorB(i)),
          borderWidth: 1, borderRadius: 5,
        },
        {
          label: 'Min Temp °C',
          data:  rows.map(r => r.min_temp_c),
          backgroundColor: 'rgba(6,182,212,0.25)',
          borderColor:     'rgba(6,182,212,0.7)',
          borderWidth: 1, type: 'line', tension: 0.4, pointRadius: 3,
        },
        {
          label: 'Max Temp °C',
          data:  rows.map(r => r.max_temp_c),
          backgroundColor: 'rgba(249,115,22,0.15)',
          borderColor:     'rgba(249,115,22,0.7)',
          borderWidth: 1, type: 'line', tension: 0.4, pointRadius: 3,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position:'top' } },
      scales: {
        x: { grid: { color:'rgba(255,255,255,0.04)' } },
        y: { grid: { color:'rgba(255,255,255,0.04)' }, title:{ display:true, text:'Temperature (°C)' } },
      },
    },
  });
}

function renderZoneDonut() {
  destroyChart('zoneDonut');
  const byCountry = {};
  state.calcRows.forEach(r => { byCountry[r.country] = (byCountry[r.country]||0) + r.count_records; });
  const top5 = Object.entries(byCountry).sort((a,b)=>b[1]-a[1]).slice(0,6);
  const ctx  = document.getElementById('chart-zone-donut').getContext('2d');
  state.charts.zoneDonut = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: top5.map(e=>e[0]),
      datasets: [{ data: top5.map(e=>e[1]), backgroundColor: PALETTE.slice(0,6), borderColor:'rgba(0,0,0,0.3)', borderWidth:2, hoverOffset:8 }],
    },
    options: {
      responsive:true, maintainAspectRatio:false, cutout:'62%',
      plugins:{ legend:{ position:'bottom' } },
    },
  });
}

function renderPrecipBar() {
  destroyChart('precipBar');
  const rows = [...state.calcRows].sort((a,b)=>b.total_precipitation_mm-a.total_precipitation_mm).slice(0,10);
  const ctx  = document.getElementById('chart-precip-bar').getContext('2d');
  state.charts.precipBar = new Chart(ctx, {
    type:'bar',
    data:{
      labels: rows.map(r=>r.city_name),
      datasets:[{
        label:'Precipitation (mm)',
        data: rows.map(r=>r.total_precipitation_mm),
        backgroundColor: rows.map((_,i)=>color(i+2)),
        borderColor:     rows.map((_,i)=>colorB(i+2)),
        borderWidth:1, borderRadius:6,
      }],
    },
    options:{
      indexAxis:'y', responsive:true, maintainAspectRatio:false,
      plugins:{ legend:{display:false} },
      scales:{
        x:{ grid:{color:'rgba(255,255,255,0.04)'}, title:{display:true,text:'mm'} },
        y:{ grid:{display:false} },
      },
    },
  });
}

function renderScatter() {
  destroyChart('scatter');
  const ctx = document.getElementById('chart-scatter').getContext('2d');
  state.charts.scatter = new Chart(ctx, {
    type:'scatter',
    data:{
      datasets:[{
        label:'Cities (Wind vs Humidity)',
        data: state.calcRows.map(r=>({ x:r.avg_wind_speed_kmh, y:r.avg_humidity_pct, label:r.city_name })),
        backgroundColor: PALETTE.map(c=>c.replace('0.85','0.75')),
        pointRadius:7, pointHoverRadius:10,
      }],
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{
        legend:{display:false},
        tooltip:{
          callbacks:{
            label: ctx => `${ctx.raw.label}: Wind ${ctx.raw.x} km/h, Humidity ${ctx.raw.y}%`,
          },
        },
      },
      scales:{
        x:{ title:{display:true,text:'Avg Wind Speed (km/h)'}, grid:{color:'rgba(255,255,255,0.04)'} },
        y:{ title:{display:true,text:'Avg Humidity (%)'}, grid:{color:'rgba(255,255,255,0.04)'} },
      },
    },
  });
}

// ─── SQL Explorer ─────────────────────────────────────────────────────────────
function renderQueryList() {
  const list = document.getElementById('query-list');
  list.innerHTML = SQL_QUERIES.map(q => `
    <div class="query-item" data-qid="${q.id}">
      <span class="query-badge badge-${q.badge}">${q.badge.toUpperCase()}</span>
      <span>${q.name}</span>
    </div>`).join('');
  list.querySelectorAll('.query-item').forEach(el => {
    el.addEventListener('click', () => {
      list.querySelectorAll('.query-item').forEach(x=>x.classList.remove('active'));
      el.classList.add('active');
      const q = SQL_QUERIES.find(x => x.id === el.dataset.qid);
      if (q) renderQueryDetail(q);
    });
  });
}

function highlightSQL(sql) {
  const keywords = ['SELECT','FROM','WHERE','GROUP BY','ORDER BY','HAVING','INNER JOIN','LEFT JOIN','JOIN','ON','AS','DISTINCT',
    'ROUND','AVG','MIN','MAX','COUNT','SUM','OVER','PARTITION BY','RANK','UNION ALL','LIMIT','AND','OR','NOT','IN','BETWEEN',
    'INSERT','UPDATE','DELETE','BEGIN','COMMIT','VALUES'];
  let h = sql
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  keywords.forEach(kw => {
    const re = new RegExp(`\\b(${kw})\\b`,'g');
    h = h.replace(re, `<span style="color:#a5b4fc;font-weight:600">$1</span>`);
  });
  // strings
  h = h.replace(/'([^']*)'/g, `<span style="color:#fde68a">'$1'</span>`);
  // comments
  h = h.replace(/(--[^\n]*)/g, `<span style="color:#475569;font-style:italic">$1</span>`);
  // functions/numbers
  h = h.replace(/\b(\d+(?:\.\d+)?)\b/g, `<span style="color:#6ee7b7">$1</span>`);
  return h;
}

function renderQueryDetail(q) {
  const detail = document.getElementById('query-detail');
  state.selectedQuery = q;

  detail.innerHTML = `
    <div class="query-detail-inner">
      <div class="query-name">${q.name}</div>
      <div class="query-description">${q.description}</div>
      <pre class="sql-block"><code>${highlightSQL(q.sql)}</code></pre>
      <button class="run-query-btn" id="run-query-btn">
        <span class="btn-icon">▶</span> Run Query on Live DB
      </button>
      <div class="results-count" id="query-result-count"></div>
      <div id="query-results-wrap" style="overflow-x:auto;border-radius:8px;border:1px solid rgba(255,255,255,0.06);">
        <p style="padding:20px 16px;color:var(--text-muted);font-size:13px">
          ⚡ Click <strong>Run Query on Live DB</strong> to execute this SQL against the live SQLite database.
        </p>
      </div>
    </div>`;

  document.getElementById('run-query-btn').addEventListener('click', async () => {
    const btn      = document.getElementById('run-query-btn');
    const countEl  = document.getElementById('query-result-count');
    const wrapEl   = document.getElementById('query-results-wrap');

    btn.innerHTML = `<span class="spinner"></span> Executing on DB…`;
    btn.disabled  = true;
    countEl.textContent = '';
    wrapEl.innerHTML = `<p style="padding:20px 16px;color:var(--text-muted);font-size:13px">⏳ Running query on SQLite database…</p>`;

    const res = await apiFetch('/api/sql/run', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ query_id: q.id }),
    });

    btn.innerHTML = `<span class="btn-icon">▶</span> Run Query on Live DB`;
    btn.disabled  = false;

    if (!res || res.status !== 'success') {
      wrapEl.innerHTML = `<p style="padding:20px 16px;color:#fda4af;font-size:13px">
        ✗ ${res?.message || 'Query execution failed'}</p>`;
      showToast(res?.message || 'Query failed', 'error');
      return;
    }

    // Render with live columns & rows from the database
    wrapEl.innerHTML = buildResultTable(res.columns, res.rows);
    countEl.innerHTML =
      `<span style="color:var(--text-secondary)">${res.row_count.toLocaleString()} row${res.row_count !== 1 ? 's' : ''} returned</span>` +
      `<span style="color:var(--text-muted);margin-left:12px;font-size:11px">⏱ ${res.exec_ms} ms — executed against live SQLite</span>`;

    showToast(`✓ Query returned ${res.row_count} row${res.row_count !== 1 ? 's' : ''} in ${res.exec_ms} ms`);
  });

  // Auto-run immediately on selection
  document.getElementById('run-query-btn').click();
}

function buildResultTable(columns, rows) {
  if (!rows || !rows.length) return `<p style="padding:16px;color:var(--text-muted)">No rows returned.</p>`;
  const head = columns.map(c => `<th>${c}</th>`).join('');
  const body = rows.map(row =>
    `<tr>${columns.map(c => {
      const v = row[c];
      return `<td>${v === null || v === undefined ? '<span style="color:var(--text-muted)">NULL</span>' : v}</td>`;
    }).join('')}</tr>`
  ).join('');
  return `<table class="query-results-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}


// ─── City Analytics ───────────────────────────────────────────────────────────
function renderCityTable() {
  const search = state.citySearch.toLowerCase();
  let rows = state.calcRows.filter(r =>
    !search || r.city_name.toLowerCase().includes(search) || (r.country||'').toLowerCase().includes(search)
  );
  rows = rows.sort((a,b) => {
    const av = a[state.sortCol] ?? 0, bv = b[state.sortCol] ?? 0;
    return state.sortAsc ? av - bv : bv - av;
  });

  const tbody = document.getElementById('city-tbody');
  tbody.innerHTML = rows.map(r => `
    <tr data-city="${r.city_name}">
      <td><strong>${r.city_name}</strong></td>
      <td>${r.country}</td>
      <td>${tempChip(r.avg_temp_c)}</td>
      <td style="font-family:'JetBrains Mono',monospace;font-size:12px">${fmt(r.min_temp_c,'°C')} / ${fmt(r.max_temp_c,'°C')}</td>
      <td>${fmt(r.avg_humidity_pct,'%')}</td>
      <td>${fmt(r.avg_wind_speed_kmh,' km/h')}</td>
      <td>${fmt(r.avg_pressure_hpa,' hPa')}</td>
      <td>${fmt(r.total_precipitation_mm,' mm')}</td>
      <td style="font-family:'JetBrains Mono',monospace">${(r.count_records||0).toLocaleString()}</td>
    </tr>`).join('');

  // Row click → city detail
  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', () => {
      const r = state.calcRows.find(x => x.city_name === tr.dataset.city);
      if (r) showCityDetail(r);
    });
  });
}

function showCityDetail(r) {
  const panel = document.getElementById('city-detail-panel');
  panel.style.display = 'block';
  document.getElementById('city-detail-name').textContent = `${r.city_name}, ${r.country}`;

  // Scroll to panel
  panel.scrollIntoView({ behavior:'smooth', block:'nearest' });

  // Temp profile
  destroyChart('cityTemp');
  const ctxT = document.getElementById('chart-city-temp').getContext('2d');
  state.charts.cityTemp = new Chart(ctxT, {
    type:'bar',
    data:{
      labels:['Min Temp','Avg Temp','Apparent Temp','Max Temp'],
      datasets:[{
        data:[r.min_temp_c, r.avg_temp_c, r.avg_apparent_temp_c, r.max_temp_c],
        backgroundColor:['rgba(6,182,212,0.7)','rgba(99,102,241,0.8)','rgba(16,185,129,0.7)','rgba(249,115,22,0.8)'],
        borderRadius:6, borderWidth:0,
      }],
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{
        y:{ grid:{color:'rgba(255,255,255,0.05)'}, title:{display:true,text:'°C'} },
        x:{ grid:{display:false} },
      },
    },
  });

  // Metrics radar-like bar
  destroyChart('cityMetrics');
  const ctxM = document.getElementById('chart-city-metrics').getContext('2d');
  state.charts.cityMetrics = new Chart(ctxM, {
    type:'radar',
    data:{
      labels:['Humidity','Wind','Pressure (÷10)','Cloud Cover','Precip (x2)'],
      datasets:[{
        label: r.city_name,
        data:[
          r.avg_humidity_pct,
          r.avg_wind_speed_kmh,
          r.avg_pressure_hpa / 10,
          r.avg_cloud_cover_pct,
          r.total_precipitation_mm * 2,
        ],
        backgroundColor:'rgba(99,102,241,0.2)',
        borderColor:'rgba(99,102,241,0.8)',
        pointBackgroundColor:'rgba(99,102,241,1)',
        borderWidth:2,
      }],
    },
    options:{
      responsive:true, maintainAspectRatio:false,
      plugins:{legend:{display:false}},
      scales:{r:{grid:{color:'rgba(255,255,255,0.06)'}, ticks:{display:false}}},
    },
  });
}

document.getElementById('city-detail-close').addEventListener('click', () => {
  document.getElementById('city-detail-panel').style.display = 'none';
});

// Search & Sort
document.getElementById('city-search').addEventListener('input', e => {
  state.citySearch = e.target.value;
  renderCityTable();
});
document.getElementById('city-sort').addEventListener('change', e => {
  state.sortCol = e.target.value;
  renderCityTable();
});
let cityDirAsc = false;
document.getElementById('sort-dir-btn').addEventListener('click', () => {
  cityDirAsc = !cityDirAsc;
  state.sortAsc = cityDirAsc;
  document.getElementById('sort-dir-btn').textContent = cityDirAsc ? '↑' : '↓';
  renderCityTable();
});

// ─── Airport Grid ─────────────────────────────────────────────────────────────
function renderAirportGrid() {
  const search   = state.airportSearch.toLowerCase();
  const srcRows  = state.airportRows.length ? state.airportRows : state.calcRows;
  let rows = srcRows.filter(r => {
    const name = (r.airport_name || r.city_name || '').toLowerCase();
    const ctry = (r.country || '').toLowerCase();
    return !search || name.includes(search) || ctry.includes(search);
  });
  rows = rows.sort((a,b) => {
    const av = a[state.airportSortCol] ?? 0, bv = b[state.airportSortCol] ?? 0;
    return state.airportSortAsc ? av - bv : bv - av;
  });

  // Pair with airport metadata if available
  const grid = document.getElementById('airport-grid');
  grid.innerHTML = rows.map((r, i) => {
    const meta = state.airportMeta[i] || {};
    const name = r.airport_name || meta.airport_name || r.city_name || '—';
    const code = r.station_code || meta.station_code || '—';
    const ctry = r.country || '—';
    const temp = r.avg_temp_c ?? 0;
    const wind = r.avg_wind_speed_kmh ?? 0;
    const hum  = r.avg_humidity_pct  ?? 0;
    const pres = r.avg_pressure_hpa  ?? 0;
    const prec = r.total_precipitation_mm ?? 0;

    return `
    <div class="airport-card">
      <div class="airport-header">
        <div>
          <div class="airport-name">✈ ${name}</div>
          <div class="airport-country">${ctry}</div>
        </div>
        <div class="airport-code">${code}</div>
      </div>
      <div class="airport-metrics">
        <div class="airport-metric-item">
          <div class="airport-metric-label">Avg Temp</div>
          <div class="airport-metric-value">${fmt(temp,'°C')}</div>
        </div>
        <div class="airport-metric-item">
          <div class="airport-metric-label">Wind Speed</div>
          <div class="airport-metric-value">${fmt(wind)} <small>km/h</small></div>
        </div>
        <div class="airport-metric-item">
          <div class="airport-metric-label">Humidity</div>
          <div class="airport-metric-value">${fmt(hum,'%')}</div>
        </div>
        <div class="airport-metric-item">
          <div class="airport-metric-label">Pressure</div>
          <div class="airport-metric-value">${fmt(pres)} <small>hPa</small></div>
        </div>
        <div class="airport-metric-item">
          <div class="airport-metric-label">Precipitation</div>
          <div class="airport-metric-value">${fmt(prec)} <small>mm</small></div>
        </div>
        <div class="airport-metric-item">
          <div class="airport-metric-label">Records</div>
          <div class="airport-metric-value">${(r.count_records||0).toLocaleString()}</div>
        </div>
      </div>
    </div>`;
  }).join('');
}

document.getElementById('airport-search').addEventListener('input', e => {
  state.airportSearch = e.target.value;
  renderAirportGrid();
});
document.getElementById('airport-sort').addEventListener('change', e => {
  state.airportSortCol = e.target.value;
  renderAirportGrid();
});
let airportDirAsc = false;
document.getElementById('airport-sort-dir').addEventListener('click', () => {
  airportDirAsc = !airportDirAsc;
  state.airportSortAsc = airportDirAsc;
  document.getElementById('airport-sort-dir').textContent = airportDirAsc ? '↑' : '↓';
  renderAirportGrid();
});

// ─── Insert Section ───────────────────────────────────────────────────────────
function populateInsertDropdowns() {
  const citySel    = document.getElementById('ins-city');
  const airportSel = document.getElementById('ins-airport');

  state.cities.forEach(c => {
    const o = document.createElement('option'); o.value = c; o.textContent = c;
    citySel.appendChild(o);
  });
  state.airports.forEach(a => {
    const o = document.createElement('option'); o.value = a; o.textContent = a;
    airportSel.appendChild(o);
  });

  // Live SQL preview
  const fields = ['ins-city','ins-airport','ins-temp','ins-humidity','ins-wind','ins-wind-dir','ins-pressure','ins-precip','ins-cloud','ins-wx'];
  fields.forEach(id => document.getElementById(id)?.addEventListener('input', updateInsertPreview));
  document.getElementById('ins-city').addEventListener('change', updateInsertPreview);
  document.getElementById('ins-airport').addEventListener('change', updateInsertPreview);
  updateInsertPreview();
}

function updateInsertPreview() {
  const city    = document.getElementById('ins-city').value;
  const airport = document.getElementById('ins-airport').value;
  const temp    = document.getElementById('ins-temp').value || '21.50';
  const hum     = document.getElementById('ins-humidity').value || '65.00';
  const wind    = document.getElementById('ins-wind').value || '15.00';
  const wdir    = document.getElementById('ins-wind-dir').value || '180';
  const pres    = document.getElementById('ins-pressure').value || '1013.25';
  const prec    = document.getElementById('ins-precip').value || '0.00';
  const cloud   = document.getElementById('ins-cloud').value || '20.00';
  const wx      = document.getElementById('ins-wx').value || 'CAVOK';
  const ts      = new Date().toISOString().replace('T',' ').slice(0,19);

  let sql = `-- Multi-Table Transactional INSERT\nBEGIN;\n`;
  if (city) {
    sql += `\n-- Insert city weather record\nINSERT INTO center_hourly_weather_data (\n  city_id, record_time, temperature_c, humidity_pct,\n  apparent_temp_c, precipitation_mm, weather_code,\n  cloud_cover_pct, sea_level_pressure_hpa,\n  wind_speed_kmh, wind_direction_deg\n) VALUES (\n  (SELECT city_id FROM cities\n   WHERE city_name = '${city}' LIMIT 1),\n  '${ts}', ${temp}, ${hum},\n  ${(+temp+0.5).toFixed(2)}, ${prec}, 1,\n  ${cloud}, ${pres},\n  ${wind}, ${wdir}\n);\n`;
  }
  if (airport) {
    const dew = (+temp - ((100 - +hum)/5)).toFixed(2);
    sql += `\n-- Insert airport weather record\nINSERT INTO airport_hourly_weather_data (\n  airport_id, record_time, temperature_c, dewpoint_c,\n  humidity_pct, wind_speed_kmh, wind_direction_deg,\n  sea_level_pressure_hpa, precipitation_mm, wx_string\n) VALUES (\n  (SELECT airport_id FROM airports\n   WHERE airport_name = '${airport}' LIMIT 1),\n  '${ts}', ${temp}, ${dew},\n  ${hum}, ${wind}, ${wdir},\n  ${pres}, ${prec}, '${wx}'\n);\n`;
  }
  sql += `\nCOMMIT;`;
  document.getElementById('insert-sql-preview').innerHTML = highlightSQL(sql);
}

document.getElementById('insert-submit-btn').addEventListener('click', async () => {
  const btn  = document.getElementById('insert-submit-btn');
  const msg  = document.getElementById('insert-result-msg');
  const city = document.getElementById('ins-city').value;
  if (!city) { showToast('Please select a city', 'error'); return; }

  btn.innerHTML = `<span class="spinner"></span> Executing…`;
  btn.disabled = true;

  const payload = {
    city_name:              city,
    airport_name:           document.getElementById('ins-airport').value,
    temperature_c:          +document.getElementById('ins-temp').value,
    humidity_pct:           +document.getElementById('ins-humidity').value,
    wind_speed_kmh:         +document.getElementById('ins-wind').value,
    wind_direction_deg:     +document.getElementById('ins-wind-dir').value,
    sea_level_pressure_hpa: +document.getElementById('ins-pressure').value,
    precipitation_mm:       +document.getElementById('ins-precip').value,
    cloud_cover_pct:        +document.getElementById('ins-cloud').value,
    wx_string:              document.getElementById('ins-wx').value,
  };

  const res = await apiFetch('/api/data/insert', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload),
  });

  btn.innerHTML = `<span class="btn-icon">⚡</span> Execute INSERT`;
  btn.disabled = false;

  if (res?.status === 'success') {
    if (res.kpis) state.kpis = res.kpis;
    if (res.data)  state.calcRows = res.data;
    renderKPIs();
    document.getElementById('record-counter').textContent =
      (state.kpis.total_records||0).toLocaleString() + ' records';
    if (res.sql_query) {
      document.getElementById('insert-sql-preview').innerHTML = highlightSQL(res.sql_query);
    }
    msg.style.display = 'block';
    msg.className = 'result-msg success';
    msg.textContent = `✓ ${res.message}`;
    showToast('Record inserted successfully!');
  } else {
    msg.style.display = 'block';
    msg.className = 'result-msg error';
    msg.textContent = `✗ ${res?.message || 'Insert failed'}`;
    showToast(res?.message || 'Insert failed', 'error');
  }
});

// ─── Filter Section ───────────────────────────────────────────────────────────
let filterCharts = { donut: null, temp: null };

function initFilterSection() {
  renderFilterKPIs(state.kpis);
  renderFilterCharts({ climate_distribution:[26.4,23.1,19.8,16.5,14.2], temp_spread:[11.2,18.5,24.3,13.8,22.1] });
  updateFilterSQL();
  ['filter-attr','filter-op','filter-threshold','filter-row-limit'].forEach(id =>
    document.getElementById(id)?.addEventListener('input', updateFilterSQL)
  );
  document.getElementById('filter-attr')?.addEventListener('change', updateFilterSQL);
  document.getElementById('filter-op')?.addEventListener('change', updateFilterSQL);
}

function updateFilterSQL() {
  const attr  = document.getElementById('filter-attr').value;
  const op    = document.getElementById('filter-op').value;
  const th    = document.getElementById('filter-threshold').value;
  const limit = document.getElementById('filter-row-limit').value;
  const opStr = op === 'gt' ? '>' : '<';

  const sql = `SELECT
  c.city_name,
  c.country,
  COUNT(*)                        AS record_count,
  ROUND(AVG(temperature_c), 2)    AS avg_temp_c,
  ROUND(AVG(humidity_pct), 2)     AS avg_humidity
FROM center_hourly_weather_data w
INNER JOIN cities c ON w.city_id = c.city_id
WHERE w.${attr} ${opStr} ${th}
GROUP BY c.city_name, c.country
ORDER BY avg_temp_c DESC
LIMIT ${limit};`;

  document.getElementById('filter-sql-block').innerHTML = highlightSQL(sql);
}

function renderFilterKPIs(kpis) {
  const panel = document.getElementById('filter-kpi-panel');
  const items = [
    { label:'Total Records', val: (kpis.total_records||0).toLocaleString() },
    { label:'Avg Temp °C',   val: fmt(kpis.avg_temperature_c,'°C') },
    { label:'Avg Humidity',  val: fmt(kpis.avg_humidity_pct,'%') },
    { label:'Avg Wind',      val: fmt(kpis.avg_wind_speed_kmh,' km/h') },
    { label:'Total Precip',  val: fmt(kpis.total_precipitation_mm,' mm') },
    { label:'Severe Alerts', val: kpis.severe_weather_alert_count ?? '—' },
  ];
  panel.innerHTML = items.map(i=>`
    <div class="filter-kpi-card">
      <div class="filter-kpi-val">${i.val}</div>
      <div class="filter-kpi-lbl">${i.label}</div>
    </div>`).join('');
}

function renderFilterCharts(chartData) {
  // Donut
  if (filterCharts.donut) { filterCharts.donut.destroy(); filterCharts.donut = null; }
  const ctxD = document.getElementById('chart-filter-donut')?.getContext('2d');
  if (ctxD) {
    filterCharts.donut = new Chart(ctxD, {
      type:'doughnut',
      data:{
        labels:['Zone A','Zone B','Zone C','Zone D','Zone E'],
        datasets:[{ data: chartData.climate_distribution, backgroundColor: PALETTE.slice(0,5), borderWidth:2, borderColor:'rgba(0,0,0,0.3)', hoverOffset:8 }],
      },
      options:{ responsive:true, maintainAspectRatio:false, cutout:'58%', plugins:{ legend:{position:'bottom'} } },
    });
  }

  // Temp bar
  if (filterCharts.temp) { filterCharts.temp.destroy(); filterCharts.temp = null; }
  const ctxT = document.getElementById('chart-filter-temp')?.getContext('2d');
  if (ctxT) {
    filterCharts.temp = new Chart(ctxT, {
      type:'bar',
      data:{
        labels:['Tropical','Arid','Temperate','Continental','Polar'],
        datasets:[{ label:'Avg Temp °C', data: chartData.temp_spread, backgroundColor: PALETTE.slice(2,7), borderRadius:5, borderWidth:0 }],
      },
      options:{
        responsive:true, maintainAspectRatio:false,
        plugins:{ legend:{display:false} },
        scales:{
          y:{ grid:{color:'rgba(255,255,255,0.04)'}, title:{display:true,text:'°C'} },
          x:{ grid:{display:false} },
        },
      },
    });
  }
}

document.getElementById('filter-run-btn')?.addEventListener('click', async () => {
  const btn   = document.getElementById('filter-run-btn');
  btn.innerHTML = `<span class="spinner"></span> Running…`;
  btn.disabled = true;

  const payload = {
    mode:      'filtered',
    attribute: document.getElementById('filter-attr').value,
    operator:  document.getElementById('filter-op').value,
    threshold: +document.getElementById('filter-threshold').value,
    row_limit: +document.getElementById('filter-row-limit').value,
  };

  const res = await apiFetch('/api/database/filter', {
    method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload),
  });

  btn.innerHTML = `<span>▶</span> Run Filter Query`;
  btn.disabled = false;

  if (res?.kpis) {
    renderFilterKPIs(res.kpis);
    if (res.chart_data) renderFilterCharts(res.chart_data);
    showToast(res.message || 'Filter applied');
  } else {
    showToast('Filter failed', 'error');
  }
});

document.getElementById('filter-reset-btn')?.addEventListener('click', async () => {
  const res = await apiFetch('/api/database/filter', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ mode:'full' }),
  });
  if (res?.kpis) {
    renderFilterKPIs(res.kpis);
    if (res.chart_data) renderFilterCharts(res.chart_data);
    showToast('Database reset to full scope');
  }
});

// ─── Boot ─────────────────────────────────────────────────────────────────────
boot();

// ═════════════════════════════════════════════════════════════════════════════
// DATABASE BROWSER — Load, Edit, Delete raw records
// ═════════════════════════════════════════════════════════════════════════════

const dbState = {
  table:       'city',
  offset:      0,
  limit:       100,
  totalCount:  0,
  filter:      '',
  rows:        [],
  currentRow:  null,
  pendingDelete: null,
};

// ── Column definitions ────────────────────────────────────────────────────────
const DB_COLS = {
  city: {
    display: ['record_id','city_name','country','station_code','record_time',
              'temperature_c','humidity_pct','apparent_temp_c','precipitation_mm',
              'cloud_cover_pct','sea_level_pressure_hpa','wind_speed_kmh','wind_direction_deg'],
    labels:  ['ID','City','Country','ICAO','Timestamp',
              'Temp °C','Humidity %','Apparent °C','Precip mm',
              'Cloud %','Pressure hPa','Wind km/h','Wind Dir°'],
    editable: ['temperature_c','humidity_pct','apparent_temp_c','precipitation_mm',
               'rain_mm','snowfall_cm','weather_code','cloud_cover_pct',
               'sea_level_pressure_hpa','wind_speed_kmh','wind_direction_deg'],
  },
  airport: {
    display: ['record_id','airport_name','country','station_code','record_time',
              'temperature_c','dewpoint_c','humidity_pct','wind_speed_kmh',
              'wind_direction_deg','sea_level_pressure_hpa','precipitation_mm','wx_string'],
    labels:  ['ID','Airport','Country','ICAO','Timestamp',
              'Temp °C','Dewpoint °C','Humidity %','Wind km/h',
              'Wind Dir°','Pressure hPa','Precip mm','WX'],
    editable: ['temperature_c','dewpoint_c','humidity_pct','wind_speed_kmh',
               'wind_direction_deg','sea_level_pressure_hpa','precipitation_mm','wx_string'],
  },
};

// ── Tab switching ─────────────────────────────────────────────────────────────
document.querySelectorAll('.db-tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.db-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    dbState.table  = btn.dataset.table;
    dbState.offset = 0;
    clearDbTable();
  });
});

function clearDbTable() {
  document.getElementById('db-empty-state').style.display = 'flex';
  document.getElementById('db-table').style.display = 'none';
  document.getElementById('db-info-text').textContent = '—';
  document.getElementById('db-page-num').textContent  = 'Page 1';
  document.getElementById('db-prev-btn').disabled = true;
  document.getElementById('db-next-btn').disabled = true;
}

// ── Load Data ─────────────────────────────────────────────────────────────────
document.getElementById('db-load-btn').addEventListener('click', () => {
  dbState.offset = 0;
  dbState.limit  = +document.getElementById('db-limit-select').value;
  dbState.filter = document.getElementById('db-search').value.trim();
  loadDbRecords();
});

document.getElementById('db-prev-btn').addEventListener('click', () => {
  if (dbState.offset > 0) {
    dbState.offset = Math.max(0, dbState.offset - dbState.limit);
    loadDbRecords();
  }
});
document.getElementById('db-next-btn').addEventListener('click', () => {
  if (dbState.offset + dbState.limit < dbState.totalCount) {
    dbState.offset += dbState.limit;
    loadDbRecords();
  }
});

// Reload when Enter pressed in search
document.getElementById('db-search').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    dbState.offset = 0;
    dbState.filter = e.target.value.trim();
    loadDbRecords();
  }
});

async function loadDbRecords() {
  const btn = document.getElementById('db-load-btn');
  btn.innerHTML = `<span class="spinner"></span>`;
  btn.disabled  = true;

  const params = new URLSearchParams({
    table:       dbState.table,
    limit:       dbState.limit,
    offset:      dbState.offset,
    city_filter: dbState.filter,
  });

  const res = await apiFetch(`/api/database/records?${params}`);
  btn.innerHTML = 'Load Data';
  btn.disabled  = false;

  if (!res || res.status !== 'success') {
    showToast(res?.message || 'Failed to load records', 'error');
    return;
  }

  dbState.rows       = res.data;
  dbState.totalCount = res.total_count;

  renderDbTable(res.data);

  // Update pagination
  const page   = Math.floor(dbState.offset / dbState.limit) + 1;
  const pages  = Math.ceil(dbState.totalCount / dbState.limit);
  const from   = dbState.offset + 1;
  const to     = Math.min(dbState.offset + dbState.limit, dbState.totalCount);
  document.getElementById('db-info-text').textContent =
    `Showing ${from}–${to} of ${dbState.totalCount.toLocaleString()} records`;
  document.getElementById('db-page-num').textContent  = `Page ${page} / ${pages}`;
  document.getElementById('db-prev-btn').disabled = dbState.offset === 0;
  document.getElementById('db-next-btn').disabled = to >= dbState.totalCount;

  showToast(`Loaded ${res.data.length} records from ${dbState.table === 'city' ? 'center_hourly_weather_data' : 'airport_hourly_weather_data'}`);
}

function renderDbTable(rows) {
  if (!rows.length) {
    document.getElementById('db-empty-state').style.display = 'flex';
    document.getElementById('db-table').style.display = 'none';
    return;
  }

  const cfg = DB_COLS[dbState.table];
  const cols = cfg.display, labels = cfg.labels;

  // Header
  document.getElementById('db-thead').innerHTML =
    `<tr>${labels.map(l => `<th>${l}</th>`).join('')}<th style="text-align:center">Actions</th></tr>`;

  // Body
  document.getElementById('db-tbody').innerHTML = rows.map((row, ri) => `
    <tr data-ri="${ri}">
      ${cols.map(c => {
        const v = row[c];
        if (c === 'record_time') return `<td style="font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--text-muted)">${v ?? '—'}</td>`;
        if (c === 'temperature_c' || c === 'dewpoint_c' || c === 'apparent_temp_c') return `<td>${tempChip(v)}</td>`;
        return `<td>${v ?? '—'}</td>`;
      }).join('')}
      <td>
        <div class="action-cell">
          <button class="row-action-btn row-edit-btn" data-ri="${ri}">✏ Edit</button>
          <button class="row-action-btn row-delete-btn" data-ri="${ri}">🗑 Delete</button>
        </div>
      </td>
    </tr>`).join('');

  document.getElementById('db-empty-state').style.display = 'none';
  document.getElementById('db-table').style.display = 'table';

  // Wire buttons
  document.getElementById('db-tbody').querySelectorAll('.row-edit-btn').forEach(btn => {
    btn.addEventListener('click', () => openEditModal(dbState.rows[+btn.dataset.ri]));
  });
  document.getElementById('db-tbody').querySelectorAll('.row-delete-btn').forEach(btn => {
    btn.addEventListener('click', () => openDeleteModal(dbState.rows[+btn.dataset.ri]));
  });
}

// ═══════════════════════════════════════════════════════════════════════
// EDIT MODAL
// ═══════════════════════════════════════════════════════════════════════
function openEditModal(row) {
  dbState.currentRow = row;
  const cfg     = DB_COLS[dbState.table];
  const rid     = row.record_id;
  const name    = row.city_name || row.airport_name || `#${rid}`;

  document.getElementById('modal-record-label').textContent =
    `Record #${rid} — ${name}`;
  document.getElementById('edit-modal').style.display = 'flex';

  // Build editable fields
  const fields = document.getElementById('modal-fields');
  fields.innerHTML = cfg.editable.map(col => `
    <div class="modal-field-group">
      <label class="modal-field-label">${col.replace(/_/g,' ')}</label>
      <input class="modal-field-input" id="mf-${col}"
             type="${typeof row[col] === 'string' ? 'text' : 'number'}"
             step="0.01"
             value="${row[col] ?? ''}" />
    </div>`).join('');

  // Live SQL preview
  cfg.editable.forEach(col => {
    document.getElementById(`mf-${col}`)?.addEventListener('input', updateEditSQL);
  });
  updateEditSQL();
}

function updateEditSQL() {
  if (!dbState.currentRow) return;
  const cfg  = DB_COLS[dbState.table];
  const rid  = dbState.currentRow.record_id;
  const sets = cfg.editable.map(col => {
    const el = document.getElementById(`mf-${col}`);
    const v  = el ? el.value : dbState.currentRow[col];
    return `  ${col} = ${isNaN(v) || v === '' ? `'${v}'` : v}`;
  }).join(',\n');
  const dbTable = dbState.table === 'city'
    ? 'center_hourly_weather_data' : 'airport_hourly_weather_data';

  document.getElementById('modal-sql-preview').innerHTML =
    highlightSQL(`UPDATE ${dbTable}\nSET\n${sets}\nWHERE record_id = ${rid};`);
}

document.getElementById('modal-close-btn').addEventListener('click',  closeEditModal);
document.getElementById('modal-cancel-btn').addEventListener('click', closeEditModal);
document.getElementById('edit-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('edit-modal')) closeEditModal();
});

function closeEditModal() {
  document.getElementById('edit-modal').style.display = 'none';
  dbState.currentRow = null;
}

document.getElementById('modal-save-btn').addEventListener('click', async () => {
  if (!dbState.currentRow) return;
  const btn = document.getElementById('modal-save-btn');
  btn.innerHTML = `<span class="spinner"></span> Saving…`;
  btn.disabled  = true;

  const cfg    = DB_COLS[dbState.table];
  const rid    = dbState.currentRow.record_id;
  const fields = {};
  cfg.editable.forEach(col => {
    const el = document.getElementById(`mf-${col}`);
    if (el) {
      fields[col] = isNaN(el.value) || el.value === '' ? el.value : +el.value;
    }
  });

  const res = await apiFetch('/api/data/update', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ record_id: rid, table: dbState.table, fields }),
  });

  btn.innerHTML = `<span class="btn-icon">💾</span> Save Changes`;
  btn.disabled  = false;

  if (res?.status === 'success') {
    showToast(`✓ ${res.message}`);
    closeEditModal();
    loadDbRecords(); // refresh table
  } else {
    showToast(res?.message || 'Update failed', 'error');
  }
});

// ═══════════════════════════════════════════════════════════════════════
// DELETE MODAL
// ═══════════════════════════════════════════════════════════════════════
function openDeleteModal(row) {
  dbState.pendingDelete = row;
  const rid    = row.record_id;
  const name   = row.city_name || row.airport_name || `#${rid}`;
  const dbTable = dbState.table === 'city'
    ? 'center_hourly_weather_data' : 'airport_hourly_weather_data';

  document.getElementById('del-modal-text').textContent =
    `Permanently delete Record #${rid} (${name})? This cannot be undone.`;
  document.getElementById('del-modal-sql').innerHTML =
    highlightSQL(`DELETE FROM ${dbTable}\nWHERE record_id = ${rid};`);
  document.getElementById('delete-modal').style.display = 'flex';
}

document.getElementById('del-modal-close').addEventListener('click',  closeDeleteModal);
document.getElementById('del-modal-cancel').addEventListener('click', closeDeleteModal);
document.getElementById('delete-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('delete-modal')) closeDeleteModal();
});

function closeDeleteModal() {
  document.getElementById('delete-modal').style.display = 'none';
  dbState.pendingDelete = null;
}

document.getElementById('del-modal-confirm').addEventListener('click', async () => {
  if (!dbState.pendingDelete) return;
  const btn = document.getElementById('del-modal-confirm');
  btn.innerHTML = `<span class="spinner"></span> Deleting…`;
  btn.disabled  = true;

  const row = dbState.pendingDelete;
  const res = await apiFetch('/api/data/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ record_id: row.record_id }),
  });

  btn.innerHTML = `🗑 Delete Record`;
  btn.disabled  = false;

  if (res?.status === 'success') {
    if (res.kpis) state.kpis = res.kpis;
    renderKPIs();
    document.getElementById('record-counter').textContent =
      (state.kpis.total_records || 0).toLocaleString() + ' records';
    showToast(`✓ Record #${row.record_id} deleted`);
    closeDeleteModal();
    loadDbRecords(); // refresh
  } else {
    showToast(res?.message || 'Delete failed', 'error');
  }
});

