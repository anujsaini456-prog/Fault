import { ApiError, type DashboardHome, type SessionResponse, type User } from "@fault-sigma/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HomePage } from "./HomePage";
import { LoginPage } from "./LoginPage";

const user: User = {
  id: "8d8a2f5e-1c1b-4f43-9a51-0a8f2b0f0c11",
  email: "ceo@northgrid.example",
  full_name: "Nia Executive",
  mfa_enabled: false,
  memberships: [
    {
      organisation_id: "6f1c6c5e-7a3e-4b0e-9f3c-1d2e3f4a5b6c",
      organisation_name: "Northgrid Power",
      site_id: null,
      role: "executive",
    },
  ],
};
const session: SessionResponse = { status: "ok", access_token: "t", expires_in: 900, user };

describe("LoginPage", () => {
  it("signs in directly when no MFA is needed", async () => {
    const onSignedIn = vi.fn();
    const login = vi.fn().mockResolvedValue(session);
    render(<LoginPage login={login} verify={vi.fn()} onSignedIn={onSignedIn} />);
    await userEvent.type(screen.getByLabelText("Work email"), "CEO@Northgrid.example");
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).toHaveBeenCalledWith("ceo@northgrid.example", "secret");
    expect(onSignedIn).toHaveBeenCalledWith(session);
  });

  it("validates before calling the server", async () => {
    const login = vi.fn();
    render(<LoginPage login={login} verify={vi.fn()} onSignedIn={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Work email"), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(login).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("valid email");
  });

  it("shows the server's error message", async () => {
    const login = vi.fn().mockRejectedValue(new ApiError(401, "Invalid email or password"));
    render(<LoginPage login={login} verify={vi.fn()} onSignedIn={vi.fn()} />);
    await userEvent.type(screen.getByLabelText("Work email"), "a@b.co");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid email or password");
  });

  it("walks an admin through MFA enrolment", async () => {
    const login = vi.fn().mockResolvedValue({
      status: "mfa_setup_required",
      mfa_token: "m",
      otpauth_uri: "otpauth://totp/x",
      secret: "JBSWY3DPEHPK3PXP",
      qr_svg: "<svg></svg>",
    });
    const verify = vi.fn().mockResolvedValue(session);
    const onSignedIn = vi.fn();
    render(<LoginPage login={login} verify={verify} onSignedIn={onSignedIn} />);
    await userEvent.type(screen.getByLabelText("Work email"), "admin@x.co");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Set up two-step verification")).toBeInTheDocument();
    expect(screen.getByAltText(/QR code/)).toBeInTheDocument();
    expect(screen.getByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("6-digit code"), "12a3456");
    await userEvent.click(screen.getByRole("button", { name: "Verify" }));
    expect(verify).toHaveBeenCalledWith("m", "123456");
    expect(onSignedIn).toHaveBeenCalledWith(session);
  });
});

describe("HomePage", () => {
  it("shows the five KPI tiles with honest no-data badges", async () => {
    const home: DashboardHome = {
      organisations: [{ id: user.memberships[0]!.organisation_id, name: "Northgrid Power" }],
      site_count: 3,
      kpis: ["SAIDI", "SAIFI", "Faults", "Availability", "Sigma"].map((label) => ({
        key: label, label, value: null, unit: "", trend: null, higher_is_better: true, trust: "none" as const,
      })),
      decisions_waiting: [],
      top_risks: [],
      what_changed: ["No fault data has been loaded yet."],
    };
    render(
      <QueryClientProvider client={new QueryClient()}>
        <HomePage user={user} loadHome={() => Promise.resolve(home)} onSignOut={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Northgrid Power")).toBeInTheDocument();
    expect(screen.getAllByText("No data yet")).toHaveLength(5);
    expect(screen.getByText("3 sites in view")).toBeInTheDocument();
    expect(screen.getByText("Decisions waiting for you")).toBeInTheDocument();
    expect(screen.getByText(/Good (morning|afternoon|evening), Nia/)).toBeInTheDocument();
  });
});
