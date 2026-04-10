# Financial Wellness × Mental Health — Phase 1

> A microservices backend that links spending behaviour with emotional wellbeing.  
> Phase 1 ships the full event-driven pipeline with rule-based analysis as a placeholder for the Phase 2 LLM/RAG engine.

---

## Architecture at a glance

```
Client (Next.js)
  └─▶ Kong :8000  (JWT RS256 verify → inject X-Authenticated-Userid)
        ├─▶ identity-service  :8010  (register / login / JWKS)
        ├─▶ transaction-service :8011 (CRUD + publish → RabbitMQ)
        ├─▶ journal-service   :8012  (entries + moods + publish → RabbitMQ)
        ├─▶ insight-service   :8013  (consume events, upsert insight)
        └─▶ notification-service :8014 (consume events, create alerts)

RabbitMQ (fanout)
  transactions.events ──▶ insight.transaction.created   (insight-service)
                      └──▶ notification.transaction.created (notification-service)
  journal.events      ──▶ insight.journal.created        (insight-service)

Redis  — idempotency guard (24 h TTL per processed event)
Jaeger — distributed tracing (W3C traceparent across HTTP + AMQP)
```

Each service owns its own Postgres database (`identity_db`, `transaction_db`, `journal_db`, `insight_db`, `notification_db`).  
Cross-service communication is **events only** — no cross-DB queries, no service-to-service HTTP in Phase 1.

---

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Docker Desktop | ≥ 4.x | Runs all containers |
| `openssl` | any | Generates RSA key pair (usually bundled with Git for Windows) |
| `python3` | ≥ 3.8 | `setup.sh` uses it to compute KID and write `kong/kong.yml` |
| `bash` | any | `setup.sh` and `gen_keys.sh` are bash scripts |

On **Windows** use Git Bash, WSL2, or any bash environment that has `openssl` and `python3` on `$PATH`.

---

## Quick start

```bash
# 1. Enter the backend directory
cd backend

# 2. One-time setup: generate RSA key pair + write kong/kong.yml with consumer credential
bash scripts/setup.sh

# 3. Start everything (first run builds 5 images — takes a few minutes)
docker compose up --build
```

That's it. The stack is healthy when you see:

```
kong          | ...Kong is ready...
identity      | ...Application startup complete...
transaction   | ...rabbitmq_connected...
journal       | ...rabbitmq_connected...
insight       | ...insight_consumers_started...
notification  | ...notification_consumers_started...
```

### Why `setup.sh`?

Kong's `jwt` plugin verifies RS256 tokens against a pre-registered consumer credential (RSA public key + KID).  
The key pair is generated fresh on every `setup.sh` run so the KID is not known ahead of time.  
`setup.sh` generates the keys, computes the KID (SHA-256 of public key content, first 8 hex chars), and rewrites `kong/kong.yml` with the matching consumer credential.  
It also copies `.env.example → .env` on first run.

---

## Ports

| Port | Service | Notes |
|------|---------|-------|
| **8000** | Kong proxy | **Only entry point for clients** |
| 8001 | Kong Admin API | Read-only in DB-less mode |
| 8010 | identity-service | Direct access — dev/debug only |
| 8011 | transaction-service | Direct access — dev/debug only |
| 8012 | journal-service | Direct access — dev/debug only |
| 8013 | insight-service | Direct access — dev/debug only |
| 8014 | notification-service | Direct access — dev/debug only |
| 5432 | PostgreSQL | 5 databases on one instance |
| 5672 | RabbitMQ AMQP | |
| 15672 | RabbitMQ Management UI | `fw` / `fw_secret` |
| 6379 | Redis | |
| 16686 | **Jaeger UI** | Full distributed traces |
| 4318 | OTLP HTTP collector | Used by all services + Kong |

---

## Happy Path A — Transaction flow

### 1. Register + login

```bash
# Register
curl -s -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123","full_name":"Alice"}' | jq .

# Login → copy the access_token
curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","password":"secret123"}' | jq .

export TOKEN="<paste access_token here>"
```

### 2. Create a transaction (triggers event pipeline)

```bash
curl -s -X POST http://localhost:8000/transactions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "amount": 750000,
    "currency": "VND",
    "type": "expense",
    "category": "shopping",
    "note": "Bought a new book after a stressful meeting",
    "transaction_date": "2026-04-08"
  }' | jq .
```

This causes **two alerts** to be generated (amount > 500 000 VND **and** category = shopping).

### 3. Verify the pipeline fired

