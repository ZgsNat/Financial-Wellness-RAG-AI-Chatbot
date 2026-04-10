-- Runs once when postgres container is first created.
-- Each service owns its database — no cross-service queries allowed.
CREATE DATABASE identity_db;
CREATE DATABASE transaction_db;
CREATE DATABASE journal_db;
CREATE DATABASE insight_db;
CREATE DATABASE notification_db;
