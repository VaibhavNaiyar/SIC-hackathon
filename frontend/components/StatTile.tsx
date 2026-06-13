interface StatTileProps {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}

export default function StatTile({ label, value, sub, accent = "brand" }: StatTileProps) {
  return (
    <div className="bg-surface-700 rounded-xl p-5 border border-white/5 flex flex-col gap-1 hover:border-brand-500/40 transition-all">
      <p className="text-xs text-gray-500 uppercase tracking-widest font-semibold">{label}</p>
      <p className={`text-3xl font-bold text-${accent}-400`}>{value}</p>
      {sub && <p className="text-xs text-gray-500">{sub}</p>}
    </div>
  );
}
