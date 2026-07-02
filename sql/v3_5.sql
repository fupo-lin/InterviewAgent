use `interview_agent`;

CREATE TABLE IF NOT EXISTS agent_evidence_items (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    evidence_id VARCHAR(160) NOT NULL,
    evidence_type VARCHAR(80) NULL,
    source_type VARCHAR(80) NULL,
    source_id BIGINT NULL,
    project_id BIGINT NULL,
    session_id BIGINT NULL,
    agent_run_id BIGINT NOT NULL,
    prompt_id VARCHAR(80) NULL,
    workflow_id VARCHAR(80) NULL,
    workflow_run_id VARCHAR(160) NULL,
    step_id VARCHAR(80) NULL,
    round_no INT NULL,
    content_excerpt TEXT NULL,
    tags JSON NULL,
    confidence VARCHAR(30) NULL,
    metadata JSON NULL,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_agent_evidence_items_agent_run
        FOREIGN KEY (agent_run_id) REFERENCES agent_runs(id),
    CONSTRAINT fk_agent_evidence_items_project
        FOREIGN KEY (project_id) REFERENCES preparation_projects(id),
    CONSTRAINT fk_agent_evidence_items_session
        FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_evidence_items_agent_run ON agent_evidence_items(agent_run_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_evidence_items'
    AND INDEX_NAME = 'idx_agent_evidence_items_agent_run'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_evidence_items_project_type ON agent_evidence_items(project_id, evidence_type)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_evidence_items'
    AND INDEX_NAME = 'idx_agent_evidence_items_project_type'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_evidence_items_session_type ON agent_evidence_items(session_id, evidence_type)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_evidence_items'
    AND INDEX_NAME = 'idx_agent_evidence_items_session_type'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_evidence_items_prompt ON agent_evidence_items(prompt_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_evidence_items'
    AND INDEX_NAME = 'idx_agent_evidence_items_prompt'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_agent_evidence_items_workflow ON agent_evidence_items(workflow_run_id, step_id)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'agent_evidence_items'
    AND INDEX_NAME = 'idx_agent_evidence_items_workflow'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
