# Financial Wellness × Mental Health

> A full-stack application that links spending behaviour with emotional wellbeing, powered by a RAG AI chatbot using hybrid search.

---

## Overview

This project is a microservices-based platform where users can:

- Track **transactions** and **journal/mood entries**
- Receive AI-generated **insights** connecting their finances and mental state
- Chat with an **AI assistant** (RAG pipeline — Gemini + BGE-M3 embeddings + hybrid BM25/vector search)
- Get **smart notifications** when spending spikes are detected

---

## Architecture

```
Client (Next.js :3000)
  └─▶ Kong API Gateway :8000  (JWT RS256 auth)
        ├─▶ identity-service    :8010  — register / login / JWKS
        ├─▶ transaction-service :8011  — CRUD + RabbitMQ events
        ├─▶ journal-service     :8012  — journal entries + moods
        ├─▶ insight-service     :8013  — RAG chat + hybrid search
        └─▶ notification-service:8014  — spend-spike alerts

Event bus (RabbitMQ fanout)
  transactions.events ──▶ insight-service  (embed + index)
                      └──▶ notification-service  (spike detection)
  journal.events      ──▶ insight-service  (embed + index)

Infrastructure
  PostgreSQL (pgvector) — 5 isolated databases + vector + FTS columns
  Redis                 — idempotency guard (24 h TTL)
  Jaeger                — distributed tracing (W3C traceparent)
  Embedding service     — BGE-M3 via sentence-transformers
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query |
| API Gateway | Kong 3.7 (DB-less, JWT RS256) |
| Backend services | Python (FastAPI), SQLAlchemy, Alembic, aio-pika |
| AI / RAG | Google Gemini, BGE-M3 embeddings, hybrid BM25 + pgvector search |
| Database | PostgreSQL 16 + pgvector |
| Message broker | RabbitMQ 3.13 |
| Cache | Redis 7 |
| Tracing | Jaeger (OpenTelemetry) |
| Containerisation | Docker Compose |

---

## Repository Structure

```
.
├── backend/              # All microservices + infrastructure
│   ├── docker-compose.yaml
│   ├── kong/kong.yml     # Kong declarative config (auto-generated)
│   ├── scripts/          # Setup, seeding, and test scripts
│   └── services/
│       ├── identity/     — Auth service (JWT RS256)
│       ├── transaction/  — Transaction CRUD
│       ├── journal/      — Journal & mood entries
│       ├── insight/      — RAG pipeline + chat endpoint
│       ├── notification/ — Spend-spike alert engine
│       └── embedding/    — BGE-M3 embedding microservice
├── frontend/             # Next.js web application
│   ├── app/
│   │   ├── (app)/        — Protected routes (dashboard, chat, journal…)
│   │   ├── login/
│   │   └── register/
│   ├── components/       — Shared UI components (shadcn/ui)
│   ├── services/         — API client functions
│   └── store/            — Auth state (Zustand)
├── docs/                 # Additional documentation
└── planning/             # Architecture planning notes
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Docker Desktop | ≥ 4.x | Run all backend containers |
| Node.js | ≥ 20 | Frontend dev server |
| npm | ≥ 10 | Frontend package manager |
| `bash` + `openssl` + `python3` | any | One-time key generation (Git Bash or WSL2 on Windows) |

---

## Quick Start

### 1 — Backend

```bash
cd backend

# Generate RSA key pair and write Kong config (one-time)
bash scripts/setup.sh

# Start all services (first run builds images — takes a few minutes)
docker compose up --build
```

The stack is ready when you see:
```
kong          | ...Kong is ready...
identity      | ...Application startup complete...
insight       | ...hybrid_search_enabled...
```

### 2 — Frontend

```bash
cd frontend

npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## Service Ports

| Port | Service |
|------|---------|
| **3000** | Frontend (Next.js) |
| **8000** | Kong API Gateway — **primary client entry point** |
| 8001 | Kong Admin API |
| 8010 | identity-service (direct/debug) |
| 8011 | transaction-service (direct/debug) |
| 8012 | journal-service (direct/debug) |
| 8013 | insight-service (direct/debug) |
| 8014 | notification-service (direct/debug) |
| 5432 | PostgreSQL |
| 5672 | RabbitMQ AMQP |
| 15672 | RabbitMQ Management UI (`fw` / `fw_secret`) |
| 6379 | Redis |
| 16686 | Jaeger Tracing UI |

---

## RAG Pipeline (Phase 2 → 3)

The AI chat feature uses a multi-phase RAG pipeline:

1. **Ingestion** — transactions and journal entries are published to RabbitMQ → consumed by `insight-service` → chunked, enriched, and embedded with BGE-M3 → stored in PostgreSQL with `pgvector` + FTS columns.

2. **Hybrid Search (Phase 3)** — queries run both:
   - **Vector search** (cosine similarity via pgvector) — understands synonyms and intent
   - **BM25 lexical search** (PostgreSQL `ts_rank`) — exact keyword matching
   - Combined score: `0.6 × vector + 0.4 × BM25`

3. **Generation** — top-k retrieved chunks are passed to Google Gemini as context to generate a grounded, data-backed response.

---

## Environment Variables

Backend secrets live in `backend/.env` (auto-created from `.env.example` by `setup.sh`).

Frontend — create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Development Notes

- All backend services use **Alembic** for database migrations (run automatically on startup).
- Kong uses **DB-less declarative mode** — `kong/kong.yml` is regenerated by `setup.sh` with a fresh RSA key pair each time.
- The `secrets/` directory (RSA keys) is excluded from version control via `.gitignore`.
