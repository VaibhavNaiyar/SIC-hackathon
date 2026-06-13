"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { api, type AnalyticsSummary, type Influencer, type User } from "@/lib/api";
import StatTile from "@/components/StatTile";
import { CardSkeleton } from "@/components/Skeleton";

const COLORS = ["#6366f1","#8b5cf6","#a78bfa","#818cf8","#c4b5fd"];

export default function DashboardPage() {
  const [summary, setSummary]       = useState<AnalyticsSummary | null>(null);
  const [influencers, setInfluencers] = useState<Influencer[]>([]);
  const [users, setUsers]           = useState<User[]>([]);
  const [loading, setLoading]       = useState(true);
  const [error, setError]           = useState("");

  useEffect(() => {
    Promise.all([api.getAnalyticsSummary(), api.getInfluencers(8), api.listUsers()])
      .then(([s, inf, u]) => { setSummary(s); setInfluencers(inf); setUsers(u); })
      .catch(() => setError("Backend offline — start the API server."))
      .finally(() => setLoading(false));
  }, []);

  const chartData = influencers.map(i => ({ name: i.name, friends: i.degree }));
  const recentUsers = [...users].slice(-5).reverse();

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 space-y-8 animate-fade-in">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold text-white">Network Dashboard</h1>
        <p className="text-gray-400 mt-1">Real-time overview of your social graph</p>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-500/40 rounded-xl p-4 text-red-300 text-sm">
          ⚠ {error}
        </div>
      )}

      {/* KPI tiles */}
      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => <CardSkeleton key={i} />)}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatTile label="Total Users"      value={summary?.total_users ?? 0}  sub="registered members" />
          <StatTile label="Friendships"      value={summary?.total_edges ?? 0}  sub="active connections" accent="emerald" />
          <StatTile label="Network Density"  value={summary ? `${(summary.density * 100).toFixed(1)}%` : "—"} sub="connectedness ratio" accent="violet" />
          <StatTile label="Avg Separation"   value={summary?.average_separation?.toFixed(2) ?? "—"} sub="degrees of separation" accent="amber" />
        </div>
      )}

      {/* Influencer bar chart + health */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-surface-700 rounded-xl p-5 border border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">
            Top Influencers by Degree
          </h2>
          {loading ? (
            <div className="h-48 animate-pulse bg-surface-600 rounded-lg" />
          ) : chartData.length === 0 ? (
            <div className="h-48 flex items-center justify-center text-gray-500 text-sm">
              No users yet — <Link href="/users" className="text-brand-400 ml-1">add some</Link>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={chartData} margin={{ top: 0, right: 10, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fill: "#9ca3af", fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: "#9ca3af", fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{ background: "#1a1a2e", border: "1px solid #ffffff10", borderRadius: 8, fontSize: 12 }}
                  labelStyle={{ color: "#e5e7eb" }}
                  cursor={{ fill: "#ffffff08" }}
                />
                <Bar dataKey="friends" radius={[4, 4, 0, 0]}>
                  {chartData.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {/* Network health */}
        <div className="bg-surface-700 rounded-xl p-5 border border-white/5 space-y-4">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest">Network Health</h2>
          {loading ? (
            <div className="space-y-3">{[...Array(4)].map((_, i) => <div key={i} className="h-4 bg-surface-600 rounded animate-pulse" />)}</div>
          ) : (
            <dl className="space-y-3">
              {[
                ["Diameter",    summary?.diameter?.toFixed(1) ?? "—",     "longest shortest path"],
                ["Components",  summary?.num_components ?? "—",            "connected clusters"],
                ["Largest",     summary?.largest_component_size ?? "—",    "users in biggest cluster"],
                ["Avg Degree",  summary?.degree_stats.mean.toFixed(2) ?? "—", "friends per user"],
              ].map(([k, v, hint]) => (
                <div key={String(k)} className="flex items-center justify-between">
                  <div>
                    <dt className="text-xs text-gray-500">{k}</dt>
                    <dd className="text-xs text-gray-600">{hint}</dd>
                  </div>
                  <span className="text-lg font-bold text-brand-400">{v}</span>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>

      {/* Quick actions + recent users */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Quick actions */}
        <div className="bg-surface-700 rounded-xl p-5 border border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">Quick Actions</h2>
          <div className="grid grid-cols-2 gap-3">
            {[
              { href: "/users",     icon: "👤", label: "Register User",    color: "bg-brand-600/20 text-brand-300" },
              { href: "/requests",  icon: "📬", label: "Send Request",     color: "bg-violet-600/20 text-violet-300" },
              { href: "/network",   icon: "🕸", label: "Find Path",        color: "bg-cyan-600/20 text-cyan-300" },
              { href: "/analytics", icon: "📊", label: "View Analytics",   color: "bg-emerald-600/20 text-emerald-300" },
            ].map(a => (
              <Link key={a.href} href={a.href}
                className={`${a.color} rounded-xl p-4 flex flex-col gap-2 hover:opacity-90 transition-opacity border border-white/5`}>
                <span className="text-2xl">{a.icon}</span>
                <span className="text-sm font-semibold">{a.label}</span>
              </Link>
            ))}
          </div>
        </div>

        {/* Recent users */}
        <div className="bg-surface-700 rounded-xl p-5 border border-white/5">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-widest mb-4">
            Recently Added
          </h2>
          {loading ? (
            <div className="space-y-2">{[...Array(3)].map((_, i) => <div key={i} className="h-10 bg-surface-600 rounded animate-pulse" />)}</div>
          ) : recentUsers.length === 0 ? (
            <p className="text-gray-500 text-sm text-center py-8">No users yet</p>
          ) : (
            <ul className="space-y-2">
              {recentUsers.map(u => (
                <li key={u.user_id} className="flex items-center gap-3 p-2 rounded-lg hover:bg-surface-600 transition-colors">
                  <div className="w-8 h-8 bg-brand-700 rounded-full flex items-center justify-center text-sm font-bold text-white">
                    {u.name[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-white truncate">{u.name}</p>
                    <p className="text-xs text-gray-500">{u.city} · {u.degree} {u.degree === 1 ? "friend" : "friends"}</p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
