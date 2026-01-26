import { redirect } from "next/navigation";

export default function UploadRedirect() {
  // Deprecated route (old flow). Keep for compatibility.
  redirect("/new?step=1");
}
