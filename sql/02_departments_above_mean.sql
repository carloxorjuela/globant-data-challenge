-- Requirement 2
-- Departments that hired more employees than the mean across all departments
-- for a given year, ordered by hires descending.
--
-- Notes
--   * The mean covers every department on record, including any that hired
--     nobody that year. The requirement says "the mean of employees hired in
--     2021 for all the departments", and a department that hired nobody is
--     still one of all the departments. The distinction matters: with three
--     departments hiring 3, 2 and 0, averaging only the active ones gives 2.5
--     and returns one department, while averaging all three gives 1.67 and
--     returns two. With the supplied data every department hired at least
--     once, so both readings happen to agree.
--   * Hires with a NULL department_id cannot be attributed to anyone and are
--     excluded from the counts and from the mean. A NULL hire_datetime fails
--     the range comparison and is excluded the same way.
--   * The year filter is a half-open range so the index on hire_datetime stays
--     usable; EXTRACT(YEAR FROM ...) would hide the column behind a function.
--   * Ties on the hire count are broken by department id so the endpoint is
--     reproducible; without it the row order would be planner-dependent.

WITH hires AS (
    SELECT
        d.id,
        d.department,
        COUNT(e.id) AS hired
    FROM departments AS d
    LEFT JOIN hired_employees AS e
           ON e.department_id = d.id
          AND e.hire_datetime >= make_timestamptz((:year)::int, 1, 1, 0, 0, 0, 'UTC')
          AND e.hire_datetime <  make_timestamptz((:year)::int + 1, 1, 1, 0, 0, 0, 'UTC')
    GROUP BY d.id, d.department
)
SELECT
    id,
    department,
    hired
FROM hires
WHERE hired > (SELECT AVG(hired) FROM hires)
ORDER BY hired DESC, id;
