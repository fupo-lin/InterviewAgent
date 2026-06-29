use `interview_agent`;

CREATE TABLE IF NOT EXISTS interview_plan_executions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  interview_plan_id BIGINT NOT NULL,
  current_section_key VARCHAR(80) NULL,
  current_section_index INT NOT NULL DEFAULT 0,
  current_section_round_no INT NOT NULL DEFAULT 0,
  total_completed_round_no INT NOT NULL DEFAULT 0,
  state JSON NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_plan_executions_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_plan_executions_plan
    FOREIGN KEY (interview_plan_id) REFERENCES interview_plans(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;



CREATE INDEX idx_interview_plan_executions_session
  ON interview_plan_executions(session_id, status);
