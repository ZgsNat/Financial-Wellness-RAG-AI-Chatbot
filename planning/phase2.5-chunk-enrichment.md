# Phase 2.5 — Transaction Chunk Enrichment

> **Mục đích:** Cải thiện Precision@1 của transaction retrieval từ 0% lên mức cạnh tranh được với journal entries.  
> **Scope:** Chỉ thay đổi `_format_transaction()` trong `insight/rag/ingestion.py` — không đụng schema, không migrate DB, không thay đổi bất kỳ service nào khác.  
> **Không cần:** LLM mới, model mới, schema migration, Docker image mới.

---

## 1. Vấn đề được xác định qua eval_rag.ps1

### Kết quả đánh giá Phase 2 (baseline)

```
Corpus: 207 chunks  (transaction=117, journal_entry=50, mood_entry=40)

Precision@1   50%  (4/8 queries)
Precision@K   75%  (6/8 queries)
Keyword Hit  100%  (8/8 queries)

Similarity range: avg=0.646  min=0.562  max=0.716
```

### Pattern thất bại cụ thể

| Query | Expected | Got | Delta sim |
|---|---|---|---|
| "chi tiêu thực phẩm và ăn uống?" | `transaction` | `journal_entry` | journal 0.705 > tx ? |
| "Thu nhập và lương tháng 3?" | `transaction` | `journal_entry` | journal 0.629 > tx ? |
| "Chi tiêu mua sắm ra sao?" | `transaction` | `journal_entry` | journal 0.683 > tx ? |
| "Sức khỏe và tiền thuốc tháng này?" | `transaction` | `journal_entry` | journal 0.716 > tx ? |

**4/4 transaction queries** đều bị một `journal_entry` đứng đầu.

---

## 2. Root Cause Analysis

### Tại sao journal entry thắng?

Embedding similarity (cosine) đo **ngữ nghĩa chung** giữa query và chunk. Query dùng ngôn ngữ tự nhiên tiếng Việt. Journal entries cũng dùng ngôn ngữ tự nhiên tiếng Việt phong phú.

**Transaction chunk hiện tại (avg 41 chars):**
```
2026-03-01: expense 450,000 VND [food]
Bún bò buổi sáng
```
- Ngôn ngữ kỹ thuật có cấu trúc (`expense`, `[food]`, `VND`)
- Ngắn — BGE-M3 có ít token ngữ nghĩa để so khớp
- Thiếu từ khóa tiếng Việt khớp với cách user đặt câu hỏi

**Journal entry (avg 130 chars):**
```
[Journal 2026-04-09] Phân tích chi tiêu tháng này:
thực phẩm chiếm 40%, mua sắm 25%...
```
- Ngôn ngữ tự nhiên, phong phú ngữ nghĩa
- Dài 3× → nhiều token semantic hơn
- Chứa đúng từ khóa user hay hỏi: "chi tiêu", "thực phẩm", "mua sắm"

### Tại sao đây là vấn đề cần fix

Trong sản phẩm thực tế, user hỏi:
> "Tôi đã tiêu bao nhiêu cho ăn uống tháng này?"

LLM cần nhận được **số liệu transaction thực tế** (450,000 VND, food, ngày 01/03) chứ không phải một nhận định chung chung từ journal. Nếu chỉ nhận journal narratives mà không nhận raw transaction data, LLM có thể:
- Lấy số liệu sai (journal tổng hợp ước lượng, không phải exact amount)
- Không thể tính tổng chính xác
- Không phân biệt được category breakdown thực tế

---

## 3. Giải pháp: Semantic Text Enrichment

### Nguyên tắc thiết kế

