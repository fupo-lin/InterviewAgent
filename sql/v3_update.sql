USE `interview_agent`;

CREATE TABLE IF NOT EXISTS agent_runs (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  agent_name VARCHAR(80) NOT NULL,
  agent_version VARCHAR(30) NULL,
  task_name VARCHAR(80) NOT NULL,
  project_id BIGINT NULL,
  session_id BIGINT NULL,
  input_schema_version VARCHAR(80) NULL,
  output_schema_version VARCHAR(80) NULL,
  prompt_id VARCHAR(80) NOT NULL,
  prompt_version VARCHAR(30) NOT NULL,
  model_name VARCHAR(80) NULL,
  input_snapshot JSON NULL,
  context_refs JSON NULL,
  evidence_refs JSON NULL,
  output_snapshot JSON NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'success',
  error_message TEXT NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_agent_runs_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_agent_runs_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_runs_project ON agent_runs(project_id, agent_name, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_runs'
    AND INDEX_NAME = 'idx_agent_runs_project'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_runs_session ON agent_runs(session_id, agent_name, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_runs'
    AND INDEX_NAME = 'idx_agent_runs_session'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_runs_prompt ON agent_runs(prompt_id, prompt_version)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_runs'
    AND INDEX_NAME = 'idx_agent_runs_prompt'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_interview_plan_executions_session ON interview_plan_executions(session_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'interview_plan_executions'
    AND INDEX_NAME = 'idx_interview_plan_executions_session'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_project_candidate_profiles_project ON project_candidate_profiles(project_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND INDEX_NAME = 'idx_project_candidate_profiles_project'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_resume_authenticity_reports_project ON resume_authenticity_reports(project_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_authenticity_reports'
    AND INDEX_NAME = 'idx_resume_authenticity_reports_project'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_resume_rewrite_results_project ON resume_rewrite_results(project_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_rewrite_results'
    AND INDEX_NAME = 'idx_resume_rewrite_results_project'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN agent_run_id BIGINT NULL AFTER source_session_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN schema_version VARCHAR(80) NOT NULL DEFAULT ''ProjectCandidateProfile.v1'' AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN profile_version_no INT NOT NULL DEFAULT 1 AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'profile_version_no'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD COLUMN evidence_refs JSON NULL AFTER profile_version_no',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_authenticity_reports ADD COLUMN agent_run_id BIGINT NULL AFTER session_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_authenticity_reports'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_authenticity_reports ADD COLUMN schema_version VARCHAR(80) NOT NULL DEFAULT ''ResumeAuthenticityReport.v1'' AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_authenticity_reports'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_authenticity_reports ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_authenticity_reports'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_rewrite_results ADD COLUMN agent_run_id BIGINT NULL AFTER rewrite_mode',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_rewrite_results'
    AND COLUMN_NAME = 'agent_run_id'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_rewrite_results ADD COLUMN schema_version VARCHAR(80) NOT NULL DEFAULT ''ResumeRewriteResult.v1'' AFTER agent_run_id',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_rewrite_results'
    AND COLUMN_NAME = 'schema_version'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_rewrite_results ADD COLUMN evidence_refs JSON NULL AFTER schema_version',
    'SELECT 1'
  )
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_rewrite_results'
    AND COLUMN_NAME = 'evidence_refs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE project_candidate_profiles ADD CONSTRAINT fk_project_candidate_profiles_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'project_candidate_profiles'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_authenticity_reports ADD CONSTRAINT fk_resume_auth_reports_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_authenticity_reports'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE resume_rewrite_results ADD CONSTRAINT fk_resume_rewrite_agent_run FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id) ON DELETE SET NULL',
    'SELECT 1'
  )
  FROM information_schema.KEY_COLUMN_USAGE
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'resume_rewrite_results'
    AND COLUMN_NAME = 'agent_run_id'
    AND REFERENCED_TABLE_NAME = 'agent_runs'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
