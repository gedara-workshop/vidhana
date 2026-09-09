"use client";

import { useEffect, useState } from "react";

type Theme = "system" | "light" | "dark";
const KEY = "vidhana-theme";

/** Three states, not two. "System" has to be reachable — a viewer who set their
 *  OS to switch at sunset expects this to follow, and a two-way toggle silently
 *  opts them out of that for ever. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    try {
      const stored = localStorage.getItem(KEY) as Theme | null;
      if (stored === "light" || stored === "dark") setTheme(stored);
    } catch { /* private mode, blocked storage — the default is fine */ }
  }, []);

  useEffect(() => {
    const root = document.documentElement;
    if (theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", theme);
    try {
      if (theme === "system") localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, theme);
    } catch { /* nothing to do; the attribute is already applied */ }
  }, [theme]);

  const next: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };
  const label: Record<Theme, string> = { system: "System", light: "Light", dark: "Dark" };

  return (
    <button
      className="btn"
      onClick={() => setTheme(next[theme])}
      title={`Theme: ${label[theme]} — click for ${label[next[theme]]}`}
      aria-label={`Theme: ${label[theme]}. Switch to ${label[next[theme]]}.`}
    >
      {theme === "system" ? <IconSystem /> : theme === "light" ? <IconSun /> : <IconMoon />}
      <span className="hidden lg:inline">{label[theme]}</span>
    </button>
  );
}

const stroke = {
  fill: "none", stroke: "currentColor", strokeWidth: 1.7,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

function IconSun() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden {...stroke}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}
function IconMoon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden {...stroke}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}
function IconSystem() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden {...stroke}>
      <rect x="2" y="4" width="20" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}
