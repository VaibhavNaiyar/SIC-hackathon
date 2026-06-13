"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type GraphData, type GraphNode, type User } from "@/lib/api";
import { useToast } from "@/components/Toast";

// Force graph must be client-only (no SSR) — it uses browser canvas APIs
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const COMMUNITY_COLORS = [
  "#6366f1","#10b981","#f59e0b","#ef4444","#8b5cf6",
  "#06b6d4","#ec4899","#84cc16","#f97316","#14b8a6",
];

function communityColor(id: number) {
  return COMMUNITY_COLORS[id % COMMUNITY_COLORS.length];
}

export default function NetworkPage() {
  const toast  = useToast();
  const fgRef  = useRef<any>(null);

  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], edges: [] });
  const [users, setUsers]         = useState<User[]>([]);
  const [loading, setLoading]     = useState(true);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);

  // Path finder state
  const [fromId, setFromId]       = useState("");
  const [toId, setToId]           = useState("");
  const [pathResult, setPathResult] = useState<string[] | null>(null);
  const [pathInfo, setPathInfo]   = useState<{ hops: number; degrees: string } | null>(null);
  const [allPaths, setAllPaths]   = useState<string[][]>([]);
  const [showAllPaths, setShowAllPaths] = useState(false);
  const [finding, setFinding]     = useState(false);
  const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set());
  const [highlightLinks, setHighlightLinks] = useState<Set<string>>(new Set());

  // Recommendations state
  const [recUser, setRecUser]     = useState("");
  const [recs, setRecs]           = useState<any[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [g, u] = await Promise.all([api.getGraph(), api.listUsers()]);
      setGraphData(g);
      setUsers(u);
    } catch {
      toast("Failed to load graph", "error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Build force-graph compatible data
  const fgNodes = graphData.nodes.map(n => ({
    ...n,
    color: communityColor(n.community),
  }));
  const fgLinks = graphData.edges.map(e => ({
    source: e.source,
    target: e.target,
    id: `${e.source}-${e.target}`,
  }));

  const findPath = async () => {
    if (!fromId || !toId) { toast("Select both users", "error"); return; }
    setFinding(true);
    setPathResult(null);
    setPathInfo(null);
    setAllPaths([]);
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());
    try {
      const [shortest, all] = await Promise.all([
        api.getShortestPath(fromId, toId),
        api.getAllPaths(fromId, toId, 4),
      ]);
      setPathInfo({ hops: shortest.hops, degrees: shortest.degrees });
      setAllPaths(all.paths);

      if (shortest.path) {
        setPathResult(shortest.path);
        const hn = new Set(shortest.path);
        const hl = new Set<string>();
        for (let i = 0; i < shortest.path.length - 1; i++) {
          hl.add(`${shortest.path[i]}-${shortest.path[i+1]}`);
          hl.add(`${shortest.path[i+1]}-${shortest.path[i]}`);
        }
        setHighlightNodes(hn);
        setHighlightLinks(hl);
        // Zoom to fit highlighted subgraph
        setTimeout(() => fgRef.current?.zoomToFit(400, 80), 300);
      } else {
        toast("No path — users are in different components", "info");
      }
    } catch (err: any) {
      toast(err?.detail ?? "Path search failed", "error");
    } finally {
      setFinding(false);
    }
  };

  const clearPath = () => {
    setPathResult(null);
    setPathInfo(null);
    setAllPaths([]);
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());
    setFromId("");
    setToId("");
  };

  const loadRecs = async () => {
    if (!recUser) return;
    setLoadingRecs(true);
    try {
      const r = await api.getRecommendations(recUser, 5);
      setRecs(r);
    } catch {
      toast("Failed to load recommendations", "error");
    } finally { setLoadingRecs(false); }
  };

  useEffect(() => { if (recUser) loadRecs(); }, [recUser]);

  const userName = (id: string) => users.find(u => u.user_id === id)?.name ?? id;

  // Node paint callback
  const paintNode = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const r = Math.max(4, (node.degree ?? 0) * 1.5 + 5);
    const isHighlighted = highlightNodes.has(node.id);
    const isHovered     = hoveredNode?.id === node.id;

    // Glow for highlighted nodes
    if (isHighlighted) {
      ctx.beginPath();
      ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
      ctx.fillStyle = "rgba(99,102,241,0.3)";
      ctx.fill();
    }

    // Node circle
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = isHighlighted ? "#818cf8" : isHovered ? "#a78bfa" : node.color;
    ctx.fill();

    // Border
    ctx.strokeStyle = isHighlighted ? "#6366f1" : "rgba(255,255,255,0.15)";
    ctx.lineWidth = isHighlighted ? 2.5 : 1;
    ctx.stroke();

    // Label at higher zoom
    if (globalScale >= 1.5 || isHighlighted || isHovered) {
      const label = node.name;
      ctx.font = `${Math.max(8, 12 / globalScale)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.fillStyle = "rgba(255,255,255,0.85)";
      ctx.fillText(label, node.x, node.y - r - 2);
    }
  }, [highlightNodes, hoveredNode]);

  const linkColor = useCallback((link: any) => {
    const id1 = `${link.source.id ?? link.source}-${link.target.id ?? link.target}`;
    const id2 = `${link.target.id ?? link.target}-${link.source.id ?? link.source}`;
    return (highlightLinks.has(id1) || highlightLinks.has(id2))
      ? "#818cf8"
      : "rgba(255,255,255,0.08)";
  }, [highlightLinks]);

  const linkWidth = useCallback((link: any) => {
    const id1 = `${link.source.id ?? link.source}-${link.target.id ?? link.target}`;
    const id2 = `${link.target.id ?? link.target}-${link.source.id ?? link.source}`;
    return (highlightLinks.has(id1) || highlightLinks.has(id2)) ? 2.5 : 1;
  }, [highlightLinks]);

  return (
    <div className="flex h-[calc(100vh-56px)]">
      {/* Sidebar */}
      <div className="w-80 shrink-0 bg-surface-800 border-r border-white/5 overflow-y-auto flex flex-col">
        {/* Path finder */}
        <div className="p-4 border-b border-white/5">
          <h2 className="font-semibold text-white mb-3 text-sm">🔍 Path Finder</h2>
          <div className="space-y-2">
            <select className="input text-xs py-1.5" value={fromId} onChange={e => setFromId(e.target.value)}>
              <option value="">From user…</option>
              {users.map(u => <option key={u.user_id} value={u.user_id}>{u.name}</option>)}
            </select>
            <select className="input text-xs py-1.5" value={toId} onChange={e => setToId(e.target.value)}>
              <option value="">To user…</option>
              {users.filter(u => u.user_id !== fromId).map(u =>
                <option key={u.user_id} value={u.user_id}>{u.name}</option>
              )}
            </select>
            <div className="flex gap-2">
              <button onClick={findPath} disabled={finding || !fromId || !toId} className="btn-primary flex-1 text-xs py-1.5">
                {finding ? "Searching…" : "Find Path"}
              </button>
              {pathResult && <button onClick={clearPath} className="btn-secondary text-xs px-2 py-1.5">✕</button>}
            </div>
          </div>

          {/* Path result */}
          {pathInfo && (
            <div className="mt-3 bg-surface-600 rounded-lg p-3 animate-slide-up">
              <div className="flex items-center justify-between mb-2">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${
                  pathResult ? "bg-emerald-600/30 text-emerald-400" : "bg-red-600/30 text-red-400"
                }`}>
                  {pathResult ? pathInfo.degrees : "Not connected"}
                </span>
                {pathResult && (
                  <span className="text-xs text-gray-400">{pathInfo.hops} hop{pathInfo.hops !== 1 ? "s" : ""}</span>
                )}
              </div>
              {pathResult && (
                <div className="flex flex-wrap items-center gap-1 text-xs">
                  {pathResult.map((id, i) => (
                    <span key={id} className="flex items-center gap-1">
                      <span className="bg-brand-600/40 text-brand-300 px-2 py-0.5 rounded-full font-medium">
                        {userName(id)}
                      </span>
                      {i < pathResult.length - 1 && <span className="text-gray-600">→</span>}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* All paths toggle */}
          {allPaths.length > 0 && (
            <div className="mt-2">
              <button
                onClick={() => setShowAllPaths(s => !s)}
                className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
              >
                {showAllPaths ? "▲" : "▼"} {allPaths.length} total path{allPaths.length !== 1 ? "s" : ""}
              </button>
              {showAllPaths && (
                <div className="mt-2 space-y-1.5 max-h-40 overflow-y-auto">
                  {allPaths.map((p, i) => (
                    <div key={i} className="text-xs bg-surface-700 rounded p-2 text-gray-300">
                      {p.map(id => userName(id)).join(" → ")}
                      <span className="text-gray-500 ml-1">({p.length - 1} hops)</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Recommendations */}
        <div className="p-4 border-b border-white/5">
          <h2 className="font-semibold text-white mb-3 text-sm">💡 Recommendations</h2>
          <select className="input text-xs py-1.5 mb-3" value={recUser} onChange={e => setRecUser(e.target.value)}>
            <option value="">Select a user…</option>
            {users.map(u => <option key={u.user_id} value={u.user_id}>{u.name}</option>)}
          </select>
          {loadingRecs ? (
            <div className="space-y-2">{[...Array(3)].map((_, i) => <div key={i} className="h-12 bg-surface-600 rounded animate-pulse" />)}</div>
          ) : recs.length > 0 ? (
            <div className="space-y-2">
              {recs.map(r => (
                <div key={r.candidate_id} className="bg-surface-600 rounded-lg p-3 text-xs animate-slide-up">
                  <div className="flex justify-between items-start mb-1">
                    <span className="font-semibold text-white">{r.candidate_name}</span>
                    <span className="text-brand-400 font-mono">+{r.why.score.toFixed(1)}</span>
                  </div>
                  <div className="text-gray-400 space-y-0.5">
                    {r.why.mutuals.length > 0 && (
                      <p>👥 {r.why.mutuals.length} mutual friend{r.why.mutuals.length !== 1 ? "s" : ""}</p>
                    )}
                    {r.why.shared_interests.length > 0 && (
                      <p>🎯 {r.why.shared_interests.join(", ")}</p>
                    )}
                    {r.why.same_city && <p>📍 Same city</p>}
                  </div>
                </div>
              ))}
            </div>
          ) : recUser ? (
            <p className="text-xs text-gray-500 text-center py-4">No recommendations available</p>
          ) : null}
        </div>

        {/* Legend */}
        <div className="p-4 mt-auto">
          <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Communities</p>
          <div className="flex flex-wrap gap-2">
            {Array.from(new Set(graphData.nodes.map(n => n.community))).slice(0, 6).map(c => (
              <span key={c} className="flex items-center gap-1.5 text-xs text-gray-400">
                <span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: communityColor(c) }} />
                #{c}
              </span>
            ))}
          </div>
          <p className="text-xs text-gray-600 mt-3">
            {graphData.nodes.length} nodes · {graphData.edges.length} edges
          </p>
          <button onClick={load} className="btn-secondary text-xs w-full mt-2 py-1.5">↻ Refresh</button>
        </div>
      </div>

      {/* Force graph canvas */}
      <div className="flex-1 relative bg-surface-900">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center z-10">
            <div className="text-center">
              <div className="w-10 h-10 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
              <p className="text-gray-400 text-sm">Loading graph…</p>
            </div>
          </div>
        )}

        {!loading && graphData.nodes.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="text-center text-gray-500">
              <p className="text-5xl mb-4">🕸</p>
              <p className="text-lg font-medium text-gray-400">Empty Network</p>
              <p className="text-sm mt-1">Register users and accept friend requests to see the graph</p>
            </div>
          </div>
        )}

        {!loading && graphData.nodes.length > 0 && (
          <ForceGraph2D
            ref={fgRef}
            graphData={{ nodes: fgNodes, links: fgLinks }}
            nodeId="id"
            linkSource="source"
            linkTarget="target"
            backgroundColor="#0f0f1a"
            nodeCanvasObject={paintNode}
            nodeCanvasObjectMode={() => "replace"}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkDirectionalParticles={2}
            linkDirectionalParticleWidth={(link: any) => {
              const id1 = `${link.source.id ?? link.source}-${link.target.id ?? link.target}`;
              const id2 = `${link.target.id ?? link.target}-${link.source.id ?? link.source}`;
              return (highlightLinks.has(id1) || highlightLinks.has(id2)) ? 3 : 0;
            }}
            linkDirectionalParticleColor={() => "#818cf8"}
            onNodeHover={(node: any) => setHoveredNode(node ?? null)}
            onNodeClick={(node: any) => {
              fgRef.current?.centerAt(node.x, node.y, 500);
              fgRef.current?.zoom(3, 500);
            }}
            cooldownTicks={80}
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
          />
        )}

        {/* Hover tooltip */}
        {hoveredNode && (
          <div className="absolute top-4 right-4 bg-surface-700/95 backdrop-blur rounded-xl p-4 border border-white/10 text-sm max-w-xs pointer-events-none animate-fade-in">
            <p className="font-semibold text-white mb-1">{hoveredNode.name}</p>
            <p className="text-xs text-gray-400">{hoveredNode.city} · age {hoveredNode.age}</p>
            <p className="text-xs text-gray-400 mt-1">{hoveredNode.degree} {hoveredNode.degree === 1 ? "friend" : "friends"} · community #{hoveredNode.community}</p>
            {hoveredNode.interests.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {hoveredNode.interests.map((i: string) => (
                  <span key={i} className="text-xs bg-brand-600/30 text-brand-300 rounded-full px-1.5 py-0.5">{i}</span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
