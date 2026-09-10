-- Requirement 2
-- Departments that hired more employees than the mean across all departments
-- for a given year, ordered by hires descending.
--
-- Notes
--   * The mean is taken over departments that hired at least once in the year.
--     Dividing instead by every row in `departments` would lower the mean by
--     counting departments with no activity as zeros. With the supplied 2021
--     data both readings return the same seven departments, since all twelve
--     departments hired at least once -- the choice is documented rather than
--     silently assumed.
--   * Hires with a NULL department_id cannot be attributed and are excluded
--     from both the per-department counts and the mean.

WITH hires AS (
    SELECT
        department_id,
        COUNT(*) AS hired
    FROM hired_employees
    WHERE department_id IS NOT NULL
      AND hire_datetime IS NOT NULL
      AND EXTRACT(YEAR FROM hire_datetime AT TIME ZONE 'UTC') = :year
    GROUP BY department_id
)
SELECT
    d.id,
    d.department,
    h.hired
FROM hires AS h
JOIN departments AS d ON d.id = h.department_id
WHERE h.hired > (SELECT AVG(hired) FROM hires)
ORDER BY h.hired DESC;
