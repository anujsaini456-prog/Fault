// Runs before first paint so there's no light/dark flash. External file (not inline) to satisfy CSP.
import { applyTheme, getStoredTheme } from "./theme";

applyTheme(getStoredTheme());
