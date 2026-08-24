PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    role TEXT NOT NULL,
    seal TEXT NOT NULL,
    discipline TEXT NOT NULL,
    summary TEXT NOT NULL,
    teaser TEXT NOT NULL,
    paid_content TEXT NOT NULL,
    deliverables TEXT NOT NULL,
    tags TEXT NOT NULL,
    accent TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    published INTEGER NOT NULL DEFAULT 1 CHECK (published IN (0, 1)),
    price_override INTEGER CHECK (price_override IS NULL OR price_override >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    normalized_email TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'review', 'suspended')),
    risk_level TEXT NOT NULL DEFAULT 'low'
        CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT NOT NULL UNIQUE,
    idea_id INTEGER NOT NULL REFERENCES ideas(id),
    customer_name TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'cancelled', 'refunded')),
    payment_provider TEXT NOT NULL DEFAULT 'mock',
    payment_ref TEXT,
    payment_token_hash TEXT NOT NULL UNIQUE,
    access_token_hash TEXT NOT NULL UNIQUE,
    activation_token_hash TEXT UNIQUE,
    created_at TEXT NOT NULL,
    paid_at TEXT,
    customer_id INTEGER REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS order_consents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE REFERENCES orders(id),
    terms_version TEXT NOT NULL,
    purchase_notice_consent INTEGER NOT NULL CHECK (purchase_notice_consent IN (0, 1)),
    digital_content_consent INTEGER NOT NULL CHECK (digital_content_consent IN (0, 1)),
    ip TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS activation_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    revoked_at TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    delivery_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (delivery_status IN ('pending', 'sent', 'failed', 'development'))
);

CREATE TABLE IF NOT EXISTS customer_login_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_email TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    revoked_at TEXT,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    requested_ip TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS customer_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_hash TEXT NOT NULL UNIQUE,
    customer_email TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revoked_reason TEXT,
    user_agent TEXT NOT NULL,
    customer_id INTEGER REFERENCES customers(id),
    device_id INTEGER REFERENCES customer_devices(id),
    ip TEXT,
    idle_expires_at TEXT,
    replay_attempts INTEGER NOT NULL DEFAULT 0,
    last_replay_at TEXT
);

CREATE TABLE IF NOT EXISTS customer_devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    public_id TEXT NOT NULL UNIQUE,
    device_token_hash TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    first_ip TEXT NOT NULL,
    last_ip TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    trusted_until TEXT NOT NULL,
    revoked_at TEXT,
    revoked_reason TEXT
);

CREATE TABLE IF NOT EXISTS section_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    section_key TEXT NOT NULL,
    idea_id INTEGER REFERENCES ideas(id),
    author_type TEXT NOT NULL CHECK (author_type IN ('customer', 'admin')),
    customer_id INTEGER REFERENCES customers(id),
    reply_to_id INTEGER REFERENCES section_messages(id),
    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'private')),
    status TEXT NOT NULL CHECK (status IN ('pending', 'published', 'hidden')),
    body TEXT NOT NULL CHECK (length(body) BETWEEN 2 AND 800),
    moderated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (author_type = 'admin' OR customer_id IS NOT NULL),
    CHECK (visibility = 'public' OR customer_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS access_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    customer_id INTEGER REFERENCES customers(id),
    device_id INTEGER REFERENCES customer_devices(id),
    order_id INTEGER REFERENCES orders(id),
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    action_taken TEXT NOT NULL,
    ip TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_no TEXT NOT NULL UNIQUE,
    access_event_id INTEGER NOT NULL UNIQUE REFERENCES access_events(id),
    customer_id INTEGER REFERENCES customers(id),
    level TEXT NOT NULL CHECK (level IN ('medium', 'high', 'critical')),
    reason_codes TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'reviewing', 'resolved', 'dismissed')),
    action_taken TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS notification_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT NOT NULL UNIQUE,
    incident_id INTEGER REFERENCES risk_incidents(id),
    channel TEXT NOT NULL,
    recipient_masked TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'failed', 'skipped')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sent_at TEXT
);

CREATE TABLE IF NOT EXISTS email_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER REFERENCES orders(id),
    email_kind TEXT NOT NULL,
    recipient_masked TEXT NOT NULL,
    status TEXT NOT NULL,
    error_code TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payment_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    order_id INTEGER REFERENCES orders(id),
    provider TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    result TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    idea_id INTEGER REFERENCES ideas(id),
    source TEXT NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS line_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    ip TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked_at TEXT,
    revoked_reason TEXT,
    auth_method TEXT NOT NULL DEFAULT 'password',
    restricted INTEGER NOT NULL DEFAULT 0 CHECK (restricted IN (0, 1))
);

CREATE TABLE IF NOT EXISTS admin_webauthn_credentials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    credential_id BLOB NOT NULL UNIQUE,
    public_key BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    transports_json TEXT NOT NULL DEFAULT '[]',
    device_type TEXT NOT NULL,
    backed_up INTEGER NOT NULL DEFAULT 0 CHECK (backed_up IN (0, 1)),
    aaguid TEXT NOT NULL DEFAULT '',
    label TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    revoked_at TEXT,
    revoked_reason TEXT
);

CREATE TABLE IF NOT EXISTS admin_webauthn_challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    challenge_hash TEXT NOT NULL UNIQUE,
    purpose TEXT NOT NULL CHECK (purpose IN ('registration', 'authentication')),
    ip TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);

CREATE TABLE IF NOT EXISTS admin_recovery_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    used_at TEXT,
    used_ip TEXT,
    revoked_at TEXT
);

CREATE TABLE IF NOT EXISTS admin_login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ip TEXT NOT NULL,
    success INTEGER NOT NULL CHECK (success IN (0, 1)),
    attempted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    ip TEXT NOT NULL,
    path TEXT NOT NULL,
    action_taken TEXT NOT NULL,
    detail TEXT NOT NULL,
    user_agent TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocked_ips (
    ip TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    blocked_until TEXT NOT NULL,
    hit_count INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target TEXT NOT NULL,
    detail TEXT NOT NULL,
    ip TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ideas_published_sort ON ideas (published, sort_order);
CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status);
CREATE INDEX IF NOT EXISTS idx_activation_order_expiry ON activation_codes (order_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_login_email_expiry ON customer_login_codes (customer_email, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_session_email_expiry ON customer_sessions (customer_email, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_customer_devices_active ON customer_devices (customer_id, revoked_at, trusted_until DESC);
CREATE INDEX IF NOT EXISTS idx_section_messages_public ON section_messages (section_key, idea_id, visibility, status, created_at);
CREATE INDEX IF NOT EXISTS idx_section_messages_private ON section_messages (customer_id, section_key, idea_id, visibility, created_at);
CREATE INDEX IF NOT EXISTS idx_section_messages_moderation ON section_messages (status, visibility, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_events_created ON access_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_access_events_customer ON access_events (customer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_risk_incidents_status ON risk_incidents (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_status ON notification_queue (status, created_at);
CREATE INDEX IF NOT EXISTS idx_email_events_order_time ON email_events (order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_name_created ON analytics_events (event_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_security_created ON security_events (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_login_ip_time ON admin_login_attempts (ip, attempted_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_webauthn_active ON admin_webauthn_credentials (revoked_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_webauthn_challenge_expiry ON admin_webauthn_challenges (purpose, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_webauthn_challenge_ip_time ON admin_webauthn_challenges (purpose, ip, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_recovery_available ON admin_recovery_codes (used_at, revoked_at);
