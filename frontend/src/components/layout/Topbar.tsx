"use client";
import { Bell, Moon, Sun, Search } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatRelative } from "@/lib/utils";
import { cn } from "@/lib/utils";

interface Notification {
  id: string;
  type: string;
  title: string;
  message: string;
  created_at: string;
  read: boolean;
}

export default function Topbar({ title }: { title: string }) {
  const { theme, setTheme } = useTheme();
  const [notes, setNotes] = useState<Notification[]>([]);
  const [open, setOpen] = useState(false);
  const unread = notes.filter((n) => !n.read).length;

  useEffect(() => {
    apiFetch<{ notifications: Notification[] }>("/api/notifications")
      .then((d) => setNotes(d.notifications ?? []))
      .catch(() => {});
  }, []);

  return (
    <header className="h-14 shrink-0 flex items-center justify-between px-6 border-b border-slate-200 dark:border-[#1e3352] bg-white dark:bg-[#0d1829] sticky top-0 z-20">
      <h1 className="text-sm font-semibold text-slate-900 dark:text-slate-100">{title}</h1>

      <div className="flex items-center gap-2">
        {/* Theme toggle */}
        <button
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          aria-label="Toggle theme"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
        </button>

        {/* Notifications */}
        <div className="relative">
          <button
            onClick={() => setOpen(!open)}
            className="relative p-2 rounded-lg text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Notifications"
          >
            <Bell className="w-4 h-4" />
            {unread > 0 && (
              <span className="absolute top-1 right-1 w-1.5 h-1.5 rounded-full bg-blue-600" />
            )}
          </button>

          {open && (
            <div className="absolute right-0 top-10 w-80 card shadow-card-lg p-0 overflow-hidden z-50">
              <div className="px-4 py-2.5 border-b border-slate-200 dark:border-[#1e3352]">
                <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">Notifications</span>
              </div>
              <div className="max-h-72 overflow-y-auto">
                {notes.length === 0 ? (
                  <p className="p-4 text-xs text-slate-400 text-center">No notifications</p>
                ) : (
                  notes.slice(0, 10).map((n) => (
                    <div key={n.id} className={cn("px-4 py-3 border-b border-slate-100 dark:border-[#1e3352]/50 last:border-0", !n.read && "bg-blue-50/50 dark:bg-blue-900/10")}>
                      <p className="text-xs font-medium text-slate-800 dark:text-slate-200">{n.title}</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 leading-snug">{n.message}</p>
                      <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">{formatRelative(n.created_at)}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
