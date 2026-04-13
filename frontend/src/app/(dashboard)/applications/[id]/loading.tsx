import { Skeleton } from "@/components/ui/skeleton";

export default function WorkspaceLoading() {
  return (
    <div className="space-y-5">
      {/* Header: title + status + actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-48 rounded-xl" />
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-9 w-28 rounded-xl" />
          <Skeleton className="h-9 w-9 rounded-xl" />
        </div>
      </div>
      {/* Command summary */}
      <Skeleton className="h-28 w-full rounded-2xl" />
      {/* Tab bar */}
      <Skeleton className="h-10 w-96 rounded-xl" />
      {/* Main content area */}
      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="space-y-4">
          <Skeleton className="h-[240px] w-full rounded-2xl" />
          <Skeleton className="h-[180px] w-full rounded-2xl" />
        </div>
        <div className="space-y-3">
          <Skeleton className="h-[160px] w-full rounded-2xl" />
          <Skeleton className="h-[120px] w-full rounded-2xl" />
          <Skeleton className="h-[80px] w-full rounded-2xl" />
        </div>
      </div>
    </div>
  );
}
