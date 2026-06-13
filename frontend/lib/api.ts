// Typed API client — one function per endpoint, central error handling.

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────────

export interface User {
  user_id: string;
  name: string;
  age: number;
  city: string;
  interests: string[];
  degree: number;
}

export interface FriendRequest {
  from_id: string;
  to_id: string;
  status: "PENDING" | "ACCEPTED" | "REJECTED";
}

export interface PathResult {
  path: string[] | null;
  hops: number;
  degrees: string;
  connected: boolean;
}

export interface AllPathsResult {
  paths: string[][];
  count: number;
}

export interface MutualFriendsResult {
  user_a: string;
  user_b: string;
  mutual_friends: string[];
  count: number;
  jaccard_similarity: number;
}

export interface RecommendationWhy {
  mutuals: string[];
  shared_interests: string[];
  same_city: boolean;
  score: number;
}

export interface Recommendation {
  candidate_id: string;
  candidate_name: string;
  why: RecommendationWhy;
}

export interface AnalyticsSummary {
  total_users: number;
  total_edges: number;
  density: number;
  num_components: number;
  largest_component_size: number;
  diameter: number;
  average_separation: number;
  degree_stats: { mean: number; median: number; max: number; min: number };
}

export interface Influencer {
  user_id: string;
  name: string;
  degree: number;
  betweenness_approx: number;
}

export interface GraphNode {
  id: string;
  name: string;
  age: number;
  city: string;
  interests: string[];
  degree: number;
  community: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ApiError {
  error: string;
  detail: string;
}

// ── Core fetch wrapper ─────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let body: ApiError = { error: "REQUEST_FAILED", detail: res.statusText };
    try { body = await res.json(); } catch { /* ignore */ }
    throw body;
  }
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Users ──────────────────────────────────────────────────────────────────────

export const api = {
  // Users
  createUser: (data: { name: string; age: number; city: string; interests: string[] }) =>
    apiFetch<User>("/users", { method: "POST", body: JSON.stringify(data) }),

  listUsers: (filters?: { city?: string; interest?: string }) => {
    const params = new URLSearchParams();
    if (filters?.city) params.set("city", filters.city);
    if (filters?.interest) params.set("interest", filters.interest);
    const qs = params.toString();
    return apiFetch<User[]>(`/users${qs ? `?${qs}` : ""}`);
  },

  getUser: (id: string) => apiFetch<User>(`/users/${id}`),

  deleteUser: (id: string) => apiFetch<void>(`/users/${id}`, { method: "DELETE" }),

  getFriends: (id: string) => apiFetch<User[]>(`/users/${id}/friends`),

  removeFriendship: (a: string, b: string) =>
    apiFetch<void>(`/users/${a}/friends/${b}`, { method: "DELETE" }),

  // Friend Requests
  sendRequest: (from_id: string, to_id: string) =>
    apiFetch<FriendRequest>("/requests", {
      method: "POST",
      body: JSON.stringify({ from_id, to_id }),
    }),

  acceptRequest: (from_id: string, to_id: string) =>
    apiFetch<FriendRequest>(
      `/requests/${from_id}/accept?to_id=${encodeURIComponent(to_id)}`,
      { method: "POST" }
    ),

  rejectRequest: (from_id: string, to_id: string) =>
    apiFetch<FriendRequest>(
      `/requests/${from_id}/reject?to_id=${encodeURIComponent(to_id)}`,
      { method: "POST" }
    ),

  getPendingRequests: (user_id: string) =>
    apiFetch<FriendRequest[]>(`/users/${user_id}/requests`),

  // Social
  getMutualFriends: (a: string, b: string) =>
    apiFetch<MutualFriendsResult>(`/users/${a}/mutual/${b}`),

  getRecommendations: (user_id: string, top_k = 5) =>
    apiFetch<Recommendation[]>(`/users/${user_id}/recommendations?top_k=${top_k}`),

  // Paths
  getShortestPath: (from: string, to: string) =>
    apiFetch<PathResult>(`/path?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`),

  getAllPaths: (from: string, to: string, max_depth = 4) =>
    apiFetch<AllPathsResult>(
      `/paths?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}&max_depth=${max_depth}`
    ),

  // Analytics
  getAnalyticsSummary: () => apiFetch<AnalyticsSummary>("/analytics/summary"),

  getInfluencers: (top_n = 5) =>
    apiFetch<Influencer[]>(`/analytics/influencers?top_n=${top_n}`),

  getChart: (kind: string) =>
    apiFetch<{ kind: string; image: string; format: string; encoding: string }>(
      `/analytics/charts/${kind}`
    ),

  // Graph
  getGraph: () => apiFetch<GraphData>("/graph"),

  // Health
  health: () => apiFetch<{ status: string; users: number; edges: number }>("/health"),
};
