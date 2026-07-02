USE `interview_agent`;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE jd_analyses ADD COLUMN agent_run_id BIGINT NULL AFTER jd_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'jd_analyses'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE jd_analyses ADD COLUMN schema_version VARCHAR(80) NOT NULL DEFAULT ''JDAnalysis.v1'' AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'jd_analyses'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE jd_analyses ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'jd_analyses'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_jd_analyses_agent_run ON jd_analyses(agent_run_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'jd_analyses'
    AND INDEX_NAME = 'idx_jd_analyses_agent_run'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE jd_analyses ADD CONSTRAINT fk_jd_analyses_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'jd_analyses'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_profiles ADD COLUMN agent_run_id BIGINT NULL AFTER resume_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_profiles'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_profiles ADD COLUMN schema_version VARCHAR(80) NOT NULL DEFAULT ''ResumeProfile.v1'' AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_profiles'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_profiles ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_profiles'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_resume_profiles_agent_run ON resume_profiles(agent_run_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_profiles'
    AND INDEX_NAME = 'idx_resume_profiles_agent_run'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_profiles ADD CONSTRAINT fk_resume_profiles_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_profiles'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
