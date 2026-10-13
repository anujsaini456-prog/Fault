import { ROLE_LABELS, type DashboardHome, type KpiTile, type TrustLevel } from "@fault-sigma/core";
import { useQuery } from "@tanstack/react-query";
import { usePreventScreenCapture } from "expo-screen-capture";
import { Pressable, RefreshControl, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, useAuth } from "../src/auth";
import { getCachedHome, setCachedHome } from "../src/secure";
import { usePalette, type Palette } from "../src/theme";

/** Online: fetch and cache. Offline: show the last synced copy, clearly labelled. */
async function loadHome(): Promise<{ home: DashboardHome; offlineSince: string | null }> {
  try {
    const home = await api.dashboardHome();
    await setCachedHome(home);
    return { home, offlineSince: null };
  } catch (e) {
    const cached = await getCachedHome();
    if (cached) return { home: cached.home, offlineSince: cached.savedAt };
    throw e;
  }
}

export default function HomeScreen() {
  usePreventScreenCapture(); // executive data: no screenshots or screen recording
  const { state, signOut } = useAuth();
  const c = usePalette();
  const q = useQuery({ queryKey: ["dashboard-home"], queryFn: loadHome });
  if (state.status !== "signed-in") return null;
  const { user } = state;
  const home = q.data?.home;
  const roles = [...new Set(user.memberships.map((m) => ROLE_LABELS[m.role]))].join(", ");

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }} edges={["top"]}>
      <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }}
        refreshControl={<RefreshControl refreshing={q.isFetching} onRefresh={() => void q.refetch()} />}>
        <View style={{ flexDirection: "row", alignItems: "flex-start", gap: 12 }}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: c.text, fontSize: 22, fontWeight: "700" }}>
              Hello, {user.full_name.split(" ")[0]}
            </Text>
            <Text style={{ color: c.muted, fontSize: 13 }} numberOfLines={1}>
              {home?.organisations.map((o) => o.name).join(" · ") ?? "…"} · {roles}
            </Text>
          </View>
          <Pressable accessibilityRole="button" onPress={() => void signOut()} hitSlop={12}>
            <Text style={{ color: c.muted, fontWeight: "500" }}>Sign out</Text>
          </Pressable>
        </View>

        {q.data?.offlineSince ? (
          <Banner c={c} text={`Offline — showing data from ${new Date(q.data.offlineSince).toLocaleString()}`} />
        ) : null}
        {q.isError ? <Banner c={c} text="Couldn't load the dashboard. Pull down to retry." danger /> : null}

        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 10 }}>
          {(home?.kpis ?? []).map((k) => <Kpi key={k.key} kpi={k} c={c} />)}
        </View>

        <Section c={c} title="Decisions waiting for you" body="Nothing needs your approval right now." />
        <Section c={c} title="Top 5 risks" body="Risk ranking appears once fault history is loaded." />
        <Section c={c} title="What changed this week" body={(home?.what_changed ?? []).join("\n")} />
      </ScrollView>
    </SafeAreaView>
  );
}

const TRUST: Record<TrustLevel, string> = { high: "High trust", medium: "Medium trust", low: "Low trust", none: "No data yet" };

function Kpi({ kpi, c }: { kpi: KpiTile; c: Palette }) {
  return (
    <View accessible accessibilityLabel={`${kpi.label}: ${kpi.value ?? "no data yet"}`}
      style={{ flexBasis: "47%", flexGrow: 1, backgroundColor: c.card, borderColor: c.border, borderWidth: 1, borderRadius: 14, padding: 12, gap: 6 }}>
      <Text style={{ color: c.muted, fontSize: 12 }}>{kpi.label}</Text>
      <Text style={{ color: kpi.value === null ? c.border : c.text, fontSize: 24, fontWeight: "700" }}>
        {kpi.value === null ? "—" : `${kpi.value}${kpi.unit ? ` ${kpi.unit}` : ""}`}
      </Text>
      <Text style={{ alignSelf: "flex-start", fontSize: 11, color: c.muted, backgroundColor: c.chip, paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, overflow: "hidden" }}>
        {TRUST[kpi.trust]}
      </Text>
    </View>
  );
}

function Section({ c, title, body }: { c: Palette; title: string; body: string }) {
  return (
    <View style={{ backgroundColor: c.card, borderColor: c.border, borderWidth: 1, borderRadius: 14, padding: 14, gap: 8 }}>
      <Text style={{ color: c.text, fontWeight: "600", fontSize: 16 }}>{title}</Text>
      <Text style={{ color: c.muted }}>{body}</Text>
    </View>
  );
}

function Banner({ c, text, danger = false }: { c: Palette; text: string; danger?: boolean }) {
  return (
    <Text style={{ color: danger ? c.danger : c.text, backgroundColor: danger ? c.dangerBg : c.chip, padding: 10, borderRadius: 8 }}>
      {text}
    </Text>
  );
}
