-- Laporan harian yang sudah dibekukan. Satu isi per hari UTC, ditulis sekali (INSERT OR IGNORE),
-- sehingga pengiriman ulang selalu memakai teks yang sama.
CREATE TABLE daily_reports (
  day TEXT PRIMARY KEY,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL
);
-- Ledger pengiriman keluar. Satu baris per dedup_key (potongan laporan x saluran).
-- SENT tidak pernah dikirim ulang. SENDING dianggap milik pengirim sampai lease habis.
CREATE TABLE notification_deliveries (
  dedup_key TEXT PRIMARY KEY,
  channel TEXT NOT NULL CHECK (channel IN ('TELEGRAM')),
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'SENDING', 'SENT', 'FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0,
  lease_until TEXT,
  last_error TEXT,
  sent_at TEXT,
  updated_at TEXT NOT NULL
);
