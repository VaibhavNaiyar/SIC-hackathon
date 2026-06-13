import type { User } from "@/lib/api";

const CITY_COLORS = ["bg-violet-600","bg-cyan-600","bg-emerald-600","bg-amber-600","bg-rose-600","bg-sky-600"];
function cityColor(city: string) {
  let h = 0;
  for (const c of city) h = (h * 31 + c.charCodeAt(0)) & 0xffff;
  return CITY_COLORS[h % CITY_COLORS.length];
}

interface Props {
  user: User;
  onClick?: () => void;
  selected?: boolean;
}

export default function UserCard({ user, onClick, selected }: Props) {
  return (
    <div
      onClick={onClick}
      className={`bg-surface-700 rounded-xl p-4 border transition-all cursor-pointer
        ${selected ? "border-brand-500 ring-1 ring-brand-500/40" : "border-white/5 hover:border-brand-500/40"}`}
    >
      <div className="flex items-center gap-3 mb-2">
        <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold text-white ${cityColor(user.city)}`}>
          {user.name[0].toUpperCase()}
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-white truncate">{user.name}</p>
          <p className="text-xs text-gray-400">{user.city} · age {user.age}</p>
        </div>
        <span className="text-xs bg-surface-600 text-brand-400 rounded-full px-2 py-0.5 font-medium">
          {user.degree} {user.degree === 1 ? "friend" : "friends"}
        </span>
      </div>
      {user.interests.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {user.interests.slice(0, 4).map(i => (
            <span key={i} className="text-xs bg-surface-600 text-gray-300 rounded-full px-2 py-0.5">
              {i}
            </span>
          ))}
          {user.interests.length > 4 && (
            <span className="text-xs text-gray-500">+{user.interests.length - 4}</span>
          )}
        </div>
      )}
    </div>
  );
}
