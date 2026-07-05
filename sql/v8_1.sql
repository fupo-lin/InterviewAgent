USE `interview_agent`;

CREATE TABLE IF NOT EXISTS candidate_growth_reports (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  report_uid VARCHAR(64) NOT NULL UNIQUE,
  project_id BIGINT NULL,
  session_id BIGINT NOT NULL,
  workflow_run_id VARCHAR(160) NULL,
  agent_run_id BIGINT NULL,
  schema_version VARCHAR(80) NOT NULL DEFAULT 'CandidateGrowthReport.v1',
  report_version VARCHAR(30) NOT NULL DEFAULT 'v1',
  source_snapshot JSON NULL,
  evidence_refs JSON NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'success',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_growth_reports_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_growth_reports_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_growth_reports_agent_run
    FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_growth_reports_session ON candidate_growth_reports(session_id, report_version, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'candidate_growth_reports'
    AND INDEX_NAME = 'idx_growth_reports_session'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_growth_reports_project ON candidate_growth_reports(project_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'candidate_growth_reports'
    AND INDEX_NAME = 'idx_growth_reports_project'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
