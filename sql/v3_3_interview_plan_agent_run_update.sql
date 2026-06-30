USE `interview_agent`;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_plans ADD COLUMN agent_run_id BIGINT NULL AFTER plan_mode',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_plans'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_plans ADD COLUMN schema_version VARCHAR(80) NOT NULL DEFAULT ''InterviewPlan.v1'' AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_plans'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_plans ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_plans'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_interview_plans_agent_run ON interview_plans(agent_run_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_plans'
    AND INDEX_NAME = 'idx_interview_plans_agent_run'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_plans ADD CONSTRAINT fk_interview_plans_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_plans'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
