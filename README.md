# Globant Data Engineering Coding Challenge

A REST API that migrates three legacy tables (`departments`, `jobs`, `hired_employees`)
into PostgreSQL, plus the two hiring metrics the stakeholders asked for.

![CI](https://github.com/carloxorjuela/globant-data-challenge/actions/workflows/ci.yml/badge.svg)

Both required sections are implemented, along with the three bonus items:
containers, automated tests and a cloud deployment.

## Running it

```bash
docker compose up -d --build
```

PostgreSQL 16 and the API come up together. Swagger lives at <http://localhost:8000/docs>.

To load the historical files:

```bash
for table in departments jobs hired_employees; do
  curl -X POST "http://localhost:8000/api/v1/${table}/upload-csv" \
       -F "file=@data/${table}.csv"
done
```

Order matters. Hires reference departments and jobs, so those two go first.

## Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/{table}/upload-csv` | Load a headerless CSV into any of the three tables |
| `POST` | `/api/v1/departments/batch` | Insert 1–1000 departments in one transaction |
| `POST` | `/api/v1/jobs/batch` | Insert 1–1000 jobs in one transaction |
| `POST` | `/api/v1/hired_employees/batch` | Insert 1–1000 hires in one transaction |
| `GET` | `/api/v1/metrics/hires-by-quarter?year=2021` | Requirement 1 |
| `GET` | `/api/v1/metrics/departments-above-mean?year=2021` | Requirement 2 |
| `GET` | `/api/v1/metrics/data-quality` | How complete the migrated data actually is |
| `GET` | `/health` | Liveness and database connectivity |

A batch insert looks like this:

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

Anything outside the 1–1000 range comes back as a `422` before the database is touched.

### Partial success

I did not want one bad record to cost the caller the other 999, so rows that fail
validation, point at a department or job that does not exist, or repeat an id inside
the same payload get reported individually while everything else commits:

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

## The two metrics

**Requirement 1** — [`sql/01_hires_by_quarter.sql`](sql/01_hires_by_quarter.sql).
Returns 938 rows for 2021, sorted alphabetically by department and job:

| department | job | Q1 | Q2 | Q3 | Q4 |
| --- | --- | --- | --- | --- | --- |
| Accounting | Account Representative IV | 1 | 0 | 0 | 0 |
| Accounting | Actuary | 0 | 1 | 0 | 0 |
| Accounting | Analyst Programmer | 0 | 0 | 1 | 0 |

**Requirement 2** — [`sql/02_departments_above_mean.sql`](sql/02_departments_above_mean.sql).
The 2021 mean works out to 139.17 hires per department, and seven clear it:

| id | department | hired |
| --- | --- | --- |
| 8 | Support | 221 |
| 5 | Engineering | 208 |
| 6 | Human Resources | 204 |
| 7 | Services | 204 |
| 4 | Business Development | 187 |
| 3 | Research and Development | 151 |
| 9 | Marketing | 143 |

Support and Services tie at 204, which is why the query breaks ties on department id.
Without that the row order would be up to the query planner and the endpoint would not
be reproducible.

I computed both results straight from the CSV files before writing any code, and the
endpoints return the same numbers.

## What the source data actually looks like

This is where most of the design work went.

`hired_employees.csv` has 1,999 rows and 70 of them are incomplete: 19 with no name,
14 with no hire date, 21 with no department, 16 with no job. None of the files ship a
header row, and the hires span two calendar years, not one. There are 1,685 hires in
2021 and 300 in 2022, so any metric that forgets to filter by year is quietly wrong.

I load the incomplete rows rather than dropping them. Throwing away 3.5% of a migration
because some fields are blank seemed worse than carrying them with known gaps, and
`GET /api/v1/metrics/data-quality` exists so nobody has to guess how much is missing.

That choice has consequences and they should be stated:

- The quarterly report inner-joins departments and jobs, so it covers 1,659 of the
  1,685 hires from 2021. The rest have an unknown department or job and there is
  nowhere to put them in that report.
- The mean in requirement 2 comes from the 1,670 hires that do carry a department.
  Counting the 15 unattributed ones would push it from 139.17 to 140.42 and return the
  same seven departments either way. I checked, rather than assuming.

## Design decisions

I picked PostgreSQL because the work is transactional row insertion with foreign keys
and repeated replays. A warehouse like BigQuery would be the wrong shape for this; it
belongs downstream, once this database is feeding analytics.

Every column on `hired_employees` is nullable except the primary key. The source data
proves completeness cannot be a load-time invariant, so quality gets measured and
reported instead of enforced by a schema that would reject 70 rows.

Ingestion upserts on the primary key, because re-running a file is a normal thing to do
during a migration and it should not blow up the second time.

Two smaller things that took longer to get right than expected:

- PostgreSQL refuses an `ON CONFLICT DO UPDATE` that touches the same row twice in one
  statement, so duplicate ids inside a payload have to be resolved before they reach the
  database. The last record wins and the superseded ones are reported.
- Foreign keys are checked in the application, not left to the database. A constraint
  violation would roll back the whole transaction and take the valid rows with it, which
  is exactly what partial success is supposed to prevent.

The SQL lives in `sql/*.sql` and is executed verbatim, so what a reviewer reads is what
actually runs. Timestamps are pinned to UTC before `EXTRACT` since the source is ISO-8601
with a `Z` suffix and quarter boundaries should not depend on a server's timezone.

The schema is created from ORM metadata at startup. For three tables that is honest and
reproducible; a longer-lived system would use Alembic. That is scope I cut on purpose,
not something I missed.

## Tests

```bash
docker compose up -d db
pip install -r requirements-dev.txt
TEST_DATABASE_URL=postgresql+psycopg://challenge:challenge@localhost:5432/challenge pytest -q
```

Fifteen integration tests, run against real PostgreSQL. The metrics use
`COUNT(*) FILTER` and the ingestion uses `ON CONFLICT`, neither of which SQLite has, and
testing against a dialect the service never uses would prove nothing.

They cover both batch boundaries (1 and 1000), both rejections (0 and 1001), replaying a
batch, orphaned foreign keys, duplicate ids in one payload, malformed CSV rows, and the
year filter that keeps 2022 hires out of a 2021 report. CI runs lint and the suite on
every push.

## Deployment

The image is stateless, listens on `$PORT` and runs as a non-root user, so it goes onto
any container runtime. On Google Cloud:

```bash
gcloud run deploy globant-data-challenge \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-secrets "DATABASE_URL=globant-database-url:latest"
```

Cloud Run scales to zero between requests, which fits a reporting API with bursty
traffic. The database password goes through Secret Manager rather than sitting in an
environment variable.

For a real migration I would put a landing zone in front of this: files arriving in
Cloud Storage, an event triggering ingestion, and the rejected rows persisted somewhere
stakeholders can read them instead of only coming back in the HTTP response.

## Scale

2,000 rows fits in a single request, so none of this is stressed by the supplied data.
The parts that would matter later are already in place: inserts are chunked at 1,000 per
statement, `hire_datetime`, `department_id` and `job_id` are indexed since that is what
the reports filter and group on, and both metrics are computed in the database rather
than pulled into Python. Somewhere past ten million hires I would move to a partitioned
table or a summary refreshed on ingestion.

## Layout

```
app/
  main.py             FastAPI application and lifespan
  config.py           Environment-driven settings
  database.py         Engine, session factory, declarative base
  models.py           ORM models for the three tables
  schemas.py          Request and response contracts
  routers/            HTTP layer: ingestion, metrics
  services/           Ingestion pipeline and metric execution
sql/                  The SQL, executed verbatim
tests/                Integration suite
data/                 The three source CSV files
```
