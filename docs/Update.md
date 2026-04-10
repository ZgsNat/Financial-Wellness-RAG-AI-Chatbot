# FinWell — Cập nhật ngày 10/04/2026

## 🐛 Bugs đã fix

### 1. Transaction mất `note` khi publish lên RabbitMQ
**Vấn đề**: `TransactionCreatedEvent` (schema dùng để publish message qua RabbitMQ) thiếu field `note`. Khi transaction được tạo, message gửi sang insight service không có ghi chú → chunk được index chỉ có ngày/loại/số tiền, không có nội dung mô tả.

**Ảnh hưởng**: AI không thể tìm thấy transaction dù đã nhập ghi chú (vd: "highland sáng vì quá buồn ngủ").

**Fix**: Thêm `note: str | None = None` vào `TransactionCreatedEvent` và pass `note=transaction.note` trong publisher.

---

### 2. Transaction bị "úp bô" bởi Journal entries trong RAG retrieval
**Vấn đề**: Hệ thống chỉ có 1 query duy nhất lấy top-8 chunks từ tất cả loại nguồn (transaction, journal, mood). Journal entries dài ~200 tokens → score hybrid cao hơn → lấp đầy cả 8 slot → transaction ngắn bị đẩy ra ngoài hoàn toàn.

**Ảnh hưởng**: Hỏi về chi tiêu cụ thể → AI trả lời "không có thông tin" dù transaction đã được ghi, đã sync.

**Fix**: **Multi-source retrieval** — tách thành 2 query riêng biệt:
- 4 slot dành riêng cho `transaction`
- 8 slot cho `journal_entry` + `mood_entry`
- Merge lại → transaction luôn xuất hiện trong context, bất kể score so sánh.

---

## ✨ Tính năng mới

### 3. Endpoint Re-index (`POST /insights/reindex`)
Cho phép re-embed và cập nhật lại chunk trong DB cho một document cụ thể. Dùng khi transaction/journal cũ đã bị index thiếu data.

**Sử dụng**: Authenticated — user chỉ có thể re-index document của chính mình.

---

### 4. Nút "Sync to AI" trên trang Transactions
Mỗi dòng transaction có thêm nút 🔄 (màu xanh). Click để re-index transaction đó vào hệ thống AI ngay lập tức, không cần tạo lại transaction.

**Khi nào dùng**: Khi transaction cũ (tạo trước bản fix hôm nay) chưa có note trong index.

---

### 5. Per-user Gemini API Key (từ session trước, deploy hôm nay)
Mỗi người dùng có thể nhập Gemini API key cá nhân, lưu trong Redis. AI chat sẽ dùng key của user thay vì key chung của hệ thống → không còn tranh quota.

**UI**: Nút 🔑 góc trên phải trang Chat → nhập key → Save. Key được hiển thị dạng masked (`AIza...j5D0`).

---

## 🏗️ Cải tiến kiến trúc

### Retrieval pipeline: Single-pool → Multi-source
```
Trước:  [top-8 từ tất cả]
                → journal chiếm 8/8 → transaction bị loại

Sau:    [top-4 transaction] + [top-8 journal/mood]
                → merge → AI luôn thấy cả 2 loại
```

### RabbitMQ event contract: thêm `note`
```
TransactionCreatedEvent (trước):  date, amount, type, category
TransactionCreatedEvent (sau):    date, amount, type, category, note ✅
```

---

## 📊 Kết quả kiểm chứng
Câu hỏi *"Ngày 10/04 tôi mua cà phê Highland, có phải do cảm xúc không?"*:

| Trước fix | Sau fix |
|---|---|
| Sources: 8 Journal entries | Sources: 4 Giao dịch + Journal entries |
| Trả lời: "Không có thông tin về Highland" | Trả lời: "Ghi chú của bạn là 'quá buồn ngủ' — nhu cầu thể chất, không phải emotional spending trực tiếp" |

---

## 📁 Files thay đổi

| File | Thay đổi |
|---|---|
| `backend/services/transaction/src/transaction/schemas/transaction.py` | Thêm `note` vào `TransactionCreatedEvent` |
| `backend/services/transaction/src/transaction/messaging/publisher.py` | Pass `note=transaction.note` khi publish |
| `backend/services/insight/src/insight/rag/retrieval.py` | Thêm param `source_types` để filter theo loại |
| `backend/services/insight/src/insight/routers/chat.py` | Multi-source retrieval (2 query riêng) |
| `backend/services/insight/src/insight/routers/insight.py` | Thêm `POST /insights/reindex` endpoint |
| `frontend/services/insight.ts` | Thêm `insightReindexApi` |
| `frontend/app/(app)/transactions/page.tsx` | Thêm nút 🔄 Sync to AI per row |
