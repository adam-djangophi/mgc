CREATE TABLE endpoints (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    url TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX idx_endpoints_tenant_id ON endpoints (tenant_id);
