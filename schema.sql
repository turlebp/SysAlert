-- Production-ready schema with proper indexes and constraints
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS subscriptions (
  chat_id INTEGER PRIMARY KEY,
  created_at INTEGER DEFAULT (strftime('%s', 'now'))
);

CREATE TABLE IF NOT EXISTS customers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chat_id INTEGER UNIQUE NOT NULL,
  alerts_enabled INTEGER DEFAULT 1,
  interval_seconds INTEGER DEFAULT 60,
  failure_threshold INTEGER DEFAULT 3,
  escalation_threshold INTEGER DEFAULT 5,
  created_at INTEGER DEFAULT (strftime('%s', 'now')),
  updated_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_customers_chat_id ON customers(chat_id);

CREATE TABLE IF NOT EXISTS targets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL,
  name TEXT NOT NULL,
  ip TEXT NOT NULL,
  port INTEGER NOT NULL,
  enabled INTEGER DEFAULT 1,
  last_checked INTEGER DEFAULT 0,
  consecutive_failures INTEGER DEFAULT 0,
  FOREIGN KEY(customer_id) REFERENCES customers(id) ON DELETE CASCADE,
  UNIQUE(customer_id, name)
);

CREATE INDEX IF NOT EXISTS idx_targets_customer_id ON targets(customer_id);
CREATE INDEX IF NOT EXISTS idx_targets_enabled ON targets(enabled);

CREATE TABLE IF NOT EXISTS history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp INTEGER DEFAULT (strftime('%s', 'now')),
  customer_chat_id INTEGER,
  target_name TEXT,
  status TEXT,
  error TEXT,
  response_time REAL
);

CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp);
CREATE INDEX IF NOT EXISTS idx_history_customer_chat_id ON history(customer_chat_id);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_chat_id INTEGER,
  action TEXT,
  details TEXT,
  created_at INTEGER DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_chat_id);

CREATE TABLE IF NOT EXISTS configs (
  key TEXT PRIMARY KEY,
  value TEXT
);