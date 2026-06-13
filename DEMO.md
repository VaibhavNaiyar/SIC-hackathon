# Demo Walkthrough Script

Evaluation guide — follow these steps in order to exercise every feature.
Expected time: ~10 minutes.

---

## Setup (30 seconds)

```bash
# Terminal 1 — Backend
cd social-graph/backend
python seed.py                          # load 30-user demo network
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd social-graph/frontend
npm run dev
```

Open **http://localhost:3000**

---

## Step 1 — Dashboard

- KPI tiles show: **30 users**, **59 friendships**, density, avg separation
- Recharts bar — top influencers by degree (David Kim leads with 6 friends)
- Network Health panel — diameter = 5, 2 components, avg degree ≈ 3.93
- Note: the Houston cluster is a **separate component** (demonstrates disconnected graph handling)

---

## Step 2 — Register a User (`/users`)

1. Fill in: Name = **"Test User"**, Age = **22**, City = **"New York"**
2. Add interests: type `music` → press `+`, type `hiking` → press `+`
3. Click **Register** → toast confirms success
4. User appears in the grid with degree badge = 0

**Validation demo:**
- Try Age = `10` → red error "Age must be ≥ 13" (Pydantic guard)
- Try empty Name → red error "Name is required"

---

## Step 3 — Send & Accept a Friend Request (`/requests`)

1. **From:** Alice Chen → **To:** Test User → **Send Friend Request**
2. Switch inbox viewer to **Test User** → see Alice's request with #1 queue badge
3. Click **✓ Accept** → toast "Friend request accepted!"
4. Go back to `/users` → Test User now shows degree = 1

**Error demo:**
- Try sending the same request again → 409 "DUPLICATE_REQUEST" toast
- Try sending from Test User to Alice → 409 "REVERSE_REQUEST" toast (already friends)

---

## Step 4 — Interactive Force Graph (`/network`)

- The force graph loads all 30 nodes and 59 edges
- **Node size** = friend count (hub nodes are larger)
- **Node colour** = community (indigo = NYC+LA+Chicago cluster, different colour = Houston)
- Hover any node → profile tooltip (name, city, age, interests, community)
- Click a node → camera zooms to it

---

## Step 5 — BFS Path Finder (`/network`)

1. **From:** Alice Chen → **To:** Xander Scott (Chicago)
2. Click **Find Path** → path animates in purple on the graph
3. Result shows e.g. `Alice Chen → David Kim → Xander Scott` with **"2 degrees of separation"**
4. Click **▼ X total paths** → all simple DFS paths shown (backtracking algorithm)

**Disconnected demo:**
- **From:** Alice Chen → **To:** Carlos Mitchell (Houston, different component)
- Result: "Not connected" badge — BFS returns None

---

## Step 6 — Friend Recommendations (`/network`)

1. Select **Test User** in the Recommendations panel
2. See scored cards with explanations:
   - "👥 1 mutual friend" (Alice Chen)
   - "🎯 music, hiking" (shared interests)
   - "📍 Same city"
3. Scores are sorted descending (greedy ranking)

---

## Step 7 — Mutual Friends

In your browser visit:
```
http://localhost:8000/users/u01/mutual/u04
```
Response:
```json
{
  "mutual_friends": ["u02", "u10"],
  "count": 2,
  "jaccard_similarity": 0.2857
}
```

---

## Step 8 — Analytics Dashboard (`/analytics`)

- **Influencer Leaderboard table** — sorted by degree, betweenness bars
- Click chart tabs:
  - **Most Connected** — matplotlib bar chart
  - **City Distribution** — users by city
  - **Degree Distribution** — histogram
  - **Friendship Growth** — cumulative line chart (timestamped edges)
  - **Network Map** — spring-layout PNG with community colours

---

## Step 9 — API Docs

Visit **http://localhost:8000/docs**

Shows all 18 endpoints with schemas, try-it-out forms, and response models.

---

## Step 10 — Persistence Demo

1. Stop the backend (`Ctrl+C`)
2. Restart: `python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
3. Reload the dashboard → all 30 users and 59 friendships are still there
4. SQLite `save_state` / `load_state` round-trip confirmed

---

## DSA Checkpoints for Evaluator

| Algorithm | How to verify |
|---|---|
| Adjacency list O(1) | `GET /users/{id}/friends` returns instantly for any user |
| Deque FIFO queue | Send 3 requests to same user; inbox shows them in send-order |
| Set intersection (mutuals) | `GET /users/u01/mutual/u04` returns `["u02","u10"]` |
| BFS shortest path | Alice→Xander: 2 hops (provably shortest — no 1-hop path exists) |
| DFS + backtracking | Toggle "all paths" — multiple routes shown, no node repeated |
| Floyd-Warshall DP | Analytics summary: diameter=5, avg_separation≈2.478 |
| Greedy recommendations | Scores decrease monotonically down the list |
| Union-Find communities | Houston users (u12-u29) get a different colour on the force graph |
