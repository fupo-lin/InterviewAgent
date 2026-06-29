use interview_agent;

ALTER TABLE interview_sessions
  ADD COLUMN project_id BIGINT NULL AFTER id,
  ADD COLUMN interview_plan_id BIGINT NULL AFTER project_id;

CREATE TABLE IF NOT EXISTS preparation_projects (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_uid VARCHAR(64) NOT NULL UNIQUE,
  title VARCHAR(100) NOT NULL,
  target_role VARCHAR(100) NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS job_descriptions (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  title VARCHAR(100) NULL,
  company_name VARCHAR(100) NULL,
  source_url VARCHAR(500) NULL,
  raw_content MEDIUMTEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_job_descriptions_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS jd_analyses (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  jd_id BIGINT NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_jd_analyses_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_jd_analyses_jd
    FOREIGN KEY (jd_id) REFERENCES job_descriptions(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resume_documents (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  file_name VARCHAR(255) NULL,
  file_type VARCHAR(30) NULL,
  raw_content MEDIUMTEXT NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_resume_documents_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS resume_profiles (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  resume_id BIGINT NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_resume_profiles_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_resume_profiles_resume
    FOREIGN KEY (resume_id) REFERENCES resume_documents(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS gap_analyses (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  jd_analysis_id BIGINT NOT NULL,
  resume_profile_id BIGINT NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_gap_analyses_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_gap_analyses_jd_analysis
    FOREIGN KEY (jd_analysis_id) REFERENCES jd_analyses(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_gap_analyses_resume_profile
    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS interview_plans (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NOT NULL,
  jd_analysis_id BIGINT NULL,
  resume_profile_id BIGINT NULL,
  gap_analysis_id BIGINT NULL,
  plan_mode VARCHAR(30) NOT NULL,
  content JSON NOT NULL,
  raw_response JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'normal',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_interview_plans_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE CASCADE,
  CONSTRAINT fk_interview_plans_jd_analysis
    FOREIGN KEY (jd_analysis_id) REFERENCES jd_analyses(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_interview_plans_resume_profile
    FOREIGN KEY (resume_profile_id) REFERENCES resume_profiles(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_interview_plans_gap_analysis
    FOREIGN KEY (gap_analysis_id) REFERENCES gap_analyses(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE INDEX idx_preparation_projects_uid
  ON preparation_projects(project_uid);

CREATE INDEX idx_job_descriptions_project
  ON job_descriptions(project_id, status);

CREATE INDEX idx_jd_analyses_project
  ON jd_analyses(project_id, status);

CREATE INDEX idx_resume_documents_project
  ON resume_documents(project_id, status);

CREATE INDEX idx_resume_profiles_project
  ON resume_profiles(project_id, status);

CREATE INDEX idx_gap_analyses_project
  ON gap_analyses(project_id, status);

CREATE INDEX idx_interview_plans_project
  ON interview_plans(project_id, status);
