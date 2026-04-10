import { api } from "@/lib/api";

export interface MoodPayload {
  score: 1 | 2 | 3 | 4 | 5;
  note?: string;
}

export interface MoodResponse {
  id: string;
  user_id: string;
  score: number;
  note?: string;
  created_at: string;
}

export interface JournalPayload {
  content: string;
}

export interface JournalResponse {
  id: string;
  user_id: string;
  content: string;
  word_count: number;
  created_at: string;
  updated_at: string;
}

export interface PaginatedJournal {
  items: JournalResponse[];
  total: number;
  page: number;
  page_size: number;
}

export const journalApi = {
  listMoods: (params?: { page?: number; page_size?: number }) =>
    api.get<MoodResponse[]>("/journal/moods", { params }).then((r) => r.data),

  logMood: (data: MoodPayload) =>
    api.post<MoodResponse>("/journal/moods", data).then((r) => r.data),

  listEntries: (params?: { page?: number; page_size?: number }) =>
    api.get<PaginatedJournal>("/journal/entries", { params }).then((r) => r.data),

  getEntry: (id: string) =>
    api.get<JournalResponse>(`/journal/entries/${id}`).then((r) => r.data),

  createEntry: (data: JournalPayload) =>
    api.post<JournalResponse>("/journal/entries", data).then((r) => r.data),

  updateEntry: (id: string, data: JournalPayload) =>
    api.patch<JournalResponse>(`/journal/entries/${id}`, data).then((r) => r.data),

  deleteEntry: (id: string) =>
    api.delete(`/journal/entries/${id}`),
};
