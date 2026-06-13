"""FastAPI application — routes, startup/shutdown, global state.

All business logic is delegated to the service layer.
Route handlers are intentionally thin: validate input (Pydantic),
call a service, return a response schema.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.errors import (
    AlreadyFriendsError,
    DuplicateRequestError,
    DuplicateUserError,
    InvalidUserDataError,
    NotFriendsError,
    NoPathError,
    RequestNotFoundError,
    ReverseRequestError,
    SelfFriendshipError,
    SocialGraphError,
    StorageError,
    UserNotFoundError,
)
from app.models.graph import FriendGraph
from app.models.requests import FriendRequestManager
from app.models.user import User
from app.schemas import (
    AllPathsResponse,
    AnalyticsSummaryResponse,
    ErrorResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    InfluencerResponse,
    MutualFriendsResponse,
    PathResponse,
    RecommendationResponse,
    RecommendationWhyResponse,
    RequestResponse,
    SendRequestBody,
    UserCreate,
    UserResponse,
)
from app.services.analytics import NetworkAnalytics, detect_communities
from app.services.pathfinder import all_simple_paths, shortest_path
from app.services.recommender import RecommendationEngine, jaccard_similarity, mutual_friends
from app.storage.store import Store
from app.viz.charts import (
    CHART_KINDS,
    chart_city_distribution,
    chart_degree_distribution,
    chart_friendship_growth,
    chart_network_graph,
    chart_top_connected,
)

# ── Global singletons ──────────────────────────────────────────────────────────

_store = Store("social_graph.db")
_graph = FriendGraph()
_requests = FriendRequestManager(_graph)
_timestamps: dict = {}


def _analytics() -> NetworkAnalytics:
    """Return a fresh NetworkAnalytics view of the current graph."""
    return NetworkAnalytics(_graph, _timestamps)


def _persist() -> None:
    """Save current state to SQLite after every mutation."""
    _store.save_state(_graph, _requests, _timestamps)


# ── App factory ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load state from SQLite on startup."""
    global _graph, _requests, _timestamps
    try:
        _graph, _requests, _timestamps = _store.load_state()
    except StorageError:
        # First run — start with empty state
        pass
    # Re-point the manager at the loaded graph
    yield


