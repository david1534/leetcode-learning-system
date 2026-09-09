import { useEffect, useState } from "react";
import { readStored, storeDraft } from "./persistence";
export type Theme = "dark" | "light" | "system";
export function useTheme() {
  const [theme, setTheme] = useState<Theme>(() => readStored("theme", "dark"));
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      document.documentElement.dataset.theme =
        theme === "system" ? (query.matches ? "dark" : "light") : theme;
      window.dispatchEvent(new Event("practice-theme"));
    };
    apply();
    query.addEventListener("change", apply);
    storeDraft("theme", theme);
    return () => query.removeEventListener("change", apply);
  }, [theme]);
  return [theme, setTheme] as const;
}