1. **Không thêm thông tin giả** — chỉ diễn đạt lại thông tin sẵn có bằng ngôn ngữ tự nhiên hơn
2. **Bilingual labels** — mỗi category/type được đặt tên cả tiếng Anh lẫn tiếng Việt để khớp cả 2 cách query
3. **Repetition có chủ đích** — category label xuất hiện 2 lần (headline + taxonomy) vì BGE-M3 weight repetition positively
4. **Không thay đổi metadata** — metadata JSON giữ nguyên cấu trúc cho filter queries

### Template mới

```
{TYPE_LABEL} {CATEGORY_LABEL} ngày {date}: {amount_fmt} {currency}.
Ghi chú: {note}.
Giao dịch: {type}. Danh mục: {category_label}.
```

**Ví dụ cụ thể:**

| Trường | Giá trị |
|---|---|
| type | `expense` |
| category | `food` |
| amount | 450000 |
| date | 2026-03-01 |
| note | Bún bò buổi sáng |

**Cũ (41 chars):**
```
2026-03-01: expense 450,000 VND [food]
Bún bò buổi sáng
```

**Mới (~140 chars):**
```
Chi tiêu thực phẩm & ăn uống ngày 2026-03-01: 450,000 VND.
Ghi chú: Bún bò buổi sáng.
Giao dịch: chi tiêu. Danh mục: thực phẩm & ăn uống.
```

### Category label mapping (tiếng Việt)

| Category | Vietnamese label |
|---|---|
| `food` | thực phẩm & ăn uống |
| `shopping` | mua sắm |
| `transport` | di chuyển & phương tiện |
| `health` | sức khỏe & y tế |
| `entertainment` | giải trí |
| `education` | học tập & giáo dục |
| `utilities` | hóa đơn tiện ích |
| `other` | chi tiêu khác |

### Type label mapping

| Type | Vietnamese label |
|---|---|
| `expense` | Chi tiêu |
| `income` | Thu nhập |

---

## 4. Phạm vi code thay đổi

Chỉ **1 hàm** trong **1 file**:

```
backend/services/insight/src/insight/rag/ingestion.py
└── _format_transaction(payload)   ← SỬA
```

Không có gì khác thay đổi:
- ❌ Không thay đổi schema DB
- ❌ Không thay đổi retrieval logic
- ❌ Không thay đổi embedding model
- ❌ Không thay đổi context builder
- ❌ Không thay đổi chat router

---

## 5. Cách reindex

Vì `_upsert_chunks` dùng `ON CONFLICT (source_id, chunk_index) DO UPDATE`, chỉ cần:

1. Rebuild `insight` Docker image
2. Restart insight service
3. Re-publish các events — **hoặc** dùng re-ingestion script trực tiếp (seed data mới qua eval_rag.ps1)

Script `eval_rag.ps1` sẽ tự động tạo user mới + seed data mới → embedding mới với format mới.

---

## 6. Kỳ vọng sau khi apply

| Metric | Phase 2 baseline | Phase 2.5 target |
|---|---|---|
| Precision@1 | 50% (4/8) | ≥75% (6/8) |
| Precision@K | 75% (6/8) | ≥87% (7/8) |
| Keyword Hit | 100% (8/8) | 100% (8/8) |
| Avg similarity | 0.646 | ~0.65–0.72 (transaction sim tăng) |

Kỳ vọng transaction queries (TX-FOOD, TX-INCOME, TX-SHOP, TX-HEALTH) sẽ cạnh tranh được với journal entries nhờ text phong phú hơn.

---

## 7. Không nằm trong scope Phase 2.5

| Item | Lý do hoãn |
|---|---|
| Semantic chunking với LLM | Tăng Gemini quota consumption dramatically |
| Hybrid search (BM25 + vector) | Cần thay đổi schema + retrieval logic |
| Re-rank với cross-encoder | Cần load thêm model |
| Source-type boosting (γ weighting) | Cần thay đổi retrieval query |
| Query expansion | Tăng latency, cần LLM |

Phase 2.5 chỉ là **1 hàm, 1 file, không cần migration** — tối thiểu rủi ro, tối đa tác động.
