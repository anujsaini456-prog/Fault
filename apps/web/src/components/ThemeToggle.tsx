import { useState } from "react";
import { getStoredTheme, setTheme, type ThemeChoice } from "../theme";

const NEXT: Record<ThemeChoice, ThemeChoice> = { system: "light", light: "dark", dark: "system" };
const LABEL: Record<ThemeChoice, string> = { system: "Auto", light: "Light", dark: "Dark" };

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(getStoredTheme);
  return (
    <button
      type="button"
      onClick={() => {
        const next = NEXT[choice];
        setTheme(next);
        setChoice(next);
      }}
      className="rounded-lg px-3 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
      aria-label={`Theme: ${LABEL[choice]}. Click to change.`}
    >
      {LABEL[choice]}
    </button>
  );
}
