USE `interview_agent`;

CREATE TABLE IF NOT EXISTS workflow_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  workflow_run_id VARCHAR(160) NOT NULL UNIQUE,
  workflow_id VARCHAR(80) NOT NULL,
  thread_id VARCHAR(160) NOT NULL UNIQUE,
  project_id BIGINT NULL,
  session_id BIGINT NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'running',
  current_step VARCHAR(80) NULL,
  state JSON NULL,
  last_error JSON NULL,
  error_message TEXT NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_workflow_runs_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_workflow_runs_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_workflow_runs_workflow ON workflow_runs(workflow_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'workflow_runs'
    AND INDEX_NAME = 'idx_workflow_runs_workflow'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_workflow_runs_project ON workflow_runs(project_id, workflow_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'workflow_runs'
    AND INDEX_NAME = 'idx_workflow_runs_project'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_workflow_runs_session ON workflow_runs(session_id, workflow_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'workflow_runs'
    AND INDEX_NAME = 'idx_workflow_runs_session'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
