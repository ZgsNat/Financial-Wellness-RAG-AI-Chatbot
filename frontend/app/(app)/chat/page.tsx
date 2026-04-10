"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Lightbulb, ChevronDown, ChevronUp, Key } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { streamChat, insightSettingsApi } from "@/services/insight";
import { journalApi, JournalResponse } from "@/services/journal";
import { transactionApi, TransactionResponse } from "@/services/transaction";
import { useAuthStore } from "@/store/auth";
import { cn } from "@/lib/utils";

type SourceDetail =
  | { kind: "journal"; data: JournalResponse }
  | { kind: "transaction"; data: TransactionResponse }
  | { kind: "loading" }
  | { kind: "error"; message: string };

const CATEGORY_LABEL: Record<string, string> = {
  food: "Ăn uống", shopping: "Mua sắm", entertainment: "Giải trí",
  transport: "Di chuyển", health: "Sức khỏe", education: "Giáo dục",
  utilities: "Tiện ích", other: "Khác",
};

const SUGGESTED_QUESTIONS = [
  { emoji: "💸", text: "Tháng này tôi đã chi tiêu tổng cộng bao nhiêu tiền?" },
  { emoji: "🍔", text: "Tôi chi bao nhiêu cho ăn uống trong tháng 3?" },
  { emoji: "📊", text: "Phân tích chi tiêu của tôi theo từng danh mục" },
  { emoji: "😰", text: "Tài chính có ảnh hưởng đến tâm trạng của tôi không?" },
  { emoji: "🛍️", text: "Danh mục nào tôi đang chi tiêu nhiều nhất?" },
  { emoji: "📈", text: "Thu nhập và chi tiêu tháng 3 của tôi như thế nào?" },
  { emoji: "🎯", text: "Tôi có đang chi tiêu vượt ngân sách không?" },
  { emoji: "💡", text: "Gợi ý cách tiết kiệm tiền hiệu quả cho tôi" },
  { emoji: "😊", text: "Tâm trạng của tôi trong thời gian gần đây như thế nào?" },
  { emoji: "💰", text: "Làm thế nào để cải thiện sức khỏe tài chính của tôi?" },
];

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: unknown[];
  streaming?: boolean;
}

