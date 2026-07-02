USE `interview_agent`;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_messages ADD COLUMN agent_run_id BIGINT NULL AFTER round_no',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_messages'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_messages ADD COLUMN schema_version VARCHAR(80) NULL AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_messages'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_messages ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_messages'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_interview_messages_agent_run ON interview_messages(agent_run_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_messages'
    AND INDEX_NAME = 'idx_interview_messages_agent_run'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_messages ADD CONSTRAINT fk_interview_messages_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_messages'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_summaries ADD COLUMN agent_run_id BIGINT NULL AFTER to_round_no',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_summaries'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_summaries ADD COLUMN schema_version VARCHAR(80) NULL AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_summaries'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_summaries ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_summaries'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_interview_summaries_agent_run ON interview_summaries(agent_run_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_summaries'
    AND INDEX_NAME = 'idx_interview_summaries_agent_run'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE interview_summaries ADD CONSTRAINT fk_interview_summaries_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_summaries'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
