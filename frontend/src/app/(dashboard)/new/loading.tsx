import { Skeleton } from "@/components/ui/skeleton";

export default function NewAppLoading() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div className="flex justify-center gap-4">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="flex flex-col items-center gap-2">
            <Skeleton className="h-10 w-10 rounded-full" />
            <Skeleton className="h-3 w-16" />
          </div>
        ))}
      </div>
      <Skeleton className="h-64 rounded-2xl" />
      <div className="flex justify-between">
        <Skeleton className="h-10 w-24 rounded-xl" />
        <Skeleton className="h-10 w-24 rounded-xl" />
      </div>
    </div>
  );
}
