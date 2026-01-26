import { redirect } from "next/navigation";

export default function BuilderRedirect() {
  // Deprecated route (old flow). Editing now lives inside Application Workspaces.
  redirect("/dashboard");
}
