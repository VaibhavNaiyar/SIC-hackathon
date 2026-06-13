# Social Network Friend Graph System

An academic project implementing a full-stack social network with a hand-rolled
graph engine, classic algorithms, pandas/numpy analytics, matplotlib charts,
SQLite persistence, a FastAPI REST API, and an interactive Next.js frontend.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Next.js 14 Frontend                      │
│  Dashboard · Users · Requests · Network · Analytics         │
│  react-force-graph-2d (SSR:false) · Recharts · Tailwind CSS │
└────────────────────────┬─────────────────────────────────────┘
                         │  HTTP/JSON  (localhost:8000)
┌────────────────────────▼─────────────────────────────────────┐
│                      FastAPI Backend                         │
│  app/main.py — routes · schemas.py — Pydantic validation    │
│  errors.py — typed exception handlers                        │
├──────────┬──────────────┬──────────────┬─────────────────────┤
│  models/ │   services/  │     viz/     │      storage/       │
│  User    │ pathfinder   │  charts.py   │  store.py (SQLite)  │
│  Graph   │ recommender  │  matplotlib  │  save/load state    │
│  Requests│ analytics    │  base64 PNG  │  parameterised SQL  │
└──────────┴──────────────┴──────────────┴─────────────────────┘
                         │
              social_graph.db (SQLite)
```

### Module boundaries

| Package | Responsibility |
|---|---|
| `models/` | Domain objects: `User`, `FriendGraph` (adjacency list), `FriendRequestManager` (deque) |
| `services/` | Pure algorithms: BFS, DFS+backtracking, Union-Find, recommendations, analytics |
| `viz/` | Headless matplotlib chart generation → base64 PNG |
| `storage/` | SQLite persistence — save/load full graph state |
| `schemas.py` | Pydantic v2 request/response models — all validation lives here |
| `errors.py` | Typed exception hierarchy → HTTP status mapping |

---

## Rubric → Feature Map

| Rubric Category (marks) | Implementation |
|---|---|
| **Problem Understanding & Design (10)** | Clean module boundaries, typed errors, this README |
| **OOP Design (10)** | `User`, `FriendGraph`, `FriendRequestManager`, `RecommendationEngine`, `NetworkAnalytics`, `Store` classes with docstrings |
| **DSA Implementation (15)** | Adjacency-list graph (`dict[str,set[str]]`), `deque` request queue, set intersection for mutuals, BFS, DFS+backtracking, Union-Find |
| **Algorithms (10)** | BFS shortest path, DFS backtracking all-paths, Floyd-Warshall DP (diameter/avg separation), greedy recommendation ranking + influencer leaderboard |
| **Data Processing — pandas/numpy (10)** | `NetworkAnalytics`: DataFrames, numpy distance matrix, degree centrality, city groupby, friendship growth time-series |
| **Visualization & Dashboards (10)** | 5 matplotlib charts (backend) + react-force-graph-2d + Recharts (frontend) |
| **UI/UX (10)** | Responsive dark-theme Next.js app, toast notifications, loading skeletons, empty states, animated path highlight |
| **Input Validation & Error Handling (10)** | Pydantic v2 schemas (age ≥ 13, non-empty fields), guard chains in all service methods, typed HTTP error responses |
| **Innovation & Extra Features (10)** | Explainable recommendations, community colour-coding, animated BFS path highlight, network health panel, demo seeder, all-paths backtracking toggle |
| **Documentation & Presentation (5)** | README, docstrings on all public methods, FastAPI `/docs`, `DEMO.md` walkthrough |

---

## DSA & Algorithms Reference

| Algorithm | File | Purpose |
|---|---|---|
| Adjacency list (`dict[str,set[str]]`) | `models/graph.py` | O(1) friend lookup, add, remove |
| `collections.deque` (FIFO queue) | `models/requests.py` | Pending request ordering |
| Set intersection | `services/recommender.py` | Mutual friends in O(min\|A\|,\|B\|) |
| Jaccard similarity | `services/recommender.py` | Neighbourhood overlap score |
| BFS (shortest path) | `services/pathfinder.py` | Degrees of separation |
| DFS + backtracking | `services/pathfinder.py` | All simple paths, depth-limited |
| Greedy ranking | `services/recommender.py` | Friend recommendations by weighted score |
| Floyd-Warshall (DP) | `services/analytics.py` | All-pairs shortest paths, diameter, avg separation |
| Union-Find (path compression + union by rank) | `services/analytics.py` | Community / connected-component detection |
| Spring layout (hand-rolled force-directed) | `viz/charts.py` | Network graph PNG without networkx |

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+

### 1 — Backend

```bash
cd social-graph/backend

