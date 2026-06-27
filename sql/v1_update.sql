USE interview_agent;

-- ALTER TABLE interview_messages
--   ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'normal';

ALTER TABLE interview_evaluations
  ADD COLUMN technical_ability TEXT NULL,
  ADD COLUMN project_experience TEXT NULL,
  ADD COLUMN communication TEXT NULL,
  ADD COLUMN improvement_suggestions TEXT NULL;

CREATE INDEX idx_interview_messages_session_status
  ON interview_messages(session_id, status);

CREATE INDEX idx_interview_evaluations_session_status
  ON interview_evaluations(session_id, status);
