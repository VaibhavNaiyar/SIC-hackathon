"use client";
import { useEffect, useRef, useState } from "react";
import { api, type User } from "@/lib/api";
import UserCard from "@/components/UserCard";
import { CardSkeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";

export default function UsersPage() {
  const toast = useToast();
  const [users, setUsers]       = useState<User[]>([]);
  const [loading, setLoading]   = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [search, setSearch]     = useState("");
  const [selected, setSelected] = useState<User | null>(null);
  const [friends, setFriends]   = useState<User[]>([]);

  // Form state
  const [name, setName]         = useState("");
  const [age, setAge]           = useState("");
  const [city, setCity]         = useState("");
  const [interestInput, setInterestInput] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [errors, setErrors]     = useState<Record<string, string>>({});

  const load = () => {
    setLoading(true);
    api.listUsers().then(setUsers).catch(() => toast("Failed to load users", "error"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const validate = () => {
    const e: Record<string, string> = {};
    if (!name.trim()) e.name = "Name is required";
    const a = parseInt(age);
    if (!age || isNaN(a) || a < 13) e.age = "Age must be ≥ 13";
    if (a > 120) e.age = "Age must be ≤ 120";
    if (!city.trim()) e.city = "City is required";
    return e;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    setErrors({});
    setSubmitting(true);
    try {
      await api.createUser({ name: name.trim(), age: parseInt(age), city: city.trim(), interests });
      toast(`${name} registered successfully!`, "success");
      setName(""); setAge(""); setCity(""); setInterests([]);
      load();
    } catch (err: any) {
      toast(err?.detail ?? "Registration failed", "error");
    } finally {
      setSubmitting(false);
    }
  };

  const addInterest = () => {
    const tag = interestInput.trim().toLowerCase();
    if (tag && !interests.includes(tag)) setInterests(i => [...i, tag]);
    setInterestInput("");
  };

  const handleCardClick = async (user: User) => {
    setSelected(user);
    try {
      const f = await api.getFriends(user.user_id);
      setFriends(f);
    } catch { setFriends([]); }
  };

  const handleDelete = async (u: User) => {
    if (!confirm(`Delete ${u.name}? This removes all their friendships.`)) return;
    try {
      await api.deleteUser(u.user_id);
      toast(`${u.name} removed`, "info");
      setSelected(null);
      load();
    } catch (err: any) {
      toast(err?.detail ?? "Delete failed", "error");
    }
  };

  const filtered = users.filter(u =>
    u.name.toLowerCase().includes(search.toLowerCase()) ||
    u.city.toLowerCase().includes(search.toLowerCase()) ||
    u.interests.some(i => i.includes(search.toLowerCase()))
  );

  return (
    <div className="max-w-7xl mx-auto px-4 py-8 animate-fade-in">
      <h1 className="text-3xl font-bold text-white mb-1">Users</h1>
      <p className="text-gray-400 text-sm mb-8">Register new members and explore the network</p>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Registration form */}
        <div className="lg:col-span-1">
          <div className="bg-surface-700 rounded-xl p-6 border border-white/5 sticky top-20">
            <h2 className="font-semibold text-white mb-4">Register User</h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Full Name</label>
                <input className="input" placeholder="Alice Johnson" value={name} onChange={e => setName(e.target.value)} />
                {errors.name && <p className="text-red-400 text-xs mt-1">{errors.name}</p>}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">Age</label>
                  <input className="input" type="number" min={13} max={120} placeholder="25" value={age} onChange={e => setAge(e.target.value)} />
                  {errors.age && <p className="text-red-400 text-xs mt-1">{errors.age}</p>}
                </div>
                <div>
                  <label className="text-xs text-gray-400 mb-1 block">City</label>
                  <input className="input" placeholder="New York" value={city} onChange={e => setCity(e.target.value)} />
                  {errors.city && <p className="text-red-400 text-xs mt-1">{errors.city}</p>}
                </div>
              </div>
              <div>
                <label className="text-xs text-gray-400 mb-1 block">Interests</label>
                <div className="flex gap-2">
                  <input
                    className="input flex-1"
                    placeholder="e.g. music"
                    value={interestInput}
                    onChange={e => setInterestInput(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addInterest(); } }}
                  />
                  <button type="button" onClick={addInterest} className="btn-secondary px-3">+</button>
                </div>
                {interests.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {interests.map(i => (
                      <span key={i} className="flex items-center gap-1 text-xs bg-brand-600/30 text-brand-300 rounded-full px-2.5 py-1">
                        {i}
                        <button type="button" onClick={() => setInterests(t => t.filter(x => x !== i))} className="hover:text-red-400">×</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <button type="submit" disabled={submitting} className="btn-primary w-full">
                {submitting ? "Registering…" : "Register"}
              </button>
            </form>
          </div>
        </div>

        {/* User list */}
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center gap-3">
            <input className="input flex-1" placeholder="Search by name, city or interest…" value={search} onChange={e => setSearch(e.target.value)} />
            <span className="text-xs text-gray-500 whitespace-nowrap">{filtered.length} user{filtered.length !== 1 ? "s" : ""}</span>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[...Array(6)].map((_, i) => <CardSkeleton key={i} />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-16 text-gray-500">
              <p className="text-4xl mb-3">👤</p>
              <p>{search ? "No users match your search" : "No users yet — register one!"}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {filtered.map(u => (
                <UserCard key={u.user_id} user={u} onClick={() => handleCardClick(u)} selected={selected?.user_id === u.user_id} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* User detail drawer */}
      {selected && (
        <div className="fixed inset-0 z-50 flex justify-end" onClick={() => setSelected(null)}>
          <div className="w-full max-w-sm bg-surface-800 border-l border-white/10 p-6 overflow-y-auto animate-slide-up" onClick={e => e.stopPropagation()}>
            <button onClick={() => setSelected(null)} className="text-gray-400 hover:text-white mb-4 text-sm">← Close</button>
            <div className="flex items-center gap-3 mb-4">
              <div className="w-14 h-14 bg-brand-700 rounded-full flex items-center justify-center text-2xl font-bold text-white">
                {selected.name[0]}
              </div>
              <div>
                <h3 className="text-xl font-bold text-white">{selected.name}</h3>
                <p className="text-gray-400 text-sm">{selected.city} · age {selected.age}</p>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Interests</p>
                <div className="flex flex-wrap gap-1.5">
                  {selected.interests.length ? selected.interests.map(i => (
                    <span key={i} className="text-xs bg-brand-600/30 text-brand-300 rounded-full px-2.5 py-1">{i}</span>
                  )) : <span className="text-xs text-gray-500">None listed</span>}
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-widest mb-2">Friends ({friends.length})</p>
                {friends.length === 0 ? (
                  <p className="text-xs text-gray-500">No friends yet</p>
                ) : (
                  <ul className="space-y-2">
                    {friends.map(f => (
                      <li key={f.user_id} className="flex items-center gap-2 text-sm text-gray-300">
                        <div className="w-6 h-6 bg-surface-600 rounded-full flex items-center justify-center text-xs">{f.name[0]}</div>
                        {f.name} <span className="text-gray-500">· {f.city}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <button onClick={() => handleDelete(selected)} className="btn-danger w-full mt-4">
                Delete User
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
