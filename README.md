# Globant Data Engineering Coding Challenge

REST API that migrates three legacy tables (`departments`, `jobs`, `hired_employees`)
into PostgreSQL and exposes the hiring metrics requested by stakeholders.

| Challenge section | Status |
| --- | --- |
| Section 1 — REST API, CSV ingestion, batch transactions of 1–1000 rows | Complete |
| Section 2 — one endpoint per stakeholder metric | Complete |
| Bonus — containers | Complete |
| Bonus — automated tests | Complete (15 integration tests, CI on every push) |
| Bonus — public cloud | See [Deployment](#deployment) |

---

## Quickstart

```bash
docker compose up -d --build
```

That brings up PostgreSQL 16 and the API. Interactive documentation is served at
<http://localhost:8000/docs>.

Load the three historical files:

```bash
for table in departments jobs hired_employees; do
  curl -X POST "http://localhost:8000/api/v1/${table}/upload-csv" \
       -F "file=@data/${table}.csv"
done
```

Departments and jobs must be loaded before hires, since hires reference them.

---

## Architecture

```mermaid
flowchart LR
    CSV[Historical CSV files] -->|multipart upload| API
    APP[Client applications] -->|JSON batch, 1-1000 rows| API

    subgraph API[FastAPI service]
        V[Pydantic validation]
        P[Ingestion pipeline]
        M[Metrics endpoints]
    end

    V --> P
    P -->|upsert on primary key| DB[(PostgreSQL)]
    M -->|parameterised SQL| DB
    P -.->|per-row rejection report| APP
```

A single ingestion pipeline serves both entry points: the CSV upload parses
files into positional rows, the JSON endpoints receive them already structured,
and from there validation, foreign-key checks, de-duplication and persistence
are identical. The metrics endpoints execute the statements stored in `sql/`
verbatim.

---

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/{table}/upload-csv` | Load a headerless CSV into `departments`, `jobs` or `hired_employees` |
| `POST` | `/api/v1/departments/batch` | Insert 1–1000 departments in one transaction |
| `POST` | `/api/v1/jobs/batch` | Insert 1–1000 jobs in one transaction |
| `POST` | `/api/v1/hired_employees/batch` | Insert 1–1000 hires in one transaction |
| `GET` | `/api/v1/metrics/hires-by-quarter?year=2021` | Requirement 1 |
| `GET` | `/api/v1/metrics/departments-above-mean?year=2021` | Requirement 2 |
| `GET` | `/api/v1/metrics/data-quality` | Completeness of the migrated hires |
| `GET` | `/health` | Liveness and database connectivity |

### Batch insert

```bash
curl -X POST http://localhost:8000/api/v1/hired_employees/batch \
     -H "Content-Type: application/json" \
     -d '{"rows": [
           {"id": 4535, "name": "Marcelo Gonzalez",
            "datetime": "2021-07-27T16:02:08Z", "department_id": 1, "job_id": 2}
         ]}'
