from __future__ import annotations

import sqlite3
import hashlib
import json
from typing import Any, Generator, Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mgc.db import DEFAULT_DB_PATH, init_db
from mgc.models import Delivery, DeliveryAttempt, Endpoint, Tenant
from mgc.repositories import (
    APIKeyRepository,
    DeliveryAttemptRepository,
    DeliveryRepository,
    EndpointRepository,
    EventRepository,
    TenantRepository,
)

# Tenant creation request and response models
class TenantCreate(BaseModel):
    name: str

class TenantCreateResponse(BaseModel):
    tenant_id: str
    name: str
    api_key: str

# Event creation request and response models
class EventCreate(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    endpoint: EndpointCreate

class EventCreateResponse(BaseModel):
    event_id: str
    delivery_ids: list[str]

# Endpoint creation and response models
class EndpointCreate(BaseModel):
    url: HttpUrl
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

class EndpointResponse(BaseModel):
    id: str
    tenant_id: str
    url: str
    method: str
    enabled: bool

    @classmethod
    def from_model(cls, endpoint: Endpoint) -> "EndpointResponse":
        return cls(
            id=endpoint.id,
            tenant_id=endpoint.tenant_id,
            url=endpoint.url,
            method=endpoint.method,
            enabled=endpoint.enabled,
        )

# Delivery response model
class DeliveryResponse(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    tenant_id: str
    status: str
    attempt_count: int
    next_attempt_at: Optional[str] = None
    claimed_by: Optional[str] = None
    claim_token: Optional[str] = None
    claim_expires_at: Optional[str] = None
    created_at: str
    updated_at: str

    @classmethod
    def from_model(cls, delivery: Delivery) -> "DeliveryResponse":
        return cls(**delivery.__dict__)

# Delivery attempt response model
class AttemptResponse(BaseModel):
    id: str
    delivery_id: str
    attempt_number: int
    worker_id: Optional[str] = None
    claim_token: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    outcome: Optional[str] = None
    http_status: Optional[int] = None
    error: Optional[str] = None

    @classmethod
    def from_model(cls, attempt: DeliveryAttempt) -> "AttemptResponse":
        return cls(**attempt.__dict__)


class DeliveryDetailResponse(BaseModel):
    delivery: DeliveryResponse
    attempts: list[AttemptResponse]


bearer_scheme = HTTPBearer(auto_error=False)


def get_db(request: Request) -> Generator[sqlite3.Connection, None, None]:
    conn = init_db(request.app.state.db_path)
    try:
        yield conn
    finally:
        conn.close()


def authenticate_tenant(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    conn: sqlite3.Connection = Depends(get_db),
) -> Tenant:
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    api_key = credentials.credentials.strip()
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    stored_key = APIKeyRepository(conn).get_active_by_key(api_key)
    if stored_key is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or revoked API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant = TenantRepository(conn).get(stored_key.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant


def create_app(db_path: str = DEFAULT_DB_PATH) -> FastAPI:
    app = FastAPI(title="mgc")
    app.state.db_path = db_path

    @app.post("/tenants", status_code=201)
    def create_tenant(
        request: TenantCreate, conn: sqlite3.Connection = Depends(get_db)
    ) -> TenantCreateResponse:
        tenant = TenantRepository(conn).create(request.name)
        _, api_key = APIKeyRepository(conn).create(tenant.id)
        return TenantCreateResponse(
            tenant_id=tenant.id,
            name=tenant.name,
            api_key=api_key,
        )

    @app.post("/events", status_code=201)
    def create_event(
        request: EventCreate,
        tenant: Tenant = Depends(authenticate_tenant),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> EventCreateResponse:
        endpoint_repo = EndpointRepository(conn)
        endpoint_url = str(request.endpoint.url)
        canonical_body = json.dumps(
            {
                "event_type": request.event_type,
                "payload": request.payload,
                "endpoint": {"url": endpoint_url, "method": request.endpoint.method},
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        body_hash = hashlib.sha256(canonical_body.encode("utf-8")).hexdigest()
        endpoint = endpoint_repo.get_by_tenant_url(
            tenant.id, endpoint_url, request.endpoint.method
        )
        with conn:
            if endpoint is None:
                endpoint = endpoint_repo.create_uncommitted(
                    tenant.id, endpoint_url, request.endpoint.method
                )
            try:
                event = EventRepository(conn).create_uncommitted(
                    tenant.id, request.event_type, request.payload, body_hash
                )
            except sqlite3.IntegrityError as exc:
                if "body_hash" not in str(exc):
                    raise
                raise HTTPException(
                    status_code=409,
                    detail="This event has already been submitted",
                ) from exc
            delivery = DeliveryRepository(conn).create_uncommitted(
                event.id, endpoint.id, tenant.id
            )
        return EventCreateResponse(event_id=event.id, delivery_ids=[delivery.id])

    @app.get("/endpoints")
    def list_endpoints(
        tenant: Tenant = Depends(authenticate_tenant),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> list[EndpointResponse]:
        endpoints = EndpointRepository(conn).list_by_tenant(tenant.id)
        return [EndpointResponse.from_model(endpoint) for endpoint in endpoints]

    @app.get("/deliveries/{delivery_id}", responses={404: {"description": "Delivery not found"}})
    def get_delivery(
        delivery_id: str,
        tenant: Tenant = Depends(authenticate_tenant),
        conn: sqlite3.Connection = Depends(get_db),
    ) -> DeliveryDetailResponse:
        delivery = DeliveryRepository(conn).get_by_tenant(delivery_id, tenant.id)
        if delivery is None:
            raise HTTPException(status_code=404, detail="Delivery not found")
        attempts = DeliveryAttemptRepository(conn).list_by_delivery(delivery_id)
        return DeliveryDetailResponse(
            delivery=DeliveryResponse.from_model(delivery),
            attempts=[AttemptResponse.from_model(attempt) for attempt in attempts],
        )

    return app


app = create_app()