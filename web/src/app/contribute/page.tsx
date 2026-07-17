import { redirect } from "next/navigation";
import { ContributeClient } from "@/components/ContributeClient";
import { getSession } from "@/lib/auth";

export default async function ContributePage() {
  const user = await getSession();
  if (!user) redirect("/login");
  return <ContributeClient userName={user.name} isReviewer={user.isReviewer} />;
}
