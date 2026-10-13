import Constants from "expo-constants";

/**
 * Your own Fault Sigma server. Set EXPO_PUBLIC_API_URL (e.g. https://faultsigma.example.org/api)
 * or `extra.apiUrl` in app.json. The app talks to nothing else.
 */
export const API_URL: string =
  process.env.EXPO_PUBLIC_API_URL ??
  (Constants.expoConfig?.extra as { apiUrl?: string } | undefined)?.apiUrl ??
  "https://localhost/api";
