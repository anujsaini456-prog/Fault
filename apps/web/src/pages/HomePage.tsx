import { ROLE_LABELS, type DashboardHome, type KpiTile, type TrustLevel, type User } from "@fault-sigma/core";
import { useQuery } from "@tanstack/react-query";
import { Logo } from "../components/Logo";
import { ThemeToggle } from "../components/ThemeToggle";

interface Props {
  user: User;
  loadHome: () => Promise<DashboardHome>;
  onSignOut: () => void;
}

/** Executive home (spec §9): KPIs first, then decisions, risks and a plain-English summary. */
export function HomePage({ user, loadHome, onSignOut }: Props) {
  const home = useQuery({ queryKey: ["dashboard-home"], queryFn: loadHome });
  const firstName = user.full_name.split(" ")[0] ?? user.full_name;
  const roles = [...new Set(user.memberships.map((m) => ROLE_LABELS[m.role]))].join(", ");

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <Logo className="h-8 w-8" />
          <div className="min-w-0 flex-1">
            <p className="truncate font-semibold">{home.data?.organisations.map((o) => o.name).join(" · ") ?? "Fault Sigma"}</p>
            <p className="truncate text-xs text-slate-500">{user.email} · {roles}</p>
          </div>
          <ThemeToggle />
          <button onClick={onSignOut} className="rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800">
            Sign out
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        <div>
          <h1 className="text-2xl font-bold">Good {greeting()}, {firstName}</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {home.data ? `${home.data.site_count} site${home.data.site_count === 1 ? "" : "s"} in view` : " "}
          </p>
        </div>

        {home.isError ? (
          <div role="alert" className="card border-red-200 text-red-700 dark:border-red-900 dark:text-red-300">
            Couldn't load the dashboard. <button className="underline" onClick={() => home.refetch()}>Try again</button>
          </div>
        ) : null}

        <section aria-labelledby="kpi-heading">
          <h2 id="kpi-heading" className="sr-only">Key indicators</h2>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
            {(home.data?.kpis ?? placeholderKpis).map((k) => (
              <KpiCard key={k.key} kpi={k} loading={home.isPending} />
            ))}
          </div>
        </section>

        <div className="grid gap-6 lg:grid-cols-3">
          <Panel title="Decisions waiting for you" empty="Nothing needs your approval right now." items={home.data?.decisions_waiting} />
          <Panel title="Top 5 risks" empty="Risk ranking appears once fault history is loaded." items={home.data?.top_risks} />
          <section className="card">
            <h2 className="mb-3 font-semibold">What changed this week</h2>
            <ul className="space-y-2 text-sm text-slate-600 dark:text-slate-300">
              {(home.data?.what_changed ?? []).map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          </section>
        </div>
      </main>
    </div>
  );
}

const placeholderKpis: KpiTile[] = Array.from({ length: 5 }, (_, i) => ({
  key: `p${i}`, label: "", value: null, unit: "", trend: null, higher_is_better: true, trust: "none",
}));

const TRUST: Record<TrustLevel, { label: string; cls: string }> = {
  high: { label: "High trust", cls: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" },
  medium: { label: "Medium trust", cls: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" },
  low: { label: "Low trust", cls: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300" },
  none: { label: "No data yet", cls: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400" },
};

function KpiCard({ kpi, loading }: { kpi: KpiTile; loading: boolean }) {
  if (loading) return <div className="card h-28 animate-pulse" aria-hidden="true" />;
  const trust = TRUST[kpi.trust];
  const good = kpi.trend === null || kpi.trend === "flat" ? null : (kpi.trend === "up") === kpi.higher_is_better;
  return (
    <article className="card flex flex-col justify-between gap-2">
      <h3 className="text-xs font-medium leading-snug text-slate-500 dark:text-slate-400">{kpi.label}</h3>
      <p className="text-2xl font-bold tabular-nums">
        {kpi.value === null ? <span className="text-slate-300 dark:text-slate-600">—</span> : `${kpi.value}${kpi.unit ? ` ${kpi.unit}` : ""}`}
        {kpi.trend ? (
          <span className={`ml-2 text-base ${good === null ? "text-slate-400" : good ? "text-emerald-600" : "text-red-600"}`}
            aria-label={`Trend ${kpi.trend}`}>
            {kpi.trend === "up" ? "▲" : kpi.trend === "down" ? "▼" : "▬"}
          </span>
        ) : null}
      </p>
      <span className={`w-fit rounded-full px-2 py-0.5 text-[11px] font-medium ${trust.cls}`}>{trust.label}</span>
    </article>
  );
}

function Panel({ title, empty, items }: { title: string; empty: string; items: unknown[] | undefined }) {
  return (
    <section className="card">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {items && items.length > 0 ? null : <p className="text-sm text-slate-500 dark:text-slate-400">{empty}</p>}
    </section>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}
