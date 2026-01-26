import { redirect } from "next/navigation";

export default function GapsRedirect() {
  // Deprecated route (old flow). Use Application Workspaces instead.
  redirect("/dashboard");
}
