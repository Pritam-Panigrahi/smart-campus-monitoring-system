# Smart Campus Monitoring System

This repository has separate React and FastAPI applications. The backend uses
FastAPI, SQLAlchemy, SQLite, and Alembic. Its initial schema contains water
tanks, waste bins, AQI stations, and their corresponding reading tables.

## Prerequisites

- Python 3.12
- Node.js and npm

## Docker and Docker Compose

Prerequisites: Docker Engine or Docker Desktop with the Docker Compose v2
plugin. Docker Compose builds the React production bundle, serves it through
Nginx, and proxies `/api` and `/ws` to FastAPI, so browser API and WebSocket
URLs never use a hard-coded localhost backend address.

From the repository root:

```bash
docker compose up --build
```

Open the application at <http://localhost:8080>. The API is available through
the same origin at <http://localhost:8080/api/health>; the backend is kept on
the internal Compose network. Stop the stack with `docker compose down`, or
use `docker compose down -v` only when you intentionally want to delete the
Docker-managed database volume.

Useful commands:

```bash
docker compose logs -f
docker compose logs -f backend
docker compose ps
```

### Persistent SQLite data

Compose mounts the named `smart_campus_data` volume at `/data` and configures
`DATABASE_URL=sqlite:////data/smart_campus.db`. The image does not contain a
database file, and startup runs only `alembic upgrade head`; migrations update
an existing database in place and do not seed, reset, recreate, or overwrite
devices or readings. Rebuilds and ordinary `docker compose down` / `up` cycles
preserve the volume. Do not use `docker compose down -v` unless you explicitly
intend to remove that persisted data.

For configuration, copy `.env.example` to `.env` and adjust `CORS_ORIGINS`,
`DATABASE_URL`, `PORT`, or `SIMULATION_DEFAULT_MODE`. For Compose, use an
absolute SQLite URL pointing inside the mounted `/data` directory. Existing
host databases are intentionally excluded from the Docker build context; back
them up and copy them into the persistent volume separately before first
startup if you need to migrate local data.

### Render

Deploy the backend and frontend as separate Docker web services, both using
the repository root as build context and their respective Dockerfiles. Attach
a Render persistent disk at `/data` to the backend and set
`DATABASE_URL=sqlite:////data/smart_campus.db`. Set the backend's `PORT` from
Render, and set `CORS_ORIGINS` to the public frontend URL. For the frontend,
set `BACKEND_URL` to the public backend URL (for example,
`https://smart-campus-api.onrender.com`). Nginx proxies API and WebSocket
traffic through that value. Render's persistent disk retains the SQLite file
across deploys; never attach a fresh disk if you need to retain existing data.

## Run the backend

From the project root, activate the existing virtual environment and start
FastAPI:

```bash
source .venv/bin/activate
PYTHONPATH=backend uvicorn app.main:app --reload
```

Run that command from the project root (`GATE`). If you are already inside the
`backend` directory, use `uvicorn app.main:app --reload` instead; do not add
`--app-dir backend` there, because it would resolve to a non-existent
`backend/backend` directory.

The API runs at <http://127.0.0.1:8000>. Confirm it with:

```bash
curl http://127.0.0.1:8000/api/health
```

Live monitoring clients can connect to `ws://127.0.0.1:8000/ws/monitoring`.
After each successfully stored reading, clients receive a module-specific event
(`WATER_TANK_READING`, `WASTE_BIN_READING`, or `AQI_READING`) followed by a
`DASHBOARD_UPDATE` event containing the current dashboard summary. Reading
events include the device and module IDs, reading ID, module value, status,
source, and UTC timestamp.

API configuration is read from the root `.env` file. Copy `.env.example` when
setting up another local environment. The SQLite URL is resolved to
`smart_campus.db` at the project root.

## Run the frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite serves the application at <http://localhost:5173> by default. The backend
CORS configuration permits this origin and `http://127.0.0.1:5173`.

## Database and migrations

SQLAlchemy configuration lives in `backend/app/core/database.py`. It defines
the engine, session factory, and declarative base. Alembic is configured in
`alembic.ini` and `backend/alembic/`. Create or update the database with:

```bash
source .venv/bin/activate
alembic upgrade head
python backend/seed_devices.py
```

The seed command is idempotent: it adds only missing devices and never changes
existing names, locations, coordinates, or device status. It does not insert
monitoring readings.

## Run backend tests

The backend integration tests use a temporary SQLite database:

```bash
source .venv/bin/activate
PYTHONPATH=backend python -m unittest discover -s backend/tests -v
```
