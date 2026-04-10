import { api } from "@/lib/api";

export type AlertType =
  | "spending_spike"
  | "category_overload"
  | "mood_spending_warning"
  | "budget_exceeded"
  | "wellness_tip";

export interface NotificationItem {
  id: string;
  user_id: string;
  type: AlertType;
  message: string;
  is_read: boolean;
  created_at: string;
}

export interface PaginatedNotifications {
  items: NotificationItem[];
  total: number;
  unread_count: number;
}

export const notificationApi = {
  list: (params?: { unread_only?: boolean; page?: number; page_size?: number }) =>
    api.get<PaginatedNotifications>("/notifications", { params }).then((r) => r.data),

  markRead: (id: string) =>
    api.patch(`/notifications/${id}/read`),
};