app = FastAPI(
    title="Social Network Friend Graph API",
    description=(
        "Friend graph system: users, friendships, BFS paths, "
        "recommendations, analytics, and interactive graph export."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow the Next.js dev server and any local origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ─────────────────────────────────────────────────────────

def _err(code: str, detail: str, status: int) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": code, "detail": detail},
    )


@app.exception_handler(UserNotFoundError)
async def handle_user_not_found(_, exc: UserNotFoundError):
    return _err(exc.code, exc.message, 404)


@app.exception_handler(DuplicateUserError)
async def handle_duplicate_user(_, exc: DuplicateUserError):
    return _err(exc.code, exc.message, 409)


@app.exception_handler(InvalidUserDataError)
async def handle_invalid_user(_, exc: InvalidUserDataError):
    return _err(exc.code, exc.message, 422)


@app.exception_handler(SelfFriendshipError)
async def handle_self_friendship(_, exc: SelfFriendshipError):
    return _err(exc.code, exc.message, 400)


@app.exception_handler(AlreadyFriendsError)
async def handle_already_friends(_, exc: AlreadyFriendsError):
    return _err(exc.code, exc.message, 409)


@app.exception_handler(NotFriendsError)
async def handle_not_friends(_, exc: NotFriendsError):
    return _err(exc.code, exc.message, 404)


@app.exception_handler(DuplicateRequestError)
async def handle_duplicate_request(_, exc: DuplicateRequestError):
    return _err(exc.code, exc.message, 409)


@app.exception_handler(ReverseRequestError)
async def handle_reverse_request(_, exc: ReverseRequestError):
    return _err(exc.code, exc.message, 409)


@app.exception_handler(RequestNotFoundError)
async def handle_request_not_found(_, exc: RequestNotFoundError):
    return _err(exc.code, exc.message, 404)


@app.exception_handler(StorageError)
async def handle_storage_error(_, exc: StorageError):
    return _err(exc.code, exc.message, 503)


@app.exception_handler(SocialGraphError)
async def handle_generic_social_error(_, exc: SocialGraphError):
    return _err(exc.code, exc.message, 400)


# ── Helper ─────────────────────────────────────────────────────────────────────

def _user_response(user_id: str) -> UserResponse:
    user = _graph.get_user(user_id)
    return UserResponse(
        user_id=user.user_id,
        name=user.name,
        age=user.age,
        city=user.city,
        interests=sorted(user.interests),
        degree=_graph.degree(user_id),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Users
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/users", response_model=UserResponse, status_code=201, tags=["Users"])
def create_user(body: UserCreate):
    """Register a new user in the social network."""
    user = User(
        name=body.name,
        age=body.age,
        city=body.city,
        interests=set(body.interests),
    )
    _graph.add_user(user)
    _persist()
    return _user_response(user.user_id)


@app.get("/users", response_model=list[UserResponse], tags=["Users"])
def list_users(
    city: str | None = Query(None, description="Filter by city"),
    interest: str | None = Query(None, description="Filter by interest tag"),
):
    """List all registered users, with optional city/interest filters."""
    users = list(_graph.users())
    if city:
        users = [u for u in users if u.city.lower() == city.lower()]
    if interest:
        users = [u for u in users if interest.lower() in u.interests]
    return [_user_response(u.user_id) for u in users]


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(user_id: str):
    """Get a single user's profile."""
    return _user_response(user_id)


@app.delete("/users/{user_id}", status_code=204, tags=["Users"])
def delete_user(user_id: str):
    """Remove a user and all their friendship edges from the network."""
    _graph.remove_user(user_id)
    _persist()


@app.get("/users/{user_id}/friends", response_model=list[UserResponse], tags=["Users"])
def get_friends(user_id: str):
    """Return all direct friends of a user."""
    friend_ids = _graph.get_friends(user_id)
    return [_user_response(fid) for fid in sorted(friend_ids)]


@app.delete("/users/{user_a}/friends/{user_b}", status_code=204, tags=["Users"])
def remove_friendship(user_a: str, user_b: str):
    """Remove a friendship edge between two users."""
    _graph.remove_friend(user_a, user_b)
    _persist()


# ═══════════════════════════════════════════════════════════════════════════════
# Friend Requests
# ═══════════════════════════════════════════════════════════════════════════════

@app.post("/requests", response_model=RequestResponse, status_code=201, tags=["Requests"])
def send_request(body: SendRequestBody):
    """Send a friend request from one user to another."""
    req = _requests.send_request(body.from_id, body.to_id)
    _persist()
    return RequestResponse(from_id=req.from_id, to_id=req.to_id, status=req.status.value)


@app.post(
    "/requests/{from_id}/accept",
    response_model=RequestResponse,
    tags=["Requests"],
)
def accept_request(from_id: str, to_id: Annotated[str, Query(...)]):
    """Accept a pending friend request.

    - **from_id**: the user who sent the request
    - **to_id**: the user who is accepting it (query param)
    """
    req = _requests.accept_request(to_id=to_id, from_id=from_id)
    _persist()
    return RequestResponse(from_id=req.from_id, to_id=req.to_id, status=req.status.value)


@app.post(
    "/requests/{from_id}/reject",
    response_model=RequestResponse,
    tags=["Requests"],
)
def reject_request(from_id: str, to_id: Annotated[str, Query(...)]):
    """Reject a pending friend request.

    - **from_id**: the user who sent the request
    - **to_id**: the user who is rejecting it (query param)
    """
    req = _requests.reject_request(to_id=to_id, from_id=from_id)
    _persist()
    return RequestResponse(from_id=req.from_id, to_id=req.to_id, status=req.status.value)


@app.get(
    "/users/{user_id}/requests",
    response_model=list[RequestResponse],
    tags=["Requests"],
)
def get_pending_requests(user_id: str):
    """Return all incoming pending requests for a user, in FIFO order."""
    pending = _requests.pending_for(user_id)
    return [
        RequestResponse(from_id=r.from_id, to_id=r.to_id, status=r.status.value)
        for r in pending
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# Mutual friends & Recommendations
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/users/{user_a}/mutual/{user_b}",
    response_model=MutualFriendsResponse,
    tags=["Social"],
)
def get_mutual_friends(user_a: str, user_b: str):
    """Return the mutual friends and Jaccard similarity between two users."""
    mutuals = sorted(mutual_friends(_graph, user_a, user_b))
    j = jaccard_similarity(_graph, user_a, user_b)
    return MutualFriendsResponse(
        user_a=user_a,
        user_b=user_b,
        mutual_friends=mutuals,
        count=len(mutuals),
        jaccard_similarity=round(j, 4),
    )


@app.get(
    "/users/{user_id}/recommendations",
    response_model=list[RecommendationResponse],
    tags=["Social"],
)
def get_recommendations(
    user_id: str,
    top_k: int = Query(5, ge=1, le=20),
):
    """Return top-K friend recommendations with explainability."""
    engine = RecommendationEngine(_graph)
    recs = engine.recommend(user_id, top_k=top_k)
    result = []
    for r in recs:
        candidate = _graph.get_user(r.candidate_id)
        result.append(
            RecommendationResponse(
                candidate_id=r.candidate_id,
                candidate_name=candidate.name,
                why=RecommendationWhyResponse(
                    mutuals=r.why.mutuals,
                    shared_interests=r.why.shared_interests,
                    same_city=r.why.same_city,
                    score=r.why.score,
                ),
            )
        )
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/path", response_model=PathResponse, tags=["Paths"])
def get_shortest_path(
    source: str = Query(..., alias="from"),
    target: str = Query(..., alias="to"),
):
    """Find the shortest connection path (BFS) between two users."""
    result = shortest_path(_graph, source, target)
    return PathResponse(
        path=result.path,
        hops=result.hops,
        degrees=result.degrees,
        connected=result.connected,
    )


@app.get("/paths", response_model=AllPathsResponse, tags=["Paths"])
def get_all_paths(
    source: str = Query(..., alias="from"),
    target: str = Query(..., alias="to"),
    max_depth: int = Query(4, ge=1, le=6),
):
    """Enumerate all simple paths (DFS + backtracking) up to max_depth hops."""
    paths = all_simple_paths(_graph, source, target, max_depth=max_depth)
    return AllPathsResponse(paths=paths, count=len(paths))


# ═══════════════════════════════════════════════════════════════════════════════
# Analytics
# ═══════════════════════════════════════════════════════════════════════════════

@app.get(
    "/analytics/summary",
    response_model=AnalyticsSummaryResponse,
    tags=["Analytics"],
)
def get_analytics_summary():
    """Return network health metrics: density, diameter, avg separation, etc."""
    s = _analytics().summary()
    return AnalyticsSummaryResponse(**s)


@app.get("/analytics/influencers", response_model=list[InfluencerResponse], tags=["Analytics"])
def get_influencers(top_n: int = Query(5, ge=1, le=20)):
    """Return top-N influencers ranked by degree + betweenness approximation."""
    inf_list = _analytics().top_influencers(top_n=top_n)
    return [InfluencerResponse(**item) for item in inf_list]


@app.get("/analytics/charts/{kind}", tags=["Analytics"])
def get_chart(kind: str):
    """Return a base64-encoded PNG chart.

    **kind** must be one of:
    `top_connected` | `city_distribution` | `friendship_growth` |
    `network_graph` | `degree_distribution`
    """
    if kind not in CHART_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown chart kind '{kind}'. "
                   f"Choose from: {sorted(CHART_KINDS)}",
        )

    an = _analytics()

    if kind == "top_connected":
        b64 = chart_top_connected(an.most_connected(top_n=10))
    elif kind == "city_distribution":
        b64 = chart_city_distribution(an.city_distribution())
    elif kind == "friendship_growth":
        b64 = chart_friendship_growth(an.friendship_growth())
    elif kind == "degree_distribution":
        b64 = chart_degree_distribution(an.users_dataframe())
    elif kind == "network_graph":
        communities = detect_communities(_graph)
        nodes = [{"id": u.user_id, "name": u.name} for u in _graph.users()]
        seen: set = set()
        edges = []
        for uid in _graph.user_ids():
            for nid in _graph.neighbors(uid):
                key = (min(uid, nid), max(uid, nid))
                if key not in seen:
                    seen.add(key)
                    edges.append(key)
        b64 = chart_network_graph(nodes, edges, community_labels=communities)
    else:
        b64 = ""

    return {"kind": kind, "image": b64, "format": "png", "encoding": "base64"}


# ═══════════════════════════════════════════════════════════════════════════════
# Graph export (force-graph payload)
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/graph", response_model=GraphResponse, tags=["Graph"])
def get_graph():
    """Return the full graph as nodes + edges for the frontend force graph."""
    communities = detect_communities(_graph)

    nodes = []
    for user in _graph.users():
        nodes.append(
            GraphNode(
                id=user.user_id,
                name=user.name,
                age=user.age,
                city=user.city,
                interests=sorted(user.interests),
                degree=_graph.degree(user.user_id),
                community=communities.get(user.user_id, 0),
            )
        )

    edges = []
    seen: set = set()
    for uid in _graph.user_ids():
        for nid in _graph.neighbors(uid):
            key = (min(uid, nid), max(uid, nid))
            if key not in seen:
                seen.add(key)
                edges.append(GraphEdge(source=key[0], target=key[1]))

    return GraphResponse(nodes=nodes, edges=edges)


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    """Quick liveness check."""
    return {
        "status": "ok",
        "users": len(_graph),
        "edges": _graph.edge_count(),
    }
