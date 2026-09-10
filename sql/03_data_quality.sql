-- Complementary report (not required by the challenge)
-- Completeness of the migrated hires.
--
-- The historical files contain rows with no name, no hire date, no department
-- or no job. They are loaded rather than discarded, so this endpoint gives
-- stakeholders a way to see exactly how much of the migration is incomplete
-- and why some hires never appear in the quarterly report.

SELECT
    COUNT(*)                                                  AS total_rows,
    COUNT(*) FILTER (WHERE name IS NULL)                      AS missing_name,
    COUNT(*) FILTER (WHERE hire_datetime IS NULL)             AS missing_hire_datetime,
    COUNT(*) FILTER (WHERE department_id IS NULL)             AS missing_department,
    COUNT(*) FILTER (WHERE job_id IS NULL)                    AS missing_job,
    COUNT(*) FILTER (
        WHERE name IS NULL
           OR hire_datetime IS NULL
           OR department_id IS NULL
           OR job_id IS NULL
    )                                                         AS incomplete_rows
FROM hired_employees;
