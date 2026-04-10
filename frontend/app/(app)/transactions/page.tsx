"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Plus, Trash2, Pencil, RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  transactionApi,
  TransactionPayload,
  TransactionResponse,
  Category,
  TransactionType,
} from "@/services/transaction";
import { insightReindexApi } from "@/services/insight";

const CATEGORIES: Category[] = [
  "food","shopping","entertainment","transport","health","education","utilities","other",
];

const TYPE_COLORS: Record<TransactionType, string> = {
  expense: "bg-rose-100 text-rose-700",
  income: "bg-emerald-100 text-emerald-700",
};

function formatVND(amount: number) {
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(amount);
}

interface FormState {
  amount: string;
  type: TransactionType;
  category: Category;
  note: string;
  transaction_date: string;
}

const defaultForm: FormState = {
  amount: "",
  type: "expense",
  category: "food",
  note: "",
  transaction_date: format(new Date(), "yyyy-MM-dd"),
};

function TransactionForm({
  initial,
  onSubmit,
  loading,
}: {
  initial?: FormState;
  onSubmit: (data: TransactionPayload) => void;
  loading: boolean;
}) {
  const [form, setForm] = useState<FormState>(initial ?? defaultForm);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onSubmit({
      amount: parseFloat(form.amount),
      type: form.type,
      category: form.category,
      note: form.note || undefined,
      transaction_date: form.transaction_date,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Amount (VND)</Label>
          <Input
            type="number"
            min={1000}
            step={1000}
            placeholder="50000"
            value={form.amount}
            onChange={(e) => setForm({ ...form, amount: e.target.value })}
            required
          />
        </div>
        <div className="space-y-1">
          <Label>Date</Label>
          <Input
            type="date"
            value={form.transaction_date}
            onChange={(e) => setForm({ ...form, transaction_date: e.target.value })}
            required
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label>Type</Label>
          <Select
            value={form.type}
              onValueChange={(v: string | null) => v && setForm({ ...form, type: v as TransactionType })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="expense">Expense</SelectItem>
              <SelectItem value="income">Income</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Category</Label>
          <Select
            value={form.category}
              onValueChange={(v: string | null) => v && setForm({ ...form, category: v as Category })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CATEGORIES.map((c) => (
                <SelectItem key={c} value={c} className="capitalize">
                  {c}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1">
        <Label>Note (optional)</Label>
        <Input
          placeholder="Coffee with friends…"
          value={form.note}
          onChange={(e) => setForm({ ...form, note: e.target.value })}
        />
      </div>
      <Button type="submit" className="w-full" disabled={loading}>
        {loading ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}

export default function TransactionsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [open, setOpen] = useState(false);
  const [editTx, setEditTx] = useState<TransactionResponse | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["transactions", page],
    queryFn: () => transactionApi.list({ page, page_size: 20 }),
  });

  const createMut = useMutation({
    mutationFn: transactionApi.create,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      setOpen(false);
      toast.success("Transaction added");
    },
    onError: () => toast.error("Failed to add transaction"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<TransactionPayload> }) =>
      transactionApi.update(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      setEditTx(null);
      toast.success("Transaction updated");
    },
    onError: () => toast.error("Failed to update"),
  });

  const deleteMut = useMutation({
    mutationFn: transactionApi.delete,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      toast.success("Deleted");
    },
    onError: () => toast.error("Failed to delete"),
  });

  const reindexMut = useMutation({
    mutationFn: (t: TransactionResponse) =>
      insightReindexApi.reindexTransaction(t.id, {
        transaction_id: t.id,
        user_id: t.user_id,
        amount: String(t.amount),
        currency: t.currency,
        type: t.type,
        category: t.category,
        note: t.note ?? "",
        transaction_date: t.transaction_date.slice(0, 10),
      }),
    onSuccess: () => toast.success("Synced to AI"),
    onError: () => toast.error("Sync failed"),
  });

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Transactions</h1>
          <p className="text-muted-foreground text-sm">{data?.total ?? 0} total</p>
        </div>
        <Button className="gap-2" onClick={() => setOpen(true)}>
          <Plus className="h-4 w-4" />
          Add
        </Button>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>New Transaction</DialogTitle>
            </DialogHeader>
            <TransactionForm
              onSubmit={(d) => createMut.mutate(d)}
              loading={createMut.isPending}
            />
          </DialogContent>
        </Dialog>
      </div>

      {/* Edit dialog */}
      <Dialog open={!!editTx} onOpenChange={(o: boolean) => !o && setEditTx(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit Transaction</DialogTitle>
          </DialogHeader>
          {editTx && (
            <TransactionForm
              initial={{
                amount: String(editTx.amount),
                type: editTx.type,
                category: editTx.category,
                note: editTx.note ?? "",
                transaction_date: editTx.transaction_date.slice(0, 10),
              }}
              onSubmit={(d) => updateMut.mutate({ id: editTx.id, data: d })}
              loading={updateMut.isPending}
            />
          )}
        </DialogContent>
      </Dialog>

      {/* Table */}
      <div className="bg-white rounded-lg border overflow-hidden">
        {isLoading ? (
          <div className="p-4 space-y-3">
            {[1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
          </div>
        ) : data?.items.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground">
            <p className="text-lg">No transactions yet</p>
            <p className="text-sm">Click &quot;Add&quot; to record your first one</p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Date</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Category</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Note</th>
                <th className="text-left px-4 py-3 font-medium text-muted-foreground">Type</th>
                <th className="text-right px-4 py-3 font-medium text-muted-foreground">Amount</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {data?.items.map((t) => (
                <tr key={t.id} className="border-b last:border-0 hover:bg-slate-50">
                  <td className="px-4 py-3 text-muted-foreground">
                    {t.transaction_date ? format(new Date(t.transaction_date), "dd/MM/yy") : "—"}
                  </td>
                  <td className="px-4 py-3 capitalize font-medium">{t.category}</td>
                  <td className="px-4 py-3 text-muted-foreground truncate max-w-40">{t.note ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${TYPE_COLORS[t.type]}`}>
                      {t.type}
                    </span>
                  </td>
                  <td className={`px-4 py-3 text-right font-semibold ${t.type === "income" ? "text-emerald-600" : "text-rose-500"}`}>
                    {t.type === "income" ? "+" : "-"}{formatVND(Number(t.amount))}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1 justify-end">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-sky-500 hover:text-sky-700"
                        title="Sync to AI (re-index for chat)"
                        onClick={() => reindexMut.mutate(t)}
                        disabled={reindexMut.isPending}
                      >
                        <RefreshCcw className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                        onClick={() => setEditTx(t)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-rose-500 hover:text-rose-700"
                        onClick={() => {
                          if (confirm("Delete this transaction?")) {
                            deleteMut.mutate(t.id);
                          }
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            Previous
          </Button>
          <span className="px-3 py-1.5 text-sm text-muted-foreground">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page === totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
