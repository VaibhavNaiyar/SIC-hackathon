"use client";
import { useEffect, useState } from "react";
import { api, type User, type FriendRequest } from "@/lib/api";
import { useToast } from "@/components/Toast";

export default function RequestsPage() {
  const toast = useToast();
  const [users, setUsers]     = useState<User[]>([]);
  const [fromId, setFromId]   = useState("");
  const [toId, setToId]       = useState("");
  const [viewerId, setViewerId] = useState("");
  const [inbox, setInbox]     = useState<FriendRequest[]>([]);
  const [sending, setSending] = useState(false);
  const [acting, setActing]   = useState<string>("");

  useEffect(() => {
    api.listUsers().then(u => { setUsers(u); if (u.length) setViewerId(u[0].user_id); }).catch(() => {});
  }, []);

  useEffect(() => {
    if (viewerId) loadInbox(viewerId);
  }, [viewerId]);

  const loadInbox = (uid: string) => {
    api.getPendingRequests(uid).then(setInbox).catch(() => setInbox([]));
  };

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fromId || !toId) { toast("Select both users", "error"); return; }
    if (fromId === toId)  { toast("Cannot request yourself", "error"); return; }
    setSending(true);
    try {
      await api.sendRequest(fromId, toId);
      const toName = users.find(u => u.user_id === toId)?.name;
      toast(`Request sent to ${toName}!`, "success");
      if (viewerId === toId) loadInbox(toId);
    } catch (err: any) {
      toast(err?.detail ?? "Failed to send request", "error");
    } finally { setSending(false); }
  };

  const handleAccept = async (req: FriendRequest) => {
    setActing(req.from_id);
    try {
      await api.acceptRequest(req.from_id, req.to_id);
      toast("Friend request accepted!", "success");
      loadInbox(viewerId);
    } catch (err: any) {
      toast(err?.detail ?? "Accept failed", "error");
    } finally { setActing(""); }
  };

  const handleReject = async (req: FriendRequest) => {
    setActing(req.from_id);
    try {
      await api.rejectRequest(req.from_id, req.to_id);
      toast("Request rejected", "info");
      loadInbox(viewerId);
    } catch (err: any) {
      toast(err?.detail ?? "Reject failed", "error");
    } finally { setActing(""); }
  };

  const userName = (id: string) => users.find(u => u.user_id === id)?.name ?? id;

  return (
    <div className="max-w-5xl mx-auto px-4 py-8 animate-fade-in">
      <h1 className="text-3xl font-bold text-white mb-1">Friend Requests</h1>
      <p className="text-gray-400 text-sm mb-8">Send requests and manage your inbox</p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Send request */}
        <div className="bg-surface-700 rounded-xl p-6 border border-white/5">
          <h2 className="font-semibold text-white mb-4">Send a Request</h2>
          <form onSubmit={handleSend} className="space-y-4">
            <div>
              <label className="text-xs text-gray-400 mb-1 block">From</label>
              <select className="input" value={fromId} onChange={e => setFromId(e.target.value)}>
                <option value="">— select user —</option>
                {users.map(u => <option key={u.user_id} value={u.user_id}>{u.name} ({u.city})</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-400 mb-1 block">To</label>
              <select className="input" value={toId} onChange={e => setToId(e.target.value)}>
                <option value="">— select user —</option>
                {users.filter(u => u.user_id !== fromId).map(u =>
                  <option key={u.user_id} value={u.user_id}>{u.name} ({u.city})</option>
                )}
              </select>
            </div>
            <button type="submit" disabled={sending || !fromId || !toId} className="btn-primary w-full">
              {sending ? "Sending…" : "Send Friend Request"}
            </button>
          </form>

          {/* Connection preview */}
          {fromId && toId && fromId !== toId && (
            <div className="mt-4 p-3 bg-surface-600 rounded-lg text-sm">
              <span className="text-brand-400 font-medium">{userName(fromId)}</span>
              <span className="text-gray-500 mx-2">→</span>
              <span className="text-brand-400 font-medium">{userName(toId)}</span>
            </div>
          )}
        </div>

        {/* Inbox */}
        <div className="bg-surface-700 rounded-xl p-6 border border-white/5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">Inbox</h2>
            <select className="input w-auto text-xs py-1" value={viewerId} onChange={e => setViewerId(e.target.value)}>
              {users.map(u => <option key={u.user_id} value={u.user_id}>{u.name}</option>)}
            </select>
          </div>

          {inbox.length === 0 ? (
            <div className="text-center py-10 text-gray-500">
              <p className="text-3xl mb-2">📭</p>
              <p className="text-sm">No pending requests</p>
            </div>
          ) : (
            <ul className="space-y-3">
              {inbox.map((req, i) => (
                <li key={req.from_id} className="bg-surface-600 rounded-xl p-4 border border-white/5 animate-slide-up"
                    style={{ animationDelay: `${i * 40}ms` }}>
                  <div className="flex items-center gap-3 mb-3">
                    <div className="w-9 h-9 bg-brand-700 rounded-full flex items-center justify-center text-sm font-bold text-white">
                      {userName(req.from_id)[0]}
                    </div>
                    <div className="flex-1">
                      <p className="text-sm font-semibold text-white">{userName(req.from_id)}</p>
                      <p className="text-xs text-gray-400">wants to connect with {userName(req.to_id)}</p>
                    </div>
                    <span className="text-xs bg-amber-600/20 text-amber-400 rounded-full px-2 py-0.5">#{i + 1} in queue</span>
                  </div>
                  <div className="flex gap-2">
                    <button
                      disabled={acting === req.from_id}
                      onClick={() => handleAccept(req)}
                      className="btn-success flex-1 text-center"
                    >
                      {acting === req.from_id ? "…" : "✓ Accept"}
                    </button>
                    <button
                      disabled={acting === req.from_id}
                      onClick={() => handleReject(req)}
                      className="btn-danger flex-1 text-center"
                    >
                      {acting === req.from_id ? "…" : "✕ Reject"}
                    </button>
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
