## Khuyến nghị Frontend Stack

**Mức độ ưu tiên: "sài được + đẹp tự động"** — không cần viết CSS, components có sẵn.

---

### Stack đề xuất

| Package | Mục đích | Ghi chú |
|---------|---------|---------|
| **Next.js 15** (App Router) | Framework | Đã quyết định |
| **TypeScript** | Type safety | Bắt lỗi sớm khi gọi API |
| **Tailwind CSS v4** | Styling | Không viết CSS file |
| **shadcn/ui** | UI Components | Button, Card, Dialog... đẹp sẵn |
| **TanStack Query v5** | API state | Auto loading/error/cache — không tự quản lý state phức tạp |
| **Zustand** | Global state | Chỉ dùng cho auth token |
| **Recharts** | Biểu đồ | Chi tiêu theo category, mood trend |
| **lucide-react** | Icons | Đã tích hợp sẵn với shadcn |
| **date-fns** | Format ngày | `format(date, "dd/MM/yyyy")` |

---

### Màu sắc — Theme gợi ý

App kết hợp **tài chính + sức khỏe tâm thần** → nên calm, không alarm người dùng:

```
Primary:   Teal/Emerald   (#10b981) → financial, growth
Secondary: Violet         (#8b5cf6) → mental wellness, calm
Warning:   Amber          (#f59e0b) → alerts, spending spike
Danger:    Rose           (#f43f5e) → budget exceeded
Background: Slate-50      (#f8fafc) → light, clean
```

shadcn/ui hỗ trợ theme bằng CSS variables — chỉ đổi 1 file là toàn bộ app đổi màu.

---

### Cấu trúc pages (App Router)

```
app/
  (auth)/
    login/page.tsx
    register/page.tsx
  (app)/                    ← protected, có sidebar
    layout.tsx              ← check JWT, redirect nếu hết hạn
    dashboard/page.tsx      ← overview cards
    transactions/
      page.tsx              ← list + filter
      new/page.tsx
    journal/
      page.tsx              ← entries list + mood log
    chat/page.tsx           ← AI chat (SSE stream)
    notifications/page.tsx
```

---

### 3 điểm kỹ thuật cần lưu ý với backend này

**1. Lưu JWT và tự gắn vào request:**
```ts
// lib/api.ts — axios instance
axios.defaults.headers.common["Authorization"] = `Bearer ${token}`;
```

**2. SSE cho `/insights/chat` — không dùng fetch thông thường:**
```ts
const res = await fetch("/insights/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
  body: JSON.stringify({ question }),
});
const reader = res.body!.getReader();
// đọc từng chunk và append vào UI
```
→ `EventSource` chuẩn không hỗ trợ POST + custom header nên phải dùng `fetch` + `ReadableStream`.

**3. Notification badge — poll mỗi 30s:**
```ts
// TanStack Query
useQuery({ queryKey: ["notifications"], queryFn: fetchNotifications, refetchInterval: 30_000 });
// unread_count từ response → hiển thị badge trên icon
```

---

### Dashboard layout gợi ý

```
┌─────────────────────────────────────────────────────┐
│  💚 FinWell    [Transactions] [Journal] [Chat] [🔔2] │  ← navbar
├──────────┬──────────────────────────────────────────┤
│          │  This Month                              │
│ Sidebar  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│          │  │ Spent    │ │ Income   │ │ Mood avg │ │
│ Quick    │  │ 2.4M VND │ │ 8M VND  │ │ 😊 3.8/5 │ │
│ links    │  └──────────┘ └──────────┘ └──────────┘ │
│          │                                          │
│          │  [Spending by Category — Pie chart]      │
│          │  [Recent Transactions — table]           │
│          │  [Latest Insight card]                   │
└──────────┴──────────────────────────────────────────┘
```

---

### Bootstrap nhanh nhất

```bash
npx create-next-app@latest frontend --typescript --tailwind --app
cd frontend
npx shadcn@latest init          # chọn theme "zinc" hoặc "slate"
npx shadcn@latest add button card dialog input table badge
npm install @tanstack/react-query zustand axios recharts date-fns lucide-react
```

Xong phần setup, tôi có thể generate từng page khi bạn sẵn sàng bắt đầu.