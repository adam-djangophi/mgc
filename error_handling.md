# Error Handling

This document explains how `mgc` handles the failure cases

## API authentication errors

Protected routes require:

```http
Authorization: Bearer <api-key>
```

Missing, empty, invalid, and revoked API keys all return:

```http
401 Unauthorized
WWW-Authenticate: Bearer
```


## Request validation errors

FastAPI and Pydantic validate incoming requests before the route runs.

An event must contain:

- `event_type` 
- `endpoint.url` - Must be a url
- `endpoint.method` and must match `GET, POST, PUT, PATCH, DELETE, HEAD, OPTIONS`

The payload is optional and defaults to an empty object.

Invalid or missing fields return `422 Unprocessable Entity`. 

## Duplicate event submissions

The API creates a canonical representation of the event request and hashes it with SHA-256. The hash includes:

- Event type.
- Payload.
- Endpoint URL.
- Endpoint method.

ordering does not change the canonical representation. A uniqueness constraint prevents the same event body from being inserted again.

A duplicate submission returns:

```http
409 Conflict
```

This check occurs inside the event transaction, so concurrent duplicate requests cannot both create separate internal events successfully.

## Atomic event and delivery creation

Event creation, endpoint creation, delivery creation, and the outbox message are written in one SQLite transaction:

```text
BEGIN
  create or find endpoint
  create event
  create delivery
  create outbox message
COMMIT
```

If any database operation fails, the transaction rolls back. This prevents partial state such as an event without its delivery or a delivery without a corresponding outbox message.

## Durable outbox failures

The `delivery_outbox` table records whether a delivery has been published to a queue. A new message starts with:

```text
published_at = NULL
attempt_count = 0
```

The publisher reads unpublished messages and sends the delivery ID to the
in-process `asyncio.Queue`. The running worker process starts both the
publisher and the queue consumers.

If publication succeeds:

```text
published_at = current time
```

If publication fails:

```text
published_at remains NULL
attempt_count increases
next_attempt_at is moved into the future
last_error stores the failure
```

The message remains durable and can be published again later. This handles the failure where the database commit succeeds but queue publication fails.


## Delivery state

Delivery state is persisted in the `deliveries` table:

```text
pending    waiting to be processed or retried
claimed    currently owned by a worker
succeeded  completed with a 2xx response
dead       will not be attempted again
```

Each attempt is persisted separately in `delivery_attempts`, including its attempt number, worker ID, claim token, HTTP status, outcome, and error message.

## Duplicate worker processing

A worker claims a delivery with an atomic database update. A claim records:

```text
claimed_by
claim_token
claim_expires_at
```

An unexpired claim cannot be taken by another worker. Status updates include the claim token, so an old worker cannot update a delivery after another worker has reclaimed it.


## Abandoned workers

If a worker crashes while a delivery is `claimed`, the claim eventually expires. Due-work lookup includes both:

- Pending deliveries whose `next_attempt_at` has arrived.
- Claimed deliveries whose `claim_expires_at` has expired.

Another worker can then reclaim the delivery with a new claim token and continue processing it.


## Webhook request failures

`WebhookVisitor` classifies network and HTTP results as follows:

| Result | Behavior |
|---|---|
| `2xx` | Mark delivery `succeeded`. |
| `429` | Retry with exponential backoff. |
| `5xx` | Retry with exponential backoff. |
| `TimeoutException` | Retry with exponential backoff. |
| `NetworkError` | Retry with exponential backoff. |
| Other `4xx` | Mark delivery `dead` immediately. |
| Any unexpected exception while processing a queued delivery | Convert to `retryable=True` and retry. |

The worker catches a broad exception in `process_queued()` and turns it into a retryable `WebhookVisitResult(None, str(exc), retryable=True)` result. This includes malformed JSON payloads from `json.loads(payload)` as well as any other unexpected failure during the HTTP send path.

The retry delays are:

```text
After attempt 1: 1 second
After attempt 2: 2 seconds
After attempt 3: 4 seconds
After attempt 4: 8 seconds
```

These are minimum delays. The actual retry can happen later depending on polling, available workers, and other deliveries in progress. There is currently no jitter added to the backoff.

After five failed attempts, the delivery becomes `dead` and is not retried again.

## HTTP 4xx responses (none transitive)

A valid URL does not guarantee that a website will accept a request. Normal websites may return `403`, `405`, or another `4xx` response because of:

- Bot protection.
- Missing cookies or browser verification.
- Unsupported HTTP methods.
- Requests containing an unexpected body.
- The URL not being a webhook receiver.

These are treated as permanent failures by the worker. A webhook testing service or endpoint controlled by the tenant should be used for delivery testing.

## Slow or broken endpoints

Timeouts and network failures are treated as transient failures and are persisted for retry. The delivery attempt still finishes with an error recorded in its attempt history.

The implementation currently has no per-endpoint circuit breaker, no tenant-level concurrency cap, and no separate per-tenant queue. Slow or noisy endpoints therefore share the same worker pool and database-backed retry loop.

## Polling and retry scheduling

The outbox publisher polls the database for unpublished messages. When it
finds work, it places delivery IDs onto the async queue. The delivery worker
consumes those IDs with up to 20 concurrent consumers. When no outbox messages
are ready, the publisher waits for the configured polling interval, which
defaults to one second.

A retry is not performed repeatedly inside the same function call. Instead, the failure is persisted as: so that a later publisher poll can requeue
the delivery when it becomes eligible. The worker then consumes the delivery ID again and claims it before sending.

## Graceful shutdown

The worker listens for a stop event. On normal shutdown, such as `Ctrl+C`, it stops starting new batches, allows the active batch to finish, and closes the database connection.

Pending and retryable deliveries remain in SQLite and can be processed when the worker starts again. A forced termination such as `kill -9` can interrupt an active HTTP request, but the claim lease allows that delivery to become eligible again after expiry.

## Test coverage

The test suite uses isolated SQLite databases and mocked HTTP transports. It does not use the development database or contact real websites.

Focused tests cover:

- Missing, invalid, and revoked API keys.
- Tenant isolation.
- Invalid event fields and endpoint methods.
- Duplicate events.
- Atomic event and delivery creation.
- Successful webhook visits.
- Timeouts, network failures, `429`, and `5xx` responses.
- Permanent `4xx` failures.
- Exponential retry scheduling.
- Five-attempt termination.
- Claim-token protection.
- Expired-claim recovery.
- Outbox publication success.
- Queue publication failure and retry persistence.

Run the tests with:

```bash
.venv/bin/pytest
```
