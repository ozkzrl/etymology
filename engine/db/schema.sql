-- Etimoloji Araştırma Motoru Veritabanı Şeması

CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_word TEXT NOT NULL UNIQUE,
    proto_turkic_root TEXT,
    root_meaning TEXT,
    sources_json TEXT,
    full_finding_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS turkic_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL,
    lang_code TEXT NOT NULL,
    lang_name TEXT NOT NULL,
    word TEXT NOT NULL,
    meaning TEXT,
    script TEXT,
    FOREIGN KEY (finding_id) REFERENCES findings(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_findings_query_word ON findings(query_word);
CREATE INDEX IF NOT EXISTS idx_turkic_entries_word ON turkic_entries(word);
CREATE INDEX IF NOT EXISTS idx_turkic_entries_lang ON turkic_entries(lang_code);
