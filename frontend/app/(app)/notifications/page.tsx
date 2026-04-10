"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Bell, CheckCheck } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent } from "@/components/ui/card";
import { notificationApi, NotificationItem, AlertType } from "@/services/notification";
import { cn } from "@/lib/utils";

const ALERT_ICONS: Record<AlertType, string> = {
  spending_spike: "📈",
  category_overload: "⚠️",
  mood_spending_warning: "💭",
  budget_exceeded: "🚨",
  wellness_tip: "💚",
};

const ALERT_COLORS: Record<AlertType, string> = {
  spending_spike: "border-amber-200 bg-amber-50",
  category_overload: "border-amber-200 bg-amber-50",
  mood_spending_warning: "border-violet-200 bg-violet-50",
  budget_exceeded: "border-rose-200 bg-rose-50",
  wellness_tip: "border-emerald-200 bg-emerald-50",
};

export default function NotificationsPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);
  const [unreadOnly, setUnreadOnly] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["notifications", page, unreadOnly],
    queryFn: () => notificationApi.list({ page, page_size: 20, unread_only: unreadOnly }),
    refetchInterval: 30_000,
  });

  const markReadMut = useMutation({
    mutationFn: notificationApi.markRead,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: () => toast.error("Failed to mark as read"),
  });

  const totalPages = data ? Math.ceil(data.total / 20) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Notifications</h1>
          <p className="text-muted-foreground text-sm">
            {data?.unread_count ?? 0} unread • {data?.total ?? 0} total
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant={unreadOnly ? "default" : "outline"}
            size="sm"
            onClick={() => setUnreadOnly(!unreadOnly)}
          >
            {unreadOnly ? "Show all" : "Unread only"}
          </Button>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full" />)}
        </div>
      ) : data?.items.length === 0 ? (
        <div className="text-center py-16 bg-white rounded-lg border">
          <Bell className="h-12 w-12 text-muted-foreground mx-auto mb-3" />
          <p className="text-lg text-muted-foreground">No notifications</p>
          {unreadOnly && (
            <Button variant="link" onClick={() => setUnreadOnly(false)}>
              View all
            </Button>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {data?.items.map((notif: NotificationItem) => (
            <Card
              key={notif.id}
              className={cn(
                "border transition-all",
                !notif.is_read && ALERT_COLORS[notif.type],
                notif.is_read && "opacity-70"
              )}
            >
              <CardContent className="pt-4">
                <div className="flex items-start gap-3">
                  <span className="text-2xl shrink-0">{ALERT_ICONS[notif.type]}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-xs font-medium text-muted-foreground capitalize">
                        {notif.type?.replace(/_/g, " ")}
                      </span>
                      {!notif.is_read && (
                        <Badge className="bg-emerald-500 text-white text-xs px-1.5 py-0 h-4">New</Badge>
                      )}
                    </div>
                    <p className="text-sm text-slate-700 leading-relaxed">{notif.message}</p>
                    <p className="text-xs text-muted-foreground mt-1.5">
                      {notif.created_at ? format(new Date(notif.created_at), "dd/MM/yyyy HH:mm") : "—"}
                    </p>
                  </div>
                  {!notif.is_read && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 shrink-0 text-emerald-600"
                      title="Mark as read"
                      onClick={() => markReadMut.mutate(notif.id)}
                      disabled={markReadMut.isPending}
                    >
                      <CheckCheck className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="flex justify-center gap-2">
          <Button variant="outline" size="sm" disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="px-3 py-1.5 text-sm text-muted-foreground">{page} / {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page === totalPages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
