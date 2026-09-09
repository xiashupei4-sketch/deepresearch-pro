import { create } from "zustand";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  toggle: () => void;
}

function apply(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem("drp-theme", theme);
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: (localStorage.getItem("drp-theme") as Theme) || "dark",
  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    apply(next);
    set({ theme: next });
  },
}));

// apply persisted theme on load
apply((localStorage.getItem("drp-theme") as Theme) || "dark");
