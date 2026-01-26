import { redirect } from "next/navigation";

export default function BenchmarkRedirect() {
  // Deprecated route (old flow). Use Application Workspaces instead.
  redirect("/dashboard");
}
