# AtmosDB — Meteorological & Aviation Telemetry DBMS

AtmosDB is a full-stack Database Management System (DBMS) designed for real-time meteorological observations, aviation flight safety telemetry, and cross-station climate analytics. It features an integrated SQLite database loaded with **78,138 high-fidelity records**, support for PostgreSQL ingestion, a Flask REST API backend, and a modern dark glassmorphic frontend interface.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
Ensure you have Python 3.9+ installed on your system.

### 2. Install Dependencies
Open a terminal in the project root and run:
```bash
pip install -r backend/requirements.txt
```

### 3. Launch the Application
Start the Flask server:
```bash
python backend/app.py
```

### 4. Access the Dashboard
Open your browser and navigate to:
```
http://127.0.0.1:5000
```
The server serves both the REST API and the complete frontend UI.

---

## 📂 Project Structure

```
DBMS Dashboard/
├── backend/
│   ├── app.py                   # Flask REST API server (7 endpoints, CORS, SQLite + PG)
│   ├── etl_pipeline.py          # Data ingestion & ETL pipeline (78,138 records)
│   ├── precomputed_stats.json   # Fast-cache analytics metrics
│   └── requirements.txt         # Python dependencies
├── database/
│   ├── schema.sql               # Relational DDL schema & constraints
│   ├── seed.sql                 # Sample test fixtures & seed queries
│   └── queries.sql              # Analytical & performance queries
├── Frontend/
│   ├── index.html               # Main dashboard web interface
│   ├── css/
│   │   └── style.css            # Custom CSS design system (Glassmorphism, animations)
│   └── js/
│       └── app.js               # Frontend application logic, Chart.js, SQL runner
├── weather_aviation.db          # Pre-packaged SQLite DB (78,138 records ready to run)
├── FRONTEND_INTEGRATION_GUIDE.md# API documentation & schema guide
├── README.md                    # Project documentation & run guide
└── .env.example                 # Environment variable templates
```

---

## 🌟 Key Features

1. **Executive Telemetry Overview**:
   - Total telemetry count, station networks, active flight corridor alerts, and global temperature/visibility metrics.
   - Quick health badges showing database connection latency and engine type.

2. **Aviation Flight Corridor Risk Matrix**:
   - Live corridor monitoring (Trans-Atlantic, Pacific Rim, Continental Express, Arctic Passage, Polar Cargo).
   - Dynamic safety categorization: `CLEAR`, `MODERATE_RISK`, `SEVERE_WARNING`.
   - Real-time wind shear alerts, visibility cutoffs, and turbulence advisories.

3. **Interactive SQL Query Studio**:
   - Interactive SQL query runner with syntax suggestions.
   - 1-click preset templates (High Severity Alerts, Icing Risk, Regional Comparisons).
   - Live execution time benchmarking and CSV export.

4. **Multi-Database Support**:
   - Ready out-of-the-box with pre-populated SQLite database.
   - Optional connection to external PostgreSQL instances via environment variables.

---

## 🛠️ Configuration (Optional PostgreSQL)

To point AtmosDB to a live PostgreSQL server instead of the bundled SQLite file, set the `DATABASE_URL` environment variable:

```bash
# Windows PowerShell
$env:DATABASE_URL="postgresql://username:password@localhost:5432/airport"

# Linux / macOS
export DATABASE_URL="postgresql://username:password@localhost:5432/airport"
```

Then start the server as normal.
