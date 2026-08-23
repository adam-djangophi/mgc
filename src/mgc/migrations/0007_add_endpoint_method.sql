ALTER TABLE endpoints ADD COLUMN method TEXT NOT NULL DEFAULT 'POST'
    CHECK (method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'));

DROP INDEX IF EXISTS idx_endpoints_tenant_url;
CREATE UNIQUE INDEX idx_endpoints_tenant_url_method
    ON endpoints (tenant_id, url, method);
