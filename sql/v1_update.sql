USE interview_agent;

-- ALTER TABLE interview_messages
--   ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'normal';

-- ALTER TABLE interview_evaluations
--   ADD COLUMN technical_ability TEXT NULL,
--   ADD COLUMN project_experience TEXT NULL,
--   ADD COLUMN communication TEXT NULL,
--   ADD COLUMN improvement_suggestions TEXT NULL,
--   ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'normal';

CREATE TABLE IF NOT EXISTS interview_summaries (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  summary_type VARCHAR(30) NOT NULL DEFAULT 'conversation',
  from_round_no INT NOT NULL DEFAULT 1,
  to_round_no INT NOT NULL,
  content TEXT NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_interview_summaries_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- CREATE INDEX idx_interview_messages_session_status
--   ON interview_messages(session_id, status);

-- CREATE INDEX idx_interview_evaluations_session_status
--   ON interview_evaluations(session_id, status);

CREATE INDEX idx_interview_summaries_session_type_round
  ON interview_summaries(session_id, summary_type, to_round_no);

CREATE INDEX idx_interview_summaries_session_status
  ON interview_summaries(session_id, status);
