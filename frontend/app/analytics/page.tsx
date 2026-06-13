"use client";
import { useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, CartesianGrid, PieChart, Pie, Legend,
} from "recharts";
import { api, type AnalyticsSummary, type Influencer } from "@/lib/api";
import StatTile from "@/components/StatTile";
import { CardSkeleton, Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";

const PALETTE = ["#6366f1","#8b5cf6","#10b981","#f59e0b","#ef4444","#06b6d4","#ec4899","#84cc16"];

interface ChartImg { kind: string; image: string }

const CHART_KINDS = [
  { id: "top_connected",     label: "Most Connected" },
  { id: "city_distribution", label: "City Distribution" },
  { id: "degree_distribution", label: "Degree Distribution" },
  { id: "friendship_growth", label: "Friendship Growth" },
  { id: "network_graph",     label: "Network Map" },
];

export default function AnalyticsPage() {
  const toast = useToast();
  const [summary, setSummary]       = useState<AnalyticsSummary | null>(null);
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [charts, setCharts]         = useState<Record<string, string>>({});
  const [loadingMain, setLoadingMain] = useState(true);
  const [loadingCharts, setLoadingCharts] = useState<Record<string, boolean>>({});
  const [activeChart, setActiveChart] = useState("top_connected");

  useEffect(() => {
    Promise.all([api.getAnalyticsSummary(), api.getInfluencers(10)])
      .then(([s, inf]) => { setSummary(s); setInfluencers(inf); })
      .catch(() => toast("Failed to load analytics", "error"))
      .finally(() => setLoadingMain(false));
  }, []);

  // Load chart lazily when tab is selected
  useEffect(() => {
    if (charts[activeChart]) return;
    setLoadingCharts(l => ({ ...l, [activeChart]: true }));
    api.getChart(activeChart)
      .then(r => setCharts(c => ({ ...c, [activeChart]: r.image })))
      .catch(() => toast(`Failed to load ${activeChart} chart`, "error"))
      .finally(() => setLoadingCharts(l => ({ ...l, [activeChart]: false })));
  }, [activeChart]);

  // Recharts data
  const infChartData = influencers.map(i => ({ name: i.name, degree: i.degree, betweenness: +(i.betweenness_approx * 100).toFixed(3) }));

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8 animate-fade-in">
      <div>
        <h1 className="text-3xl font-bold text-white">Analytics</h1>
        <p className="text-gray-400 text-sm mt-1">Network-wide metrics and visualisations</p>
      </div>

      {/* KPI row */}
      {loadingMain ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile label="Users"           value={summary?.total_users ?? 0} />
          <StatTile label="Friendships"     value={summary?.total_edges ?? 0}  accent="emerald" />
          <StatTile label="Components"      value={summary?.num_components ?? 0} accent="violet" />
          <StatTile label="Diameter"        value={summary?.diameter?.toFixed(1) ?? "—"} accent="amber" sub="longest shortest path" />
        </div>
      )}

      {/* Two-column: Recharts influencer chart + health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Influencer bar */}
        <div className="lg:col-span-2 bg-surface-700 rounded-xl p-5 border border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">
            Influencer Leaderboard
          </h2>
          {loadingMain ? <Skeleton className="h-52" /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={infChartData} margin={{ left: -15, right: 10 }}>
                <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#9ca3af", fontSize: 10 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#1a1a2e", border: "1px solid #ffffff10", borderRadius: 8, fontSize: 11 }}
                  cursor={{ fill: "#ffffff06" }}
                />
                <Bar dataKey="degree" name="Connections" radius={[4,4,0,0]}>
                  {infChartData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Health metrics */}
        <div className="bg-surface-700 rounded-xl p-5 border border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">Network Health</h2>
          {loadingMain ? (
            <div className="space-y-3">{[...Array(5)].map((_, i) => <Skeleton key={i} className="h-4" />)}</div>
          ) : (
            <dl className="space-y-4">
              {[
                ["Density",          `${((summary?.density ?? 0) * 100).toFixed(2)}%`, "of possible edges exist"],
                ["Avg Separation",   summary?.average_separation?.toFixed(3) ?? "—",   "mean shortest path"],
                ["Avg Degree",       summary?.degree_stats.mean.toFixed(2) ?? "—",     "friends per user"],
                ["Max Degree",       summary?.degree_stats.max ?? "—",                 "most connected user"],
                ["Largest Cluster",  summary?.largest_component_size ?? "—",           "users in top component"],
              ].map(([k, v, hint]) => (
                <div key={String(k)} className="flex justify-between items-end border-b border-white/5 pb-3 last:border-0 last:pb-0">
                  <div>
                    <dt className="text-xs font-medium text-gray-300">{k}</dt>
                    <dd className="text-xs text-gray-500 mt-0.5">{hint}</dd>
                  </div>
                  <span className="text-lg font-bold text-brand-400 tabular-nums">{v}</span>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>

      {/* Influencer table */}
      <div className="bg-surface-700 rounded-xl border border-white/5 overflow-hidden">
        <div className="p-5 border-b border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Top Influencers</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-white/5">
                <th className="px-5 py-3 text-left">Rank</th>
                <th className="px-5 py-3 text-left">Name</th>
                <th className="px-5 py-3 text-right">Connections</th>
                <th className="px-5 py-3 text-right">Betweenness</th>
                <th className="px-5 py-3 text-left">Influence Bar</th>
              </tr>
            </thead>
            <tbody>
              {loadingMain ? (
                [...Array(5)].map((_, i) => (
                  <tr key={i} className="border-b border-white/5">
                    <td colSpan={5} className="px-5 py-3"><Skeleton className="h-4 w-full" /></td>
                  </tr>
                ))
              ) : influencers.length === 0 ? (
                <tr><td colSpan={5} className="text-center py-8 text-gray-500">No users yet</td></tr>
              ) : influencers.map((inf, i) => {
                const maxDeg = influencers[0]?.degree || 1;
                return (
                  <tr key={inf.user_id} className="border-b border-white/5 hover:bg-surface-600/40 transition-colors">
                    <td className="px-5 py-3">
                      <span className={`text-xs font-bold ${i === 0 ? "text-amber-400" : i === 1 ? "text-gray-300" : i === 2 ? "text-amber-700" : "text-gray-500"}`}>
                        #{i + 1}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-medium text-white">{inf.name}</td>
                    <td className="px-5 py-3 text-right text-brand-400 font-semibold tabular-nums">{inf.degree}</td>
                    <td className="px-5 py-3 text-right text-gray-400 tabular-nums text-xs">{(inf.betweenness_approx * 100).toFixed(3)}%</td>
                    <td className="px-5 py-3 w-40">
                      <div className="bg-surface-600 rounded-full h-1.5 w-full">
                        <div
                          className="h-1.5 rounded-full transition-all"
                          style={{ width: `${(inf.degree / maxDeg) * 100}%`, background: PALETTE[i % PALETTE.length] }}
                        />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Matplotlib chart tabs */}
      <div className="bg-surface-700 rounded-xl border border-white/5 overflow-hidden">
        <div className="p-5 border-b border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-3">Static Charts</h2>
          <div className="flex gap-2 flex-wrap">
            {CHART_KINDS.map(c => (
              <button
                key={c.id}
                onClick={() => setActiveChart(c.id)}
                className={`text-xs px-3 py-1.5 rounded-lg transition-all font-medium ${
                  activeChart === c.id ? "bg-brand-600 text-white" : "bg-surface-600 text-gray-400 hover:text-white"
                }`}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <div className="p-5 flex items-center justify-center min-h-64">
          {loadingCharts[activeChart] ? (
            <div className="text-center">
              <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              <p className="text-xs text-gray-500">Generating chart…</p>
            </div>
          ) : charts[activeChart] ? (
            <img
              src={`data:image/png;base64,${charts[activeChart]}`}
              alt={activeChart}
              className="max-w-full rounded-lg"
            />
          ) : (
            <p className="text-gray-500 text-sm">Chart will appear here</p>
          )}
        </div>
      </div>
    </div>
  );
}
