USE `interview_agent`;

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  project_id BIGINT NULL,
  session_id BIGINT NULL,
  source_type VARCHAR(80) NOT NULL,
  source_id BIGINT NULL,
  title VARCHAR(255) NULL,
  content_hash VARCHAR(80) NOT NULL,
  metadata JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_knowledge_documents_project
    FOREIGN KEY (project_id) REFERENCES preparation_projects(id)
    ON DELETE SET NULL,
  CONSTRAINT fk_knowledge_documents_session
    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
    ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS knowledge_chunks (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  document_id BIGINT NOT NULL,
  project_id BIGINT NULL,
  session_id BIGINT NULL,
  source_type VARCHAR(80) NOT NULL,
  source_id BIGINT NULL,
  chunk_index INT NOT NULL,
  content TEXT NOT NULL,
  content_hash VARCHAR(80) NOT NULL,
  token_count INT NOT NULL DEFAULT 0,
  embedding_model VARCHAR(80) NOT NULL,
  embedding JSON NULL,
  keywords JSON NULL,
  metadata JSON NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_knowledge_chunks_document
    FOREIGN KEY (document_id) REFERENCES knowledge_documents(id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET @schema_name = DATABASE();

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_knowledge_documents_project_source ON knowledge_documents(project_id, source_type, source_id, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'knowledge_documents'
    AND INDEX_NAME = 'idx_knowledge_documents_project_source'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_knowledge_chunks_project_source ON knowledge_chunks(project_id, source_type, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'knowledge_chunks'
    AND INDEX_NAME = 'idx_knowledge_chunks_project_source'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_knowledge_chunks_session_source ON knowledge_chunks(session_id, source_type, status)',
    'SELECT 1'
  )
  FROM information_schema.STATISTICS
  WHERE TABLE_SCHEMA = @schema_name
    AND TABLE_NAME = 'knowledge_chunks'
    AND INDEX_NAME = 'idx_knowledge_chunks_session_source'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
