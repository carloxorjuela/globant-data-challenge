-- Requirement 1
-- Employees hired per job and department in a given year, split by quarter,
-- ordered alphabetically by department and job.
--
-- Notes
--   * hire_datetime is TIMESTAMPTZ. It is pinned to UTC before EXTRACT so the
--     quarter a hire falls into never depends on the server's session
--     timezone; the source files are ISO-8601 with a Z suffix.
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
WHERE e.hire_datetime IS NOT NULL
  AND EXTRACT(YEAR FROM e.hire_datetime AT TIME ZONE 'UTC') = :year
GROUP BY d.department, j.job
ORDER BY d.department, j.job;