export default function ChatPage() {
  const token = useAuthStore((s) => s.token);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [sourceDetail, setSourceDetail] = useState<SourceDetail | null>(null);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [keyOpen, setKeyOpen] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [maskedKey, setMaskedKey] = useState<string | null>(null);
  const [keySaving, setKeySaving] = useState(false);

  useEffect(() => {
    insightSettingsApi.get().then((r) => setMaskedKey(r.masked_key)).catch(() => {});
  }, []);

  async function saveApiKey() {
    setKeySaving(true);
    try {
      const r = await insightSettingsApi.save(keyInput);
      setMaskedKey(r.masked_key);
      setKeyInput("");
      setKeyOpen(false);
    } finally {
      setKeySaving(false);
    }
  }

  async function openSource(type: string, id: string) {
    setSourceDetail({ kind: "loading" });
    setSourceOpen(true);
    try {
      if (type === "journal_entry" || type === "mood_entry") {
        const data = await journalApi.getEntry(id);
        setSourceDetail({ kind: "journal", data });
      } else if (type === "transaction") {
        const data = await transactionApi.get(id);
        setSourceDetail({ kind: "transaction", data });
      } else {
        setSourceDetail({ kind: "error", message: "Loại nguồn không hỗ trợ." });
      }
    } catch {
      setSourceDetail({ kind: "error", message: "Không thể tải dữ liệu. Vui lòng thử lại." });
    }
  }

  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "assistant",
      content:
        "Hello! I'm your FinWell AI assistant. Ask me anything about your financial and mental wellness — spending patterns, budget tips, mood trends, or general advice.",
    },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function handleSend() {
    if (!input.trim() || streaming || !token) return;
    const question = input.trim();
    setInput("");

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: question };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = { id: assistantId, role: "assistant", content: "", streaming: true };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);

    await streamChat(
      question,
      token,
      (delta) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + delta } : m
          )
        );
      },
      (sources) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false, sources } : m
          )
        );
        setStreaming(false);
      },
      (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${err}`, streaming: false }
              : m
          )
        );
        setStreaming(false);
      }
    );
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  async function handleSuggest(question: string) {
    setShowSuggestions(false);
    if (streaming || !token) return;
    setInput("");

    const userMsg: Message = { id: crypto.randomUUID(), role: "user", content: question };
    const assistantId = crypto.randomUUID();
    const assistantMsg: Message = { id: assistantId, role: "assistant", content: "", streaming: true };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);

    await streamChat(
      question,
      token,
      (delta) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + delta } : m
          )
        );
      },
      (sources) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, streaming: false, sources } : m
          )
        );
        setStreaming(false);
      },
      (err) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `Error: ${err}`, streaming: false }
              : m
          )
        );
        setStreaming(false);
      }
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)]">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">AI Chat</h1>
          <p className="text-sm text-muted-foreground">
            Ask about your finances and wellness. Rate limit: 10 messages/min.
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className={cn("gap-1.5", maskedKey && "border-emerald-400 text-emerald-700")}
          onClick={() => setKeyOpen(true)}
        >
          <Key className="h-3.5 w-3.5" />
          {maskedKey ? maskedKey : "Set API Key"}
        </Button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={cn("flex gap-3", msg.role === "user" ? "justify-end" : "justify-start")}
          >
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-full bg-violet-100 flex items-center justify-center shrink-0 mt-1">
                <Bot className="h-4 w-4 text-violet-600" />
              </div>
            )}
            <div
              className={cn(
                "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-emerald-600 text-white rounded-tr-sm"
                  : "bg-white border rounded-tl-sm"
              )}
            >
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.streaming && !msg.content && (
                <div className="space-y-1.5 mt-1">
                  <Skeleton className="h-3 w-40" />
                  <Skeleton className="h-3 w-32" />
                </div>
              )}
              {msg.streaming && msg.content && (
                <span className="inline-block w-1.5 h-4 bg-violet-400 animate-pulse ml-0.5 rounded" />
              )}
              {msg.sources && (msg.sources as unknown[]).length > 0 && (
                <div className="mt-2 pt-2 border-t border-slate-200 space-y-1">
                  <p className="text-xs font-medium text-muted-foreground mb-1">Nguồn tham khảo</p>
                  {(() => {
                    const sources = msg.sources as { source_type: string; source_id: string; similarity: number }[];
                    const typeConfig: Record<string, { label: string; emoji: string }> = {
                      transaction: { label: "Giao dịch", emoji: "💳" },
                      journal_entry: { label: "Nhật ký", emoji: "📓" },
                      mood_entry: { label: "Tâm trạng", emoji: "😊" },
                    };
                    return sources.map((s) => {
                      const cfg = typeConfig[s.source_type] ?? { label: s.source_type, emoji: "📄" };
                      const shortId = s.source_id.slice(0, 8);
                      return (
                        <button
                          key={s.source_id}
                          onClick={() => openSource(s.source_type, s.source_id)}
                          className="flex items-center gap-1.5 text-xs text-violet-600 hover:text-violet-800 hover:underline text-left"
                        >
                          <span>{cfg.emoji}</span>
                          <span>{cfg.label} #{shortId}…</span>
                          <span className="text-slate-400">({Math.round(s.similarity * 100)}% phù hợp)</span>
                        </button>
                      );
                    });
                  })()}
                </div>
              )}
            </div>
            {msg.role === "user" && (
              <div className="w-8 h-8 rounded-full bg-emerald-100 flex items-center justify-center shrink-0 mt-1">
                <User className="h-4 w-4 text-emerald-600" />
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <Card className="mt-4 p-3">
        {/* Suggestion popup */}
        {showSuggestions && (
          <div className="mb-3 grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-60 overflow-y-auto">
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                onClick={() => handleSuggest(q.text)}
                disabled={streaming}
                className="flex items-start gap-2 text-left rounded-xl border border-slate-200 bg-slate-50 hover:bg-violet-50 hover:border-violet-300 px-3 py-2 text-sm text-slate-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <span className="text-base shrink-0">{q.emoji}</span>
                <span className="leading-snug">{q.text}</span>
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-2 items-end">
          <Textarea
            placeholder="Ask about your spending, mood trends, or financial advice… (Enter to send)"
            value={input}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            className="resize-none border-0 focus-visible:ring-0 p-0 shadow-none"
            disabled={streaming}
          />
          <Button
            size="icon"
            variant="outline"
            className={cn("shrink-0", showSuggestions && "bg-violet-50 border-violet-300 text-violet-600")}
            onClick={() => setShowSuggestions((v) => !v)}
            title="Gợi ý câu hỏi"
          >
            {showSuggestions ? <ChevronDown className="h-4 w-4" /> : <Lightbulb className="h-4 w-4" />}
          </Button>
          <Button
            size="icon"
            className="shrink-0 bg-emerald-600 hover:bg-emerald-700"
            onClick={handleSend}
            disabled={!input.trim() || streaming}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </Card>

      {/* API Key settings dialog */}
      <Dialog open={keyOpen} onOpenChange={setKeyOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Gemini API Key cá nhân</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Nhập key riêng để dùng quota của bạn, không ảnh hưởng người dùng khác.
            Lấy key miễn phí tại{" "}
            <a href="https://aistudio.google.com" target="_blank" rel="noreferrer noopener" className="text-violet-600 underline">
              aistudio.google.com
            </a>.
          </p>
          {maskedKey && (
            <p className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-3 py-1.5">
              Key hiện tại: <span className="font-mono">{maskedKey}</span>
            </p>
          )}
          <Input
            type="password"
            placeholder="AIzaSy..."
            value={keyInput}
            onChange={(e) => setKeyInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && saveApiKey()}
            autoComplete="off"
          />
          <div className="flex gap-2">
            <Button className="flex-1" onClick={saveApiKey} disabled={keySaving || !keyInput.trim()}>
              {keySaving ? "Đang lưu…" : "Lưu key"}
            </Button>
            {maskedKey && (
              <Button variant="outline" onClick={async () => { await insightSettingsApi.save(""); setMaskedKey(null); setKeyOpen(false); }}>
                Xóa
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Source detail modal */}
      <Dialog open={sourceOpen} onOpenChange={setSourceOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Chi tiết nguồn</DialogTitle>
          </DialogHeader>
          {sourceDetail?.kind === "loading" && (
            <div className="space-y-2 py-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
          {sourceDetail?.kind === "error" && (
            <p className="text-sm text-destructive py-2">{sourceDetail.message}</p>
          )}
          {sourceDetail?.kind === "journal" && (
            <div className="space-y-2 text-sm py-2">
              <p className="text-xs text-muted-foreground">
                {new Date(sourceDetail.data.created_at).toLocaleDateString("vi-VN", {
                  weekday: "long", year: "numeric", month: "long", day: "numeric",
                })}
              </p>
              <p className="whitespace-pre-wrap leading-relaxed">{sourceDetail.data.content}</p>
            </div>
          )}
          {sourceDetail?.kind === "transaction" && (() => {
            const t = sourceDetail.data;
            const isIncome = t.type === "income";
            return (
              <div className="space-y-2 text-sm py-2">
                <p className="text-xs text-muted-foreground">
                  {new Date(t.transaction_date).toLocaleDateString("vi-VN", {
                    weekday: "long", year: "numeric", month: "long", day: "numeric",
                  })}
                </p>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">{CATEGORY_LABEL[t.category] ?? t.category}</span>
                  <span className={cn("font-semibold text-base", isIncome ? "text-emerald-600" : "text-rose-600")}>
                    {isIncome ? "+" : "-"}{t.amount.toLocaleString("vi-VN")} {t.currency}
                  </span>
                </div>
                {t.note && <p className="text-muted-foreground italic">"{t.note}"</p>}
              </div>
            );
          })()}
        </DialogContent>
      </Dialog>
    </div>
  );
}
