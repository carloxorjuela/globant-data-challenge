# Globant Data Engineering Coding Challenge

A REST API that migrates three legacy tables (`departments`, `jobs`, `hired_employees`)
into PostgreSQL, plus the two hiring metrics the stakeholders asked for.

![CI](https://github.com/carloxorjuela/globant-data-challenge/actions/workflows/ci.yml/badge.svg)

Running on Cloud Run, loaded with the supplied data:
**<https://globant-data-challenge-zyesaqqlqq-uc.a.run.app/docs>**

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
       -H "X-API-Key: local-development-key" \
       -F "file=@data/${table}.csv"
done
```

Order matters. Hires reference departments and jobs, so those two go first.

## Authentication

Writing needs a key, reading does not.

The deployed instance is public, so anyone with the link can read every report. That
same link would also let anyone overwrite the data those reports describe, so the four
ingestion endpoints sit behind an `X-API-Key` header. The scheme is declared in OpenAPI,
so on `/docs` there is an **Authorize** button: paste the key and the write endpoints
work from the browser. The key for the deployed instance is not in this repository and
is shared separately.

Locally, compose sets a throwaway key (`local-development-key`) so the stack works out
of the box; export `API_KEY` before `docker compose up` to use your own. It fails closed
either way: with no key configured the write endpoints refuse rather than falling back
to open access.

## Endpoints

| Method | Endpoint | Purpose | Key |
| --- | --- | --- | --- |
| `POST` | `/api/v1/{table}/upload-csv` | Load a headerless CSV into any of the three tables | yes |
| `POST` | `/api/v1/departments/batch` | Insert 1–1000 departments in one transaction | yes |
| `POST` | `/api/v1/jobs/batch` | Insert 1–1000 jobs in one transaction | yes |
| `POST` | `/api/v1/hired_employees/batch` | Insert 1–1000 hires in one transaction | yes |
| `GET` | `/api/v1/metrics/hires-by-quarter?year=2021` | Requirement 1 | no |
| `GET` | `/api/v1/metrics/departments-above-mean?year=2021` | Requirement 2 | no |
| `GET` | `/api/v1/metrics/data-quality` | How complete the migrated data actually is | no |
| `GET` | `/health` | Liveness and database connectivity | no |

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

Rows that point at a department or job that does not exist, or that repeat an id inside
the same payload, are reported individually while everything else commits:

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

There is a line here worth stating precisely, because it is not "any bad row is always
isolated". The JSON batch endpoints check the payload against a typed schema before the
service sees it, so a structurally wrong row (a negative id, an unparseable timestamp)
fails the whole request with a `422` and nothing is written. Only the errors that need
the database to answer them, an unknown foreign key or a duplicate id inside the
payload, are resolved per row. The CSV endpoint is more forgiving because a file has no
schema to fail against as a unit: there, a malformed line is reported next to the rows
that loaded fine.

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
- The mean in requirement 2 averages over every department on record, including any
  that hired nobody that year, which is the literal reading of "for all the departments".
  Here all twelve hired, so it comes out at 139.17 across the 1,670 attributed hires.
  Counting the 15 unattributed 2021 hires too would push it to 140.42 and still return
  the same seven. Both readings were checked rather than assumed.

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
pytest -q
```

Twenty-eight integration tests, run against real PostgreSQL. SQLite would be quicker to wire
up and does support both `COUNT(*) FILTER` and `ON CONFLICT`, so that is not the reason;
the reason is that upsert conflict semantics, timezone handling and planner behaviour
are exactly the things I wanted to check against the engine this actually runs on.

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
  --add-cloudsql-instances "$CONNECTION_NAME" \
  --set-secrets "DATABASE_URL=globant-database-url:latest,API_KEY=globant-api-key:latest"
```

[`deploy/gcp.sh`](deploy/gcp.sh) has the whole sequence, from enabling the APIs to the
deploy itself. Cloud Run scales to zero between requests, which fits a reporting API
with bursty traffic. The service runs under a dedicated service account holding two
permissions and nothing else, and the database password lives in Secret Manager rather
than in an environment variable.

The deployed instance is loaded with the three supplied files, so the metric endpoints
return the numbers in this README against real data, not fixtures.

For a real migration I would put a landing zone in front of this: files arriving in
Cloud Storage, an event triggering ingestion, and the rejected rows persisted somewhere
stakeholders can read them instead of only coming back in the HTTP response.

## Scale

2,000 rows fits in a single request, so nothing here is under real pressure and I have
not benchmarked it. What is in place: inserts are chunked at 1,000 rows per statement,
which bounds statement size but does not split the transaction, since ingestion still
commits once at the end. Both metrics are computed in the database rather than pulled
into Python.

The year filter is a half-open range against the bare column rather than
`EXTRACT(YEAR FROM hire_datetime)`, which matters more than it looks. Wrapping the
column in a function leaves the planner scanning the whole index and discarding rows
(`Filter:` in the plan); comparing the column against two bounds turns it into a real
index condition (`Index Cond:`). At 2,000 rows the planner picks a sequential scan
either way, so this is about what happens later, not about the supplied data.

One wording caveat worth knowing: `inserted` in the batch response counts rows written,
which includes rows an upsert updated rather than created. It is not a count of new
records.

## Layout

```
app/
  main.py             FastAPI application and lifespan
  config.py           Environment-driven settings
  database.py         Engine, session factory, declarative base
  models.py           ORM models for the three tables
  schemas.py          Request and response contracts
  security.py         API key guard for the write endpoints
  routers/            HTTP layer: ingestion, metrics
  services/           Ingestion pipeline and metric execution
deploy/gcp.sh         One-shot provisioning of the GCP side
sql/                  The SQL, executed verbatim
tests/                Integration suite
data/                 The three source CSV files
```
