"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { Plus, Trash2, Pencil } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { journalApi, JournalResponse } from "@/services/journal";

const MOOD_EMOJIS = [
  { score: 1 as const, emoji: "😢", label: "Terrible" },
  { score: 2 as const, emoji: "😕", label: "Bad" },
  { score: 3 as const, emoji: "😐", label: "Okay" },
  { score: 4 as const, emoji: "🙂", label: "Good" },
  { score: 5 as const, emoji: "😊", label: "Great" },
];

function MoodLogger() {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<1|2|3|4|5|null>(null);
  const [note, setNote] = useState("");

  const logMood = useMutation({
    mutationFn: () => journalApi.logMood({ score: selected!, note: note || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["moods"] });
      setSelected(null);
      setNote("");
      toast.success("Mood logged!");
    },
    onError: () => toast.error("Failed to log mood"),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">How are you feeling today?</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-3">
          {MOOD_EMOJIS.map(({ score, emoji, label }) => (
            <button
              key={score}
              type="button"
              title={label}
              onClick={() => setSelected(score)}
              className={`text-3xl rounded-lg p-2 transition-all ${
                selected === score
                  ? "bg-violet-100 ring-2 ring-violet-400 scale-110"
                  : "hover:bg-slate-100"
              }`}
            >
              {emoji}
            </button>
          ))}
        </div>
        {selected && (
          <div className="space-y-2">
            <Textarea
              placeholder="Any notes? (optional)"
              value={note}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNote(e.target.value)}
              rows={2}
            />
            <Button
              size="sm"
              onClick={() => logMood.mutate()}
              disabled={logMood.isPending}
            >
              {logMood.isPending ? "Logging…" : "Log mood"}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function JournalFormDialog({
  initial,
  trigger,
  onSubmit,
  loading,
}: {
  initial?: string;
  trigger: React.ReactNode;
  onSubmit: (content: string) => void;
  loading: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState(initial ?? "");

  return (
    <>
      <span
        onClick={() => {
          setContent(initial ?? "");
          setOpen(true);
        }}
        style={{ cursor: "pointer", display: "contents" }}
      >
        {trigger}
      </span>
      <Dialog
        open={open}
        onOpenChange={(o: boolean) => {
          setOpen(o);
        }}
      >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{initial ? "Edit Entry" : "New Journal Entry"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <Textarea
            placeholder="Write freely about your day, thoughts, or feelings…"
            value={content}
            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setContent(e.target.value)}
            rows={8}
          />
          <p className="text-xs text-muted-foreground">{content.length} / 10000 chars</p>
          <Button
            className="w-full"
            onClick={() => {
              onSubmit(content);
              setOpen(false);
            }}
            disabled={loading || content.trim().length < 1}
          >
            {loading ? "Saving…" : "Save"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
    </>
  );
}

export default function JournalPage() {
  const qc = useQueryClient();
  const [page, setPage] = useState(1);

  const { data: entries, isLoading: entriesLoading } = useQuery({
    queryKey: ["journal-entries", page],
    queryFn: () => journalApi.listEntries({ page, page_size: 10 }),
  });

  const { data: moods } = useQuery({
    queryKey: ["moods"],
    queryFn: () => journalApi.listMoods({ page_size: 7 }),
  });

  const createMut = useMutation({
    mutationFn: (content: string) => journalApi.createEntry({ content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-entries"] });
      toast.success("Entry saved!");
    },
    onError: () => toast.error("Failed to save entry"),
  });

  const updateMut = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      journalApi.updateEntry(id, { content }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-entries"] });
      toast.success("Entry updated!");
    },
    onError: () => toast.error("Failed to update entry"),
  });

  const deleteMut = useMutation({
    mutationFn: journalApi.deleteEntry,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-entries"] });
      toast.success("Deleted");
    },
  });

  const totalPages = entries ? Math.ceil(entries.total / 10) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Journal</h1>
        <JournalFormDialog
          trigger={
            <Button className="gap-2">
              <Plus className="h-4 w-4" />
              New Entry
            </Button>
          }
          onSubmit={(content) => createMut.mutate(content)}
          loading={createMut.isPending}
        />
      </div>

      {/* Mood logger */}
      <MoodLogger />

      {/* Recent moods */}
      {moods && moods.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent Moods</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-3 flex-wrap">
              {moods.slice(0, 7).map((m) => (
                <div key={m.id} className="text-center">
                  <p className="text-2xl">{MOOD_EMOJIS.find((e) => e.score === m.score)?.emoji ?? "😐"}</p>
                  <p className="text-xs text-muted-foreground">{m.created_at ? format(new Date(m.created_at), "dd/MM") : ""}</p>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Entries */}
      <div className="space-y-3">
        <h2 className="font-semibold text-slate-800">Entries</h2>
        {entriesLoading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => <Skeleton key={i} className="h-28 w-full" />)}
          </div>
        ) : entries?.items.length === 0 ? (
          <div className="text-center py-16 text-muted-foreground bg-white rounded-lg border">
            <p className="text-lg">No entries yet</p>
            <p className="text-sm">Start writing your thoughts</p>
          </div>
        ) : (
          entries?.items.map((entry: JournalResponse) => (
            <Card key={entry.id}>
              <CardContent className="pt-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-slate-700 leading-relaxed line-clamp-3">
                      {entry.content}
                    </p>
                    <p className="text-xs text-muted-foreground mt-2">
                      {entry.created_at ? format(new Date(entry.created_at), "dd/MM/yyyy HH:mm") : "—"} • {entry.word_count} words
                    </p>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <JournalFormDialog
                      initial={entry.content}
                      trigger={
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                      }
                      onSubmit={(content) => updateMut.mutate({ id: entry.id, content })}
                      loading={updateMut.isPending}
                    />
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-rose-500"
                      onClick={() => {
                        if (confirm("Delete this entry?")) deleteMut.mutate(entry.id);
                      }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>

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
