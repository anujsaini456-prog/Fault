import { Navigate, Route, Routes } from "react-router-dom";
import { api, useAuth } from "./auth";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";

export function App() {
  const { state, acceptSession, signOut } = useAuth();

  if (state.status === "loading") {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-slate-500" role="status">
        Loading…
      </div>
    );
  }

  if (state.status === "signed-out") {
    return (
      <Routes>
        <Route
          path="/login"
          element={
            <LoginPage
              login={(email, password) => api.login({ email, password })}
              verify={(mfa_token, code) => api.verifyMfa({ mfa_token, code })}
              onSignedIn={acceptSession}
            />
          }
        />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route
        path="/"
        element={<HomePage user={state.user} loadHome={api.dashboardHome} onSignOut={() => void signOut()} />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