# Install dependencies
pip install -r requirements.txt

# (Optional) Seed a 30-user demo network
python seed.py

# Start the API server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: **http://localhost:8000/docs**

### 2 — Frontend

```bash
cd social-graph/frontend

# Install dependencies
npm install

# Development server
npm run dev
```

App: **http://localhost:3000**

### 3 — Run tests

```bash
cd social-graph/backend
python -m pytest tests/ -v
# 265 tests, all passing
```

---

## Pages

| Route | Description |
|---|---|
| `/` | Dashboard — KPI tiles, influencer bar chart, network health |
| `/users` | Register users, search/filter, profile drawer with friends list |
| `/requests` | Send friend requests, FIFO inbox with Accept/Reject |
| `/network` | Interactive force graph, BFS path finder with animated highlight, all-paths toggle, recommendations panel |
| `/analytics` | Full analytics: influencer table, Recharts charts, tabbed matplotlib PNGs |

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/users` | Register a new user |
| GET | `/users` | List users (filterable by city/interest) |
| GET | `/users/{id}` | Get user profile |
| DELETE | `/users/{id}` | Remove user |
| GET | `/users/{id}/friends` | List direct friends |
| POST | `/requests` | Send friend request |
| POST | `/requests/{id}/accept` | Accept a request |
| POST | `/requests/{id}/reject` | Reject a request |
| GET | `/users/{id}/requests` | Pending inbox (FIFO) |
| GET | `/users/{a}/mutual/{b}` | Mutual friends + Jaccard |
| GET | `/users/{id}/recommendations` | Explainable friend recommendations |
| GET | `/path?from=&to=` | BFS shortest path |
| GET | `/paths?from=&to=` | All simple paths (backtracking) |
| GET | `/analytics/summary` | Network health metrics |
| GET | `/analytics/influencers` | Top influencers leaderboard |
| GET | `/analytics/charts/{kind}` | Matplotlib chart as base64 PNG |
| GET | `/graph` | Full graph for force-graph rendering |
| GET | `/health` | Liveness check |

---

## Project Structure

```
social-graph/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI routes
│   │   ├── schemas.py       # Pydantic models
│   │   ├── errors.py        # Typed exceptions
│   │   ├── models/
│   │   │   ├── user.py      # User dataclass
│   │   │   ├── graph.py     # FriendGraph (adjacency list)
│   │   │   └── requests.py  # FriendRequestManager (deque)
│   │   ├── services/
│   │   │   ├── pathfinder.py   # BFS + DFS backtracking
│   │   │   ├── recommender.py  # Greedy recommendations
│   │   │   └── analytics.py    # pandas/numpy + Union-Find
│   │   ├── viz/
│   │   │   └── charts.py    # Matplotlib charts → base64
│   │   └── storage/
│   │       └── store.py     # SQLite persistence
│   ├── tests/               # 265 pytest tests
│   ├── seed.py              # 30-user demo seeder
│   └── requirements.txt
├── frontend/
│   ├── app/                 # Next.js App Router pages
│   ├── components/          # Navbar, Toast, UserCard, etc.
│   └── lib/api.ts           # Typed API client
└── README.md
```
