import { redirect } from "next/navigation";

export default function ConsultantRedirect() {
  // Deprecated route (old flow). Use Career Lab / Learning Plan instead.
  redirect("/career");
}
