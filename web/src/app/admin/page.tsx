import { redirect } from "next/navigation";
import { AdminClient } from "@/components/AdminClient";
import { getSession } from "@/lib/auth";

export default async function AdminPage() {
  const user = await getSession();
  if (!user) redirect("/login");
  if (!user.isReviewer) redirect("/contribute");
  return (
    <AdminClient
      role={user.role}
      isOwner={user.isAdmin}
      userName={user.name}
    />
  );
}
