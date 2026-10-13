import {
  ApiError,
  loginRequestSchema,
  totpCodeSchema,
  type LoginResponse,
  type SessionResponse,
} from "@fault-sigma/core";
import { useState, type FormEvent } from "react";
import { Logo } from "../components/Logo";

type Step =
  | { kind: "password" }
  | { kind: "mfa"; mfaToken: string }
  | { kind: "mfa-setup"; mfaToken: string; secret: string; qrSvg: string };

interface Props {
  login: (email: string, password: string) => Promise<LoginResponse>;
  verify: (mfaToken: string, code: string) => Promise<SessionResponse>;
  onSignedIn: (s: SessionResponse) => void;
}

function message(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  return "Can't reach the server. Check your connection and try again.";
}

export function LoginPage({ login, verify, onSignedIn }: Props) {
  const [step, setStep] = useState<Step>({ kind: "password" });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitPassword(e: FormEvent) {
    e.preventDefault();
    const parsed = loginRequestSchema.safeParse({ email, password });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check your details");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await login(parsed.data.email, parsed.data.password);
      setPassword("");
      if (r.status === "ok") onSignedIn(r);
      else if (r.status === "mfa_required") setStep({ kind: "mfa", mfaToken: r.mfa_token });
      else setStep({ kind: "mfa-setup", mfaToken: r.mfa_token, secret: r.secret, qrSvg: r.qr_svg });
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e: FormEvent) {
    e.preventDefault();
    if (step.kind === "password") return;
    const parsed = totpCodeSchema.safeParse(code);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Enter the 6-digit code");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSignedIn(await verify(step.mfaToken, parsed.data));
    } catch (err) {
      setError(message(err));
      setCode("");
      if (err instanceof ApiError && err.message.startsWith("Sign-in expired")) setStep({ kind: "password" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <Logo className="h-12 w-12" />
          <h1 className="text-2xl font-bold">Fault Sigma</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Fault intelligence for decision makers</p>
        </div>

        <div className="card p-6">
          {step.kind === "password" ? (
            <form onSubmit={submitPassword} noValidate className="space-y-4">
              <div>
                <label htmlFor="email" className="label">Work email</label>
                <input id="email" type="email" autoComplete="username" className="input" value={email}
                  onChange={(e) => setEmail(e.target.value)} required autoFocus />
              </div>
              <div>
                <label htmlFor="password" className="label">Password</label>
                <input id="password" type="password" autoComplete="current-password" className="input"
                  value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <ErrorText error={error} />
              <button type="submit" className="btn-primary" disabled={busy}>
                {busy ? "Signing in…" : "Sign in"}
              </button>
            </form>
          ) : (
            <form onSubmit={submitCode} noValidate className="space-y-4">
              {step.kind === "mfa-setup" ? (
                <div className="space-y-3 text-sm">
                  <h2 className="text-base font-semibold">Set up two-step verification</h2>
                  <p className="text-slate-600 dark:text-slate-400">
                    Your role requires it. Scan this code with an authenticator app (for example Aegis, FreeOTP or
                    Google Authenticator), then enter the 6-digit code it shows.
                  </p>
                  <img
                    src={`data:image/svg+xml;utf8,${encodeURIComponent(step.qrSvg)}`}
                    alt="QR code for your authenticator app"
                    className="mx-auto h-48 w-48 rounded-lg bg-white p-2"
                  />
                  <details className="text-slate-600 dark:text-slate-400">
                    <summary className="cursor-pointer">Can't scan? Enter this key instead</summary>
                    <code className="mt-2 block break-all rounded bg-slate-100 p-2 font-mono text-xs dark:bg-slate-800">
                      {step.secret}
                    </code>
                  </details>
                </div>
              ) : (
                <div className="space-y-1">
                  <h2 className="text-base font-semibold">Two-step verification</h2>
                  <p className="text-sm text-slate-600 dark:text-slate-400">Enter the code from your authenticator app.</p>
                </div>
              )}
              <div>
                <label htmlFor="code" className="label">6-digit code</label>
                <input id="code" inputMode="numeric" autoComplete="one-time-code" pattern="\d{6}" maxLength={6}
                  className="input text-center font-mono text-2xl tracking-[0.5em]" value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} autoFocus />
              </div>
              <ErrorText error={error} />
              <button type="submit" className="btn-primary" disabled={busy || code.length !== 6}>
                {busy ? "Checking…" : "Verify"}
              </button>
              <button type="button" className="w-full text-sm text-slate-500 hover:underline"
                onClick={() => { setStep({ kind: "password" }); setCode(""); setError(null); }}>
                Use a different account
              </button>
            </form>
          )}
        </div>
        <p className="mt-6 text-center text-xs text-slate-500">
          Self-hosted. Your data never leaves your organisation's servers.
        </p>
      </div>
    </main>
  );
}

function ErrorText({ error }: { error: string | null }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
      {error}
    </p>
  );
}
