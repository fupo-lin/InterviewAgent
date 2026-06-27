CREATE DATABASE IF NOT EXISTS interview_agent
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE interview_agent;

CREATE TABLE IF NOT EXISTS interview_sessions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_uid VARCHAR(64) NOT NULL UNIQUE,
  role_name VARCHAR(50) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interview_messages (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  role_type VARCHAR(20) NOT NULL,
  message_type VARCHAR(20) NOT NULL,
  round_no INT NOT NULL DEFAULT 0,
  content TEXT NOT NULL,
  raw_response JSON NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_interview_messages_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interview_evaluations (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id BIGINT NOT NULL,
  strengths TEXT NULL,
  weaknesses TEXT NULL,
  suggestions TEXT NULL,
  summary TEXT NULL,
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_interview_evaluations_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_interview_sessions_session_uid
  ON interview_sessions(session_uid);

CREATE INDEX idx_interview_messages_session_round
  ON interview_messages(session_id, round_no);

CREATE INDEX idx_interview_evaluations_session
  ON interview_evaluations(session_id);
