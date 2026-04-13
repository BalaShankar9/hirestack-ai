import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLoading() {
  return (
    <div className="space-y-6">
      {/* Hero command center */}
      <Skeleton className="h-[200px] rounded-3xl" />
      {/* Quick actions */}
      <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[72px] rounded-xl" />
        ))}
      </div>
      {/* Main grid */}
      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <div className="grid gap-3 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[160px] rounded-2xl" />
          ))}
        </div>
        <div className="space-y-3">
          <Skeleton className="h-[200px] rounded-2xl" />
          <Skeleton className="h-[64px] rounded-2xl" />
          <Skeleton className="h-[64px] rounded-2xl" />
          <Skeleton className="h-[64px] rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
