-- MIT demo schema (shape-only, no real PII)
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY,
  item TEXT NOT NULL,
  qty INTEGER NOT NULL CHECK (qty > 0),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
