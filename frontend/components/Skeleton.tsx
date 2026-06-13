export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div className={`animate-pulse bg-surface-600 rounded-lg ${className}`} />
  );
}

export function CardSkeleton() {
  return (
    <div className="bg-surface-700 rounded-xl p-5 border border-white/5 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-6 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}
