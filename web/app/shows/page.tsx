import { redirect } from "next/navigation";

// Shows merged into the Music page (right column, All / My artists filter).
export default function ShowsPage() {
  redirect("/music");
}
