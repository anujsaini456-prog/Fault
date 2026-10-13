import { useColorScheme } from "react-native";

const light = {
  bg: "#f8fafc", card: "#ffffff", border: "#e2e8f0", text: "#0f172a", muted: "#64748b",
  brand: "#1d4ed8", danger: "#b91c1c", dangerBg: "#fef2f2", chip: "#f1f5f9", inputBg: "#ffffff",
};
const dark: typeof light = {
  bg: "#020617", card: "#0f172a", border: "#1e293b", text: "#f1f5f9", muted: "#94a3b8",
  brand: "#3b82f6", danger: "#fca5a5", dangerBg: "#450a0a", chip: "#1e293b", inputBg: "#0f172a",
};
export type Palette = typeof light;

export function usePalette(): Palette {
  return useColorScheme() === "dark" ? dark : light;
}
