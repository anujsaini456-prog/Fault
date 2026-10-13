import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { AuthProvider, useAuth } from "../src/auth";
import { usePalette } from "../src/theme";

const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 60_000 } } });

function Routes() {
  const { state, unlock, signOut } = useAuth();
  const c = usePalette();

  if (state.status === "loading" || state.status === "locked") {
    return (
      <View style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: 16, backgroundColor: c.bg, padding: 24 }}>
        <Text style={{ fontSize: 24, fontWeight: "700", color: c.text }}>Fault Sigma</Text>
        {state.status === "loading" ? (
          <ActivityIndicator color={c.brand} />
        ) : (
          <>
            <Pressable accessibilityRole="button" onPress={() => void unlock()}
              style={{ backgroundColor: c.brand, paddingVertical: 14, paddingHorizontal: 32, borderRadius: 10 }}>
              <Text style={{ color: "#fff", fontWeight: "600", fontSize: 16 }}>Unlock</Text>
            </Pressable>
            <Pressable accessibilityRole="button" onPress={() => void signOut()}>
              <Text style={{ color: c.muted }}>Sign out</Text>
            </Pressable>
          </>
        )}
      </View>
    );
  }

  const signedIn = state.status === "signed-in";
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.bg } }}>
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="index" />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="login" />
      </Stack.Protected>
    </Stack>
  );
}

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <StatusBar style="auto" />
          <Routes />
        </AuthProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
