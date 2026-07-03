USE `interview_agent`;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN previous_profile_id BIGINT NULL AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'previous_profile_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN is_current TINYINT(1) NOT NULL DEFAULT 1 AFTER profile_version_no',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'is_current'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN source_context_refs JSON NULL AFTER is_current',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'source_context_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE project_candidate_profiles
SET status = 'superseded',
    is_current = 0
WHERE status != 'deleted'
  AND id NOT IN (
    SELECT latest_id
    FROM (
      SELECT p.id AS latest_id
      FROM project_candidate_profiles p
      JOIN (
        SELECT project_id, MAX(profile_version_no) AS max_version
        FROM project_candidate_profiles
        WHERE status != 'deleted'
        GROUP BY project_id
      ) latest_version
        ON latest_version.project_id = p.project_id
       AND latest_version.max_version = p.profile_version_no
      JOIN (
        SELECT project_id, profile_version_no, MAX(id) AS max_id
        FROM project_candidate_profiles
        WHERE status != 'deleted'
        GROUP BY project_id, profile_version_no
      ) latest_id
        ON latest_id.project_id = p.project_id
       AND latest_id.profile_version_no = p.profile_version_no
       AND latest_id.max_id = p.id
      WHERE p.status != 'deleted'
    ) latest_profiles
  );

UPDATE project_candidate_profiles
SET status = 'current',
    is_current = 1
WHERE status != 'deleted'
  AND id IN (
    SELECT latest_id
    FROM (
      SELECT p.id AS latest_id
      FROM project_candidate_profiles p
      JOIN (
        SELECT project_id, MAX(profile_version_no) AS max_version
        FROM project_candidate_profiles
        WHERE status != 'deleted'
        GROUP BY project_id
      ) latest_version
        ON latest_version.project_id = p.project_id
       AND latest_version.max_version = p.profile_version_no
      JOIN (
        SELECT project_id, profile_version_no, MAX(id) AS max_id
        FROM project_candidate_profiles
        WHERE status != 'deleted'
        GROUP BY project_id, profile_version_no
      ) latest_id
        ON latest_id.project_id = p.project_id
       AND latest_id.profile_version_no = p.profile_version_no
       AND latest_id.max_id = p.id
      WHERE p.status != 'deleted'
    ) latest_profiles
  );

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD CONSTRAINT fk_project_candidate_profiles_previous FOREIGN KEY (previous_profile_id) REFERENCES project_candidate_profiles(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'previous_profile_id'
    AND REFERENCED_TABLE_NAME = 'project_candidate_profiles'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_project_candidate_profiles_current ON project_candidate_profiles(project_id, is_current, profile_version_no)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND INDEX_NAME = 'idx_project_candidate_profiles_current'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
