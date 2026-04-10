Để kiểm tra đầy đủ, tôi đọc tất cả routers: 

Searched for files matching `**/routers/*.py`, 11 matches

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/identity/src/identity/routers/auth.py)

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/transaction/src/transaction/routers/transaction.py)

Compacted conversation

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/insight/src/insight/routers/chat.py)

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/journal/src/journal/routers/journal.py)

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/insight/src/insight/routers/insight.py)

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/notification/src/notification/routers/alert.py)

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/kong/kong.yml#1-1), lines 1 to 80

Now let me quickly check the key schemas for request/response bodies:  

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/journal/src/journal/schemas/journal.py)

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/transaction/src/transaction/schemas/transaction.py)

Searched for regex `class TransactionType|class Category|class MoodScore|class InsightType|class AlertType` (`**/models/*.py`), 5 results

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/identity/src/identity/schemas/auth.py#1-1), lines 1 to 50

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/transaction/src/transaction/models/transaction.py#1-1), lines 1 to 50

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/notification/src/notification/models/alert.py#1-1), lines 1 to 40

Read [](file:///e%3A/FolderCode/project/Financial%20Wellness%20-%20Mental%20Health/backend/services/insight/src/insight/models/insight.py#1-1), lines 1 to 35

Now I have everything. Here's the complete API inventory for frontend handoff:

---

## API Inventory — Sẵn sàng cho Frontend

**Base URL:** `http://localhost:8000` (qua Kong gateway)  
**Auth:** Bearer JWT — thêm header `Authorization: Bearer <access_token>` cho tất cả protected endpoints

---

### Auth (`/auth/*`) — Public, không cần token

| Method | Path | Request Body | Response |
|--------|------|-------------|----------|
| POST | `/auth/register` | `{ email, password, full_name? }` | `{ id, email, full_name, is_active, created_at }` 201 |
| POST | `/auth/login` | `{ email, password }` | `{ access_token, token_type: "bearer", expires_in }` |
| GET | `/auth/.well-known/jwks.json` | — | JWKS public key |

---

### Transactions (`/transactions/*`) — JWT required

| Method | Path | Query / Body | Response |
|--------|------|-------------|----------|
| POST | `/transactions` | `{ amount, currency?, type?, category, note?, transaction_date }` | `TransactionResponse` 201 |
| GET | `/transactions` | `?page&page_size&date_from&date_to` | `{ items[], total, page, page_size }` |
| GET | `/transactions/{id}` | — | `TransactionResponse` |
| PATCH | `/transactions/{id}` | `{ amount?, category?, note?, transaction_date? }` | `TransactionResponse` |
| DELETE | `/transactions/{id}` | — | 204 |

**Enums:**
- `type`: `"expense"` | `"income"` (default: `"expense"`)
- `category`: `"food"` | `"shopping"` | `"entertainment"` | `"transport"` | `"health"` | `"education"` | `"utilities"` | `"other"`
- `currency` default: `"VND"`

---

### Journal (`/journal/*`) — JWT required

| Method | Path | Query / Body | Response |
|--------|------|-------------|----------|
| POST | `/journal/moods` | `{ score: 1-5, note? }` | `{ id, user_id, score, note, created_at }` 201 |
| GET | `/journal/moods` | `?page&page_size` | `MoodEntryResponse[]` |
| POST | `/journal/entries` | `{ content }` (1–10000 chars) | `{ id, user_id, content, word_count, created_at, updated_at }` 201 |
| GET | `/journal/entries` | `?page&page_size` | `{ items[], total, page, page_size }` |
| GET | `/journal/entries/{id}` | — | `JournalEntryResponse` |
| PATCH | `/journal/entries/{id}` | `{ content }` | `JournalEntryResponse` |
| DELETE | `/journal/entries/{id}` | — | 204 |

---

### Insights & Chat (`/insights/*`) — JWT required

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | `/insights` | — | `InsightResponse[]` |
| POST | `/insights/chat` | `{ question: string, stream?: true }` | **SSE stream**: `data: {"delta":"..."}` → `data: {"done":true,"sources":[...]}` |

**Rate limit chat:** 10 req/min  
**InsightType values:** `spending_pattern`, `mood_spending`, `budget_summary`, `wellness_suggestion`

**SSE parsing cho `/insights/chat`:**
```js
// Mỗi event: data: <json>\n\n
// { delta: "text chunk" }  — append to UI
// { done: true, sources: [...] }  — render sources
// { error: "..." }  — show error
```

---

### Notifications (`/notifications/*`) — JWT required

| Method | Path | Query / Body | Response |
|--------|------|-------------|----------|
| GET | `/notifications` | `?unread_only=false&page&page_size` | `{ items[], total, unread_count }` |
| PATCH | `/notifications/{id}/read` | — | 204 |

**AlertType values:** `spending_spike`, `category_overload`, `mood_spending_warning`, `budget_exceeded`, `wellness_tip`

---

### Tổng kết

| Service | Endpoints | Auth |
|---------|-----------|------|
| Auth | 3 | Public |
| Transaction | 5 | JWT |
| Journal | 7 | JWT |
| Insight | 2 | JWT |
| Notification | 2 | JWT |
| **Total** | **19** | — |

**Tất cả 19 endpoints đã sẵn sàng.** Backend đủ để bắt đầu xây frontend — không thiếu endpoint nào cho core flows: auth → log transaction → log mood/journal → view insights/chat → view notifications. 

