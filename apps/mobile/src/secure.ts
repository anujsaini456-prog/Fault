import type { DashboardHome } from "@fault-sigma/core";
import * as SecureStore from "expo-secure-store";

// Keychain (iOS) / Keystore-backed storage (Android). Never AsyncStorage for credentials.
const REFRESH_KEY = "fs.refresh";
const HOME_CACHE_KEY = "fs.home";
const opts: SecureStore.SecureStoreOptions = { keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY };

export const getRefreshToken = () => SecureStore.getItemAsync(REFRESH_KEY, opts);
export const setRefreshToken = (t: string) => SecureStore.setItemAsync(REFRESH_KEY, t, opts);

/** Last synced dashboard, readable offline (spec §9). Encrypted at rest like the token. */
export async function getCachedHome(): Promise<{ savedAt: string; home: DashboardHome } | null> {
  const raw = await SecureStore.getItemAsync(HOME_CACHE_KEY, opts);
  try {
    return raw ? (JSON.parse(raw) as { savedAt: string; home: DashboardHome }) : null;
  } catch {
    return null;
  }
}
export const setCachedHome = (home: DashboardHome) =>
  SecureStore.setItemAsync(HOME_CACHE_KEY, JSON.stringify({ savedAt: new Date().toISOString(), home }), opts);

/** Sign-out or revocation wipes everything this app stored on the device. */
export async function wipeDevice(): Promise<void> {
  await Promise.all([SecureStore.deleteItemAsync(REFRESH_KEY, opts), SecureStore.deleteItemAsync(HOME_CACHE_KEY, opts)]);
}
