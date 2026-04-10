import { api } from "@/lib/api";

export type TransactionType = "expense" | "income";
export type Category =
  | "food"
  | "shopping"
  | "entertainment"
  | "transport"
  | "health"
  | "education"
  | "utilities"
  | "other";

export interface TransactionPayload {
  amount: number;
  currency?: string;
  type?: TransactionType;
  category: Category;
  note?: string;
  transaction_date: string; // ISO date string
}

export interface TransactionResponse {
  id: string;
  user_id: string;
  amount: number;
  currency: string;
  type: TransactionType;
  category: Category;
  note?: string;
  transaction_date: string;
  created_at: string;
}

export interface PaginatedTransactions {
  items: TransactionResponse[];
  total: number;
  page: number;
  page_size: number;
}

export const transactionApi = {
  list: (params?: { page?: number; page_size?: number; date_from?: string; date_to?: string }) =>
    api.get<PaginatedTransactions>("/transactions", { params }).then((r) => r.data),

  get: (id: string) =>
    api.get<TransactionResponse>(`/transactions/${id}`).then((r) => r.data),

  create: (data: TransactionPayload) =>
    api.post<TransactionResponse>("/transactions", data).then((r) => r.data),

  update: (id: string, data: Partial<TransactionPayload>) =>
    api.patch<TransactionResponse>(`/transactions/${id}`, data).then((r) => r.data),

  delete: (id: string) =>
    api.delete(`/transactions/${id}`),
};
