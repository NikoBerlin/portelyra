PRAGMA foreign_keys = ON;

CREATE TABLE identity_meta (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = 2800),
  writer_role TEXT NOT NULL CHECK (writer_role = 'identity_gateway'),
  schema_fingerprint TEXT NOT NULL CHECK (length(schema_fingerprint) = 64)
);

CREATE TABLE auth_provider_policy (
  issuer_fingerprint TEXT NOT NULL CHECK (length(issuer_fingerprint) = 64),
  audience_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('active','disabled')),
  registered_at_utc TEXT NOT NULL,
  PRIMARY KEY (issuer_fingerprint, audience_id)
);

CREATE TABLE auth_principal (
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  issuer_fingerprint TEXT NOT NULL CHECK (length(issuer_fingerprint) = 64),
  subject_fingerprint TEXT NOT NULL CHECK (length(subject_fingerprint) = 64),
  audience_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('server_user','server_admin','server_support')),
  status TEXT NOT NULL CHECK (status IN ('active','deactivated','deletion_pending')),
  principal_revision INTEGER NOT NULL CHECK (principal_revision >= 1),
  session_revision INTEGER NOT NULL CHECK (session_revision >= 1),
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  deletion_requested_at_utc TEXT,
  retention_until_utc TEXT,
  PRIMARY KEY (tenant_id, user_id),
  UNIQUE (issuer_fingerprint, subject_fingerprint),
  UNIQUE (actor_id)
);

CREATE TABLE auth_data_space_access (
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  data_space_id TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','revoked')),
  granted_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT,
  PRIMARY KEY (tenant_id, user_id, data_space_id),
  FOREIGN KEY (tenant_id, user_id) REFERENCES auth_principal(tenant_id, user_id)
);

CREATE TABLE auth_session (
  session_ref TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  data_space_id TEXT NOT NULL,
  session_revision INTEGER NOT NULL,
  principal_revision INTEGER NOT NULL,
  claims_fingerprint TEXT NOT NULL CHECK (length(claims_fingerprint) = 64),
  identity_fingerprint TEXT NOT NULL CHECK (length(identity_fingerprint) = 64),
  status TEXT NOT NULL CHECK (status IN ('active','revoked')),
  issued_at_utc TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  revoked_at_utc TEXT,
  FOREIGN KEY (tenant_id, user_id) REFERENCES auth_principal(tenant_id, user_id),
  FOREIGN KEY (tenant_id, user_id, data_space_id) REFERENCES auth_data_space_access(tenant_id, user_id, data_space_id)
);

CREATE INDEX auth_session_principal_idx ON auth_session(tenant_id, user_id, status);

CREATE TABLE auth_job_nonce (
  job_nonce TEXT PRIMARY KEY,
  key_id TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  data_space_id TEXT NOT NULL,
  job_capability TEXT NOT NULL,
  input_fingerprint TEXT NOT NULL CHECK (length(input_fingerprint) = 64),
  consumed_at_utc TEXT NOT NULL,
  FOREIGN KEY (tenant_id, user_id) REFERENCES auth_principal(tenant_id, user_id)
);

CREATE TABLE auth_audit (
  audit_ref TEXT PRIMARY KEY,
  event_code TEXT NOT NULL CHECK (event_code IN (
    'identity_store_bootstrapped','auth_provider_registered','principal_provisioned','principal_reactivated','principal_deactivated',
    'principal_deletion_requested','data_spaces_replaced','session_opened','session_logged_out',
    'sessions_rotated','signed_job_consumed'
  )),
  tenant_id TEXT NOT NULL,
  user_id TEXT NOT NULL,
  data_space_id TEXT,
  actor_id TEXT NOT NULL,
  event_at_utc TEXT NOT NULL
);
