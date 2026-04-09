import { redirect } from "next/navigation";

export default function ConsultantRedirect() {
  // Deprecated route (old flow). Use Improvement / Learning Plan instead.
  redirect("/career");
}
