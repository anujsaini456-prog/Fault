export const ROLES = ["executive", "analyst", "engineer", "admin"] as const;
export type Role = (typeof ROLES)[number];

/** Human-readable labels for executive-facing UI. */
export const ROLE_LABELS: Record<Role, string> = {
  executive: "Executive",
  analyst: "Analyst",
  engineer: "Engineer",
  admin: "Administrator",
};

/** Roles that must use TOTP MFA (spec §7). */
export const MFA_REQUIRED_ROLES: readonly Role[] = ["admin"];

export function hasAnyRole(userRoles: readonly Role[], allowed: readonly Role[]): boolean {
  return userRoles.some((r) => allowed.includes(r));
}
