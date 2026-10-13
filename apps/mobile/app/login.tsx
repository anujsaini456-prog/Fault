import { ApiError, loginRequestSchema, totpCodeSchema } from "@fault-sigma/core";
import * as Linking from "expo-linking";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, useAuth } from "../src/auth";
import { usePalette } from "../src/theme";

type Step =
  | { kind: "password" }
  | { kind: "mfa"; mfaToken: string }
  | { kind: "mfa-setup"; mfaToken: string; secret: string; otpauthUri: string };

function message(e: unknown): string {
  return e instanceof ApiError ? e.message : "Can't reach the server. Check your connection and try again.";
}

export default function LoginScreen() {
  const { acceptSession } = useAuth();
  const c = usePalette();
  const [step, setStep] = useState<Step>({ kind: "password" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const input = {
    borderWidth: 1, borderColor: c.border, backgroundColor: c.inputBg, color: c.text,
    borderRadius: 10, paddingHorizontal: 14, paddingVertical: 12, fontSize: 16,
  } as const;
  const label = { color: c.muted, fontSize: 14, fontWeight: "500", marginBottom: 6 } as const;

  async function submitPassword() {
    const parsed = loginRequestSchema.safeParse({ email, password });
    if (!parsed.success) return setError(parsed.error.issues[0]?.message ?? "Check your details");
    setBusy(true);
    setError(null);
    try {
      const r = await api.login(parsed.data);
      setPassword("");
      if (r.status === "ok") await acceptSession(r);
      else if (r.status === "mfa_required") setStep({ kind: "mfa", mfaToken: r.mfa_token });
      else setStep({ kind: "mfa-setup", mfaToken: r.mfa_token, secret: r.secret, otpauthUri: r.otpauth_uri });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  }

  async function submitCode() {
    if (step.kind === "password") return;
    const parsed = totpCodeSchema.safeParse(code);
    if (!parsed.success) return setError(parsed.error.issues[0]?.message ?? "Enter the 6-digit code");
    setBusy(true);
    setError(null);
    try {
      await acceptSession(await api.verifyMfa({ mfa_token: step.mfaToken, code: parsed.data }));
    } catch (e) {
      setError(message(e));
      setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: "center", padding: 24, gap: 24 }}
          keyboardShouldPersistTaps="handled">
          <View style={{ alignItems: "center", gap: 6 }}>
            <Text style={{ fontSize: 28, fontWeight: "700", color: c.text }}>Fault Sigma</Text>
            <Text style={{ color: c.muted }}>Fault intelligence for decision makers</Text>
          </View>

          <View style={{ backgroundColor: c.card, borderColor: c.border, borderWidth: 1, borderRadius: 16, padding: 20, gap: 16 }}>
            {step.kind === "password" ? (
              <>
                <View>
                  <Text style={label}>Work email</Text>
                  <TextInput style={input} value={email} onChangeText={setEmail} autoCapitalize="none"
                    autoComplete="email" keyboardType="email-address" textContentType="username"
                    accessibilityLabel="Work email" />
                </View>
                <View>
                  <Text style={label}>Password</Text>
                  <TextInput style={input} value={password} onChangeText={setPassword} secureTextEntry
                    autoComplete="current-password" textContentType="password" accessibilityLabel="Password"
                    onSubmitEditing={() => void submitPassword()} />
                </View>
              </>
            ) : (
              <>
                <Text style={{ fontSize: 17, fontWeight: "600", color: c.text }}>
                  {step.kind === "mfa-setup" ? "Set up two-step verification" : "Two-step verification"}
                </Text>
                {step.kind === "mfa-setup" ? (
                  <View style={{ gap: 10 }}>
                    <Text style={{ color: c.muted }}>
                      Your role requires it. Add Fault Sigma to an authenticator app, then enter the code it shows.
                    </Text>
                    <Pressable accessibilityRole="button" onPress={() => void Linking.openURL(step.otpauthUri)}>
                      <Text style={{ color: c.brand, fontWeight: "600" }}>Open authenticator app</Text>
                    </Pressable>
                    <Text style={{ color: c.muted, fontSize: 13 }}>Or enter this key manually:</Text>
                    <Text selectable style={{ fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace", color: c.text, backgroundColor: c.chip, padding: 8, borderRadius: 6 }}>
                      {step.secret}
                    </Text>
                  </View>
                ) : (
                  <Text style={{ color: c.muted }}>Enter the code from your authenticator app.</Text>
                )}
                <TextInput style={[input, { textAlign: "center", fontSize: 24, letterSpacing: 8 }]} value={code}
                  onChangeText={(t) => setCode(t.replace(/\D/g, "").slice(0, 6))} keyboardType="number-pad"
                  autoComplete="one-time-code" textContentType="oneTimeCode" accessibilityLabel="6-digit code"
                  onSubmitEditing={() => void submitCode()} />
              </>
            )}

            {error ? (
              <Text accessibilityRole="alert" style={{ color: c.danger, backgroundColor: c.dangerBg, padding: 10, borderRadius: 8 }}>
                {error}
              </Text>
            ) : null}

            <Pressable accessibilityRole="button" disabled={busy}
              onPress={() => void (step.kind === "password" ? submitPassword() : submitCode())}
              style={{ backgroundColor: c.brand, opacity: busy ? 0.6 : 1, borderRadius: 10, paddingVertical: 14, alignItems: "center" }}>
              <Text style={{ color: "#fff", fontWeight: "600", fontSize: 16 }}>
                {busy ? "Please wait…" : step.kind === "password" ? "Sign in" : "Verify"}
              </Text>
            </Pressable>
            {step.kind !== "password" ? (
              <Pressable accessibilityRole="button" onPress={() => { setStep({ kind: "password" }); setCode(""); setError(null); }}>
                <Text style={{ color: c.muted, textAlign: "center" }}>Use a different account</Text>
              </Pressable>
            ) : null}
          </View>
          <Text style={{ color: c.muted, fontSize: 12, textAlign: "center" }}>
            Self-hosted. Your data never leaves your organisation's servers.
          </Text>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