```bash
# Spending insight UPSERTed
curl -s http://localhost:8000/insights \
  -H "Authorization: Bearer $TOKEN" | jq .

# Alerts created
curl -s http://localhost:8000/notifications \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### 4. View the trace end-to-end

Open **http://localhost:16686**, search for service `kong-gateway`, pick the `POST /transactions` trace.  
You will see Kong → transaction-service as one trace, and then two child spans for insight-service and notification-service consumers that share the same `trace_id`.

---

## Happy Path B — Journal / mood flow

```bash
# Log mood (score 1–5)
curl -s -X POST http://localhost:8000/journal/moods \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"score": 2, "note": "Feeling low after today"}' | jq .

# Write a journal entry
curl -s -X POST http://localhost:8000/journal/entries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Rough day. Browsed Shopee for comfort — ended up buying 2 figures."}' | jq .

# Mood-spending insight (Phase 1 placeholder, Phase 2 = LLM correlation)
curl -s http://localhost:8000/insights \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## Development without Kong

All services expose a `DEBUG` mode: if `DEBUG=true` in the service environment, the auth dependency accepts a `X-Dev-User-Id: <uuid>` header directly instead of requiring Kong to inject `X-Authenticated-Userid`.

```bash
# Hit transaction-service directly (bypass Kong)
curl -s -X POST http://localhost:8011/transactions \
  -H "X-Dev-User-Id: 00000000-0000-0000-0000-000000000001" \
  -H "Content-Type: application/json" \
  -d '{"amount":100000,"currency":"VND","type":"expense","category":"food","transaction_date":"2026-04-08"}' | jq .
```

> **Note:** `DEBUG=true` is not set in the compose file by default. For local testing, set it temporarily in the relevant service environment.

---

## Running a single service in isolation

```bash
cd services/transaction
cp .env.example .env          # edit DATABASE_URL / RABBITMQ_URL to point to localhost
uv run uvicorn transaction.main:app --reload --port 8011
```

Each service has its own `pyproject.toml` with pinned dependencies and can be started independently.

---

## Re-seeding (full reset)

```bash
docker compose down -v          # destroys all volumes (data gone)
bash scripts/setup.sh           # re-generate keys
docker compose up --build
```

---

## Troubleshooting

### Kong returns `401 Unauthorized` on all protected routes

Most likely cause: `setup.sh` was not run, or the key pair was regenerated **after** `docker compose up`.

```bash
bash scripts/setup.sh           # regenerates kong/kong.yml with matching consumer
docker compose restart kong     # picks up the new config without full restart
```

### Kong health fails at startup

Kong starts only after all 5 services are up (`depends_on`). If a migration fails the service won't start.

```bash
docker compose logs identity-migrator   # check migration output
docker compose logs postgres            # check DB errors
```

### RabbitMQ consumer not connecting

```bash
docker compose logs insight | grep -E "consumer|rabbitmq"
```

The consumers use `connect_robust` which retries automatically. If rabbitmq is still starting, the service will keep retrying until it connects.

### pgvector extension

The insight-service migration runs `CREATE EXTENSION IF NOT EXISTS vector` inside a `DO $$ BEGIN … EXCEPTION WHEN OTHERS THEN … END $$;` block so it is **safe on `postgres:16-alpine`** (which ships without pgvector).  
For Phase 2, switch the Postgres image in `docker-compose.yaml` to `pgvector/pgvector:pg16` and the extension will be available.

---

## What is not implemented in Phase 1

| Feature | Status | Phase |
|---------|--------|-------|
| Spending pattern analysis (real) | Stub rule-based text | Phase 2 (LLM) |
| Mood-spending correlation | Placeholder text | Phase 2 (LLM + RAG) |
| Journal content embedding | Not yet | Phase 2 (pgvector) |
| Push notifications (WebSocket / FCM) | Not yet | Phase 2 |
| Budget management | Not yet | Phase 2 |
| Refresh tokens / token revocation | Not yet | Phase 2 |

---

## Data model summary

```
identity_db.users
  id (uuid) | email (unique) | hashed_password | full_name | is_active | created_at

transaction_db.transactions
  id | user_id | amount (Numeric 15,2) | currency | type (expense/income)
  category | note (text) | transaction_date | created_at
  Index: (user_id, transaction_date)

journal_db.mood_entries
  id | user_id | score (1-5) | note (text) | created_at

journal_db.journal_entries
  id | user_id | content (text ≤ 10k) | word_count | created_at | updated_at

insight_db.insights
  id | user_id | insight_type | summary (text) | detail (text/JSON)
  source_event_id | generated_at | updated_at
  UniqueConstraint: (user_id, insight_type)   ← one record per type, always upserted

notification_db.alerts
  id | user_id | alert_type | title | body (text) | is_read
  source_event_id | created_at                   ← append-only
```

Redis (ephemeral):
```
processed:insight.transaction:<event_id>       → "1"  TTL 24 h
processed:insight.journal:<event_id>           → "1"  TTL 24 h
processed:notification.transaction:<event_id>  → "1"  TTL 24 h
```
