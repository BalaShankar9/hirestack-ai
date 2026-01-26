import { redirect } from "next/navigation";

export default function ExportRedirect() {
  // Deprecated route (old flow). Export now lives inside Application Workspaces.
  redirect("/dashboard");
}
