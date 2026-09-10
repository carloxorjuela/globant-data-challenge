-- Requirement 1
-- Employees hired per job and department in a given year, split by quarter,
-- ordered alphabetically by department and job.
--
-- Notes
--   * The year filter is a half-open range rather than
--     EXTRACT(YEAR FROM hire_datetime) = :year. Wrapping the column in a
--     function hides it from the index on hire_datetime; comparing the bare
--     column against two bounds does not. Both bounds are built in UTC, which
--     also keeps the boundary independent of the server's timezone.
--   * The quarter pivot still uses EXTRACT, but only on rows the range filter
--     has already selected, so it costs nothing in access path terms.
--   * The joins are inner on purpose. A hire with no department or no job
--     cannot be placed in this report, and the historical data contains such
--     rows. They are excluded here and surfaced by the data-quality endpoint.
--   * COUNT(*) FILTER pivots the quarters in one pass, so quarters with no
--     hires come back as 0 rather than as a missing row.

SELECT
    d.department,
    j.job,
    COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.hire_datetime AT TIME ZONE 'UTC') = 1) AS "Q1",
    COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.hire_datetime AT TIME ZONE 'UTC') = 2) AS "Q2",
    COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.hire_datetime AT TIME ZONE 'UTC') = 3) AS "Q3",
    COUNT(*) FILTER (WHERE EXTRACT(QUARTER FROM e.hire_datetime AT TIME ZONE 'UTC') = 4) AS "Q4"
FROM hired_employees AS e
JOIN departments AS d ON d.id = e.department_id
JOIN jobs        AS j ON j.id = e.job_id
WHERE e.hire_datetime >= make_timestamptz((:year)::int, 1, 1, 0, 0, 0, 'UTC')
  AND e.hire_datetime <  make_timestamptz((:year)::int + 1, 1, 1, 0, 0, 0, 'UTC')
GROUP BY d.department, j.job
ORDER BY d.department, j.job;
