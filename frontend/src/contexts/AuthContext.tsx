"use client";
import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { apiFetch } from "@/lib/api";

interface User {
  user_id: string;
  name: string;
  email: string;
  currency?: string;
  profile_photo?: string;
}

interface AuthCtx {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>(null!);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function loadProfile() {
    try {
      const data = await apiFetch<{ profile: User }>("/api/profile");
      setUser(data.profile);
    } catch {
      setUser(null);
      localStorage.removeItem("token");
      setToken(null);
    }
  }

  useEffect(() => {
    const t = localStorage.getItem("token");
    if (t) {
      setToken(t);
      loadProfile().finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  async function login(email: string, password: string) {
    const data = await apiFetch<{ token: string; name: string; user_id: string; email: string }>(
      "/api/login",
      { method: "POST", body: JSON.stringify({ email, password }) }
    );
    localStorage.setItem("token", data.token);
    setToken(data.token);
    setUser({ user_id: data.user_id, name: data.name, email: data.email });
    await loadProfile();
  }

  function logout() {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    window.location.href = "/login";
  }

  async function refresh() {
    await loadProfile();
  }

  return (
    <Ctx.Provider value={{ user, token, loading, login, logout, refresh }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);
