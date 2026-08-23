CREATE UNIQUE INDEX idx_endpoints_tenant_url
    ON endpoints (tenant_id, url);