```

```json
{ "received": 1, "inserted": 1, "rejected": 0, "errors": [] }
```

A payload of 0 or more than 1000 rows is rejected with `422` before any
database work happens.

### Partial success

One bad record never costs the caller the other 999. Rows that fail validation,
reference a missing department or job, or repeat an id inside the payload are
reported individually while the rest are committed:

```json
{
  "received": 2,
  "inserted": 1,
  "rejected": 1,
  "errors": [
    { "index": 1, "reason": "unknown department_id 999", "row": { "id": 2 } }
  ]
}
```

---

## The two required metrics

### 1. Hires per department and job, by quarter

`GET /api/v1/metrics/hires-by-quarter?year=2021` — [`sql/01_hires_by_quarter.sql`](sql/01_hires_by_quarter.sql)

Returns 938 rows for 2021, ordered alphabetically by department and job:

| department | job | Q1 | Q2 | Q3 | Q4 |
| --- | --- | --- | --- | --- | --- |
| Accounting | Account Representative IV | 1 | 0 | 0 | 0 |
| Accounting | Actuary | 0 | 1 | 0 | 0 |
| Accounting | Analyst Programmer | 0 | 0 | 1 | 0 |

### 2. Departments hiring above the mean

`GET /api/v1/metrics/departments-above-mean?year=2021` — [`sql/02_departments_above_mean.sql`](sql/02_departments_above_mean.sql)

The 2021 mean is 139.17 hires per department; seven departments exceed it:

| id | department | hired |
| --- | --- | --- |
| 8 | Support | 221 |
| 5 | Engineering | 208 |
| 6 | Human Resources | 204 |
| 7 | Services | 204 |
| 4 | Business Development | 187 |
| 3 | Research and Development | 151 |
| 9 | Marketing | 143 |

---

## Data quality findings

The supplied `hired_employees.csv` holds 1,999 rows, 70 of which are incomplete:

| Issue | Rows |
| --- | --- |
| Missing name | 19 |
| Missing hire date | 14 |
| Missing department | 21 |
| Missing job | 16 |
| **Distinct incomplete rows** | **70** |

These rows are migrated, not discarded — silently dropping 3.5% of a migration
is worse than carrying it with known gaps. `GET /api/v1/metrics/data-quality`
reports them, and the consequences are explicit:

- The quarterly report inner-joins departments and jobs, so it covers 1,659 of
  the 1,685 hires recorded in 2021. The difference is hires whose department or
  job is unknown and which therefore cannot be placed in the report.
- The mean in requirement 2 is computed over the 1,670 hires that carry a
  department. Including the 15 unattributed 2021 hires would move the mean from
  139.17 to 140.42 and return the same seven departments.

The files also span two calendar years — 1,685 hires in 2021 and 300 in 2022 —
so every metric filters on an explicit `year` parameter rather than assuming
the dataset is already scoped.

---

## Design decisions

**PostgreSQL over a warehouse.** The workload is transactional row insertion
with foreign keys and idempotent replays. BigQuery or Snowflake would be the
wrong tool here; they belong downstream, once this database feeds analytics.

**Every hire column is nullable except the primary key.** The source data
proves that completeness cannot be a load-time invariant. Quality is measured
and reported instead of being enforced by a schema that would reject 70 rows.

**Upsert on the primary key.** Re-running a file is a normal operation during a
migration, so ingestion is idempotent: `ON CONFLICT (id) DO UPDATE`.

**Duplicates inside a payload are resolved before the database sees them.**
PostgreSQL refuses an `ON CONFLICT DO UPDATE` that touches the same row twice
in one statement, so the last record per id wins and the superseded ones are
reported rather than dropped silently.

**Foreign keys are checked in the application, not left to the database.**
A database-level violation would abort the whole transaction and take the valid
rows with it. Checking first is what makes partial success possible.

**SQL lives in files, not in string literals.** `sql/*.sql` is executed
verbatim, so the SQL a reviewer reads is the SQL that runs.

**Timestamps are pinned to UTC before `EXTRACT`.** The source data is ISO-8601
with a `Z` suffix; quarter boundaries must not depend on a server's timezone.

**The schema is created from ORM metadata at startup.** For a three-table
challenge this is honest and reproducible. A longer-lived system would move to
Alembic migrations; that is deliberate scope, not an oversight.

---

## Testing

```bash
docker compose up -d db
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://challenge:challenge@localhost:5432/challenge pytest -q
```

Fifteen integration tests run against a real PostgreSQL instance, because the
metrics depend on `COUNT(*) FILTER` and `ON CONFLICT`, which SQLite does not
support. Faking that dialect would test a database the service never uses.

Coverage includes both batch boundaries (1 and 1000 rows), both rejections
(0 and 1001), idempotent replay, orphaned foreign keys, duplicate ids inside a
payload, malformed CSV rows, and the year filter that keeps 2022 hires out of a
2021 report.

CI runs lint and the full suite on every push and pull request.

---

## Deployment

The image is stateless, listens on `$PORT` and runs as a non-root user, so it
deploys to any container runtime. On Google Cloud:

```bash
gcloud run deploy globant-data-challenge \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "DATABASE_URL=${DATABASE_URL}"
```

Cloud Run scales to zero between requests, which suits a reporting API whose
traffic is bursty. A managed PostgreSQL instance holds the data.

For a production migration the same service would sit behind a landing zone:
raw files arriving in Cloud Storage, an event triggering ingestion, and the
rejected-row report persisted for stakeholders rather than only returned in the
response.

---

## Scaling considerations

The supplied dataset is 2,000 rows and fits comfortably in one request. The
design still holds as volume grows:

- Ingestion chunks inserts at 1,000 rows per statement, so a large file becomes
  a sequence of bounded statements instead of one oversized transaction.
- `hire_datetime`, `department_id` and `job_id` are indexed, which is what the
  reporting queries filter and group on.
- Both metrics are computed in the database. Nothing is pulled into Python to
  be aggregated.
- Past roughly ten million hires the reporting queries would be better served by
  a partitioned table or a materialised summary refreshed on ingestion.

---

## Repository layout

```
app/
  main.py             FastAPI application and lifespan
  config.py           Environment-driven settings
  database.py         Engine, session factory, declarative base
  models.py           ORM models for the three tables
  schemas.py          Request and response contracts
  routers/            HTTP layer: ingestion, metrics
  services/           Ingestion pipeline and metric execution
sql/                  The reviewable SQL, executed verbatim
tests/                Integration suite
data/                 The three source CSV files
```
