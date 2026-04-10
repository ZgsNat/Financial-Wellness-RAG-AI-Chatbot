"use client";

import { useQuery } from "@tanstack/react-query";
import { format, startOfMonth, endOfMonth } from "date-fns";
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { transactionApi, TransactionResponse } from "@/services/transaction";
import { journalApi } from "@/services/journal";
import { insightApi } from "@/services/insight";
import { Skeleton } from "@/components/ui/skeleton";

const COLORS = ["#10b981", "#8b5cf6", "#f59e0b", "#f43f5e", "#3b82f6", "#06b6d4", "#84cc16", "#94a3b8"];

const CATEGORY_LABELS: Record<string, string> = {
  food: "Food",
  shopping: "Shopping",
  entertainment: "Entertainment",
  transport: "Transport",
  health: "Health",
  education: "Education",
  utilities: "Utilities",
  other: "Other",
};

const MOOD_EMOJI: Record<number, string> = { 1: "😢", 2: "😕", 3: "😐", 4: "🙂", 5: "😊" };

function formatVND(amount: number) {
  return new Intl.NumberFormat("vi-VN", { style: "currency", currency: "VND" }).format(amount);
}

function safeFormat(value: string | null | undefined, fmt: string, fallback = "—") {
  if (!value) return fallback;
  const d = new Date(value);
  return isNaN(d.getTime()) ? fallback : format(d, fmt);
}

export default function DashboardPage() {
  const now = new Date();
  const dateFrom = format(startOfMonth(now), "yyyy-MM-dd");
  const dateTo = format(endOfMonth(now), "yyyy-MM-dd");

  const { data: txData, isLoading: txLoading } = useQuery({
    queryKey: ["transactions", "dashboard", dateFrom, dateTo],
    queryFn: () => transactionApi.list({ page_size: 100, date_from: dateFrom, date_to: dateTo }),
  });

  const { data: moods } = useQuery({
    queryKey: ["moods", "dashboard"],
    queryFn: () => journalApi.listMoods({ page_size: 7 }),
  });

  const { data: insights } = useQuery({
    queryKey: ["insights"],
    queryFn: () => insightApi.list(),
  });

  const transactions: TransactionResponse[] = txData?.items ?? [];

  const totalExpense = transactions
    .filter((t) => t.type === "expense")
    .reduce((s, t) => s + Number(t.amount), 0);

  const totalIncome = transactions
    .filter((t) => t.type === "income")
    .reduce((s, t) => s + Number(t.amount), 0);

  const avgMood =
    moods && moods.length > 0
      ? moods.reduce((s, m) => s + m.score, 0) / moods.length
      : null;

  // Category breakdown for pie chart
  const categoryData = Object.entries(
    transactions
      .filter((t) => t.type === "expense")
      .reduce<Record<string, number>>((acc, t) => {
        acc[t.category] = (acc[t.category] ?? 0) + Number(t.amount);
        return acc;
      }, {})
  ).map(([name, value]) => ({ name: CATEGORY_LABELS[name] ?? name, value }));

  const latestInsight = insights?.[0];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Dashboard</h1>
        <p className="text-muted-foreground text-sm">{format(now, "MMMM yyyy")}</p>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Expenses
            </CardTitle>
          </CardHeader>
          <CardContent>
            {txLoading ? (
              <Skeleton className="h-7 w-32" />
            ) : (
              <p className="text-2xl font-bold text-rose-500">{formatVND(totalExpense)}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Income
            </CardTitle>
          </CardHeader>
          <CardContent>
            {txLoading ? (
              <Skeleton className="h-7 w-32" />
            ) : (
              <p className="text-2xl font-bold text-emerald-600">{formatVND(totalIncome)}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Mood (7-day avg)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {avgMood === null ? (
              <p className="text-2xl font-bold text-muted-foreground">—</p>
            ) : (
              <p className="text-2xl font-bold text-violet-600">
                {MOOD_EMOJI[Math.round(avgMood)]} {avgMood.toFixed(1)}/5
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Pie chart */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Spending by Category</CardTitle>
          </CardHeader>
          <CardContent>
            {categoryData.length === 0 ? (
              <p className="text-center text-muted-foreground py-8 text-sm">
                No expenses this month
              </p>
            ) : (
              <ResponsiveContainer width="100%" height={240}>
                <PieChart>
                  <Pie
                    data={categoryData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={90}
                    paddingAngle={3}
                    dataKey="value"
                  >
                    {categoryData.map((_, index) => (
                      <Cell key={index} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(v: unknown) => formatVND(v as number)} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        {/* Recent transactions */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Transactions</CardTitle>
          </CardHeader>
          <CardContent>
            {txLoading ? (
              <div className="space-y-2">
                {[1, 2, 3].map((i) => <Skeleton key={i} className="h-10 w-full" />)}
              </div>
            ) : transactions.length === 0 ? (
              <p className="text-center text-muted-foreground py-8 text-sm">No transactions yet</p>
            ) : (
              <div className="space-y-2">
                {transactions.slice(0, 5).map((t) => (
                  <div key={t.id} className="flex items-center justify-between py-2 border-b last:border-0">
                    <div>
                      <p className="text-sm font-medium capitalize">{t.category}</p>
                      <p className="text-xs text-muted-foreground">{safeFormat(t.transaction_date, "dd/MM/yyyy")}</p>
                    </div>
                    <p className={`text-sm font-semibold ${t.type === "income" ? "text-emerald-600" : "text-rose-500"}`}>
                      {t.type === "income" ? "+" : "-"}{formatVND(Number(t.amount))}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Latest Insight */}
      {latestInsight && (
        <Card className="border-violet-200 bg-violet-50">
          <CardHeader>
            <CardTitle className="text-base text-violet-700">✨ Latest Insight</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-violet-800 leading-relaxed">{latestInsight.content}</p>
            <p className="text-xs text-violet-500 mt-2 capitalize">
              {latestInsight.type?.replace("_", " ")} • {safeFormat(latestInsight.created_at, "dd/MM/yyyy")}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
