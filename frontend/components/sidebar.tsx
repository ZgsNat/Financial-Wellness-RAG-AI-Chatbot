"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  LayoutDashboard,
  CreditCard,
  BookOpen,
  MessageSquare,
  Bell,
  LogOut,
  TrendingUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useAuthStore } from "@/store/auth";
import { useQuery } from "@tanstack/react-query";
import { notificationApi } from "@/services/notification";

const navItems = [
  { href: "/dashboard", icon: LayoutDashboard, label: "Dashboard" },
  { href: "/transactions", icon: CreditCard, label: "Transactions" },
  { href: "/journal", icon: BookOpen, label: "Journal" },
  { href: "/chat", icon: MessageSquare, label: "AI Chat" },
  { href: "/notifications", icon: Bell, label: "Notifications" },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout } = useAuthStore();

  const { data: notifData } = useQuery({
    queryKey: ["notifications", "count"],
    queryFn: () => notificationApi.list({ page_size: 1 }),
    refetchInterval: 30_000,
  });

  const unreadCount = notifData?.unread_count ?? 0;

  function handleLogout() {
    logout();
    router.push("/login");
  }

  return (
    <aside className="w-64 bg-white border-r min-h-screen flex flex-col">
      {/* Brand */}
      <div className="p-6 border-b">
        <div className="flex items-center gap-2">
          <TrendingUp className="h-6 w-6 text-emerald-600" />
          <span className="text-xl font-bold text-slate-800">FinWell</span>
        </div>
        {user && (
          <p className="text-xs text-muted-foreground mt-1 truncate">
            {user.full_name || user.email}
          </p>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {navItems.map(({ href, icon: Icon, label }) => {
          const active = pathname.startsWith(href);
          const isNotif = href === "/notifications";
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors",
                active
                  ? "bg-emerald-50 text-emerald-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1">{label}</span>
              {isNotif && unreadCount > 0 && (
                <Badge className="bg-rose-500 text-white text-xs h-5 min-w-5 flex items-center justify-center p-0">
                  {unreadCount > 9 ? "9+" : unreadCount}
                </Badge>
              )}
            </Link>
          );
        })}
      </nav>

      {/* Logout */}
      <div className="p-4 border-t">
        <Button
          variant="ghost"
          className="w-full justify-start gap-3 text-slate-600"
          onClick={handleLogout}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </Button>
      </div>
    </aside>
  );
}
