import { z } from "zod";
import { ROLES } from "./roles";

export const roleSchema = z.enum(ROLES);

export const loginRequestSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password").max(256),
});
export type LoginRequest = z.infer<typeof loginRequestSchema>;

export const totpCodeSchema = z
  .string()
  .trim()
  .regex(/^\d{6}$/, "Enter the 6-digit code from your authenticator app");

export const mfaVerifyRequestSchema = z.object({
  mfa_token: z.string().min(1),
  code: totpCodeSchema,
});
export type MfaVerifyRequest = z.infer<typeof mfaVerifyRequestSchema>;

export const membershipSchema = z.object({
  organisation_id: z.string().uuid(),
  organisation_name: z.string(),
  site_id: z.string().uuid().nullable(),
  role: roleSchema,
});
export type Membership = z.infer<typeof membershipSchema>;

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  full_name: z.string(),
  mfa_enabled: z.boolean(),
  memberships: z.array(membershipSchema),
});
export type User = z.infer<typeof userSchema>;

const sessionSchema = z.object({
  access_token: z.string(),
  expires_in: z.number().int().positive(),
  /** Only returned to mobile clients; web gets an httpOnly cookie instead. */
  refresh_token: z.string().nullable().optional(),
  user: userSchema,
});

export const sessionResponseSchema = sessionSchema.extend({ status: z.literal("ok") });
export type SessionResponse = z.infer<typeof sessionResponseSchema>;

export const loginResponseSchema = z.discriminatedUnion("status", [
  sessionResponseSchema,
  z.object({ status: z.literal("mfa_required"), mfa_token: z.string() }),
  z.object({
    status: z.literal("mfa_setup_required"),
    mfa_token: z.string(),
    otpauth_uri: z.string(),
    secret: z.string(),
    qr_svg: z.string(),
  }),
]);
export type LoginResponse = z.infer<typeof loginResponseSchema>;

export const trustLevelSchema = z.enum(["high", "medium", "low", "none"]);
export type TrustLevel = z.infer<typeof trustLevelSchema>;

export const kpiTileSchema = z.object({
  key: z.string(),
  label: z.string(),
  value: z.number().nullable(),
  unit: z.string(),
  trend: z.enum(["up", "down", "flat"]).nullable(),
  /** Whether "up" is good for this KPI (e.g. availability) or bad (e.g. SAIDI). */
  higher_is_better: z.boolean(),
  trust: trustLevelSchema,
});
export type KpiTile = z.infer<typeof kpiTileSchema>;

export const dashboardHomeSchema = z.object({
  organisations: z.array(z.object({ id: z.string().uuid(), name: z.string() })),
  site_count: z.number().int().nonnegative(),
  kpis: z.array(kpiTileSchema),
  decisions_waiting: z.array(z.unknown()),
  top_risks: z.array(z.unknown()),
  what_changed: z.array(z.string()),
});
export type DashboardHome = z.infer<typeof dashboardHomeSchema>;
