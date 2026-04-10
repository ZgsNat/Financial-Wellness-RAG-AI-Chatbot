import { create } from "zustand";
import { persist } from "zustand/middleware";

function setCookie(name: string, value: string, days = 7) {
  if (typeof document === "undefined") return;
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function deleteCookie(name: string) {
  if (typeof document === "undefined") return;
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

interface AuthState {
  token: string | null;
  user: { id: string; email: string; full_name?: string } | null;
  setAuth: (token: string, user: AuthState["user"]) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => {
        setCookie("fw-token", token);
        set({ token, user });
      },
      logout: () => {
        deleteCookie("fw-token");
        set({ token: null, user: null });
      },
    }),
    { name: "fw-auth" }
  )
);
