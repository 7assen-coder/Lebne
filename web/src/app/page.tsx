import { redirect } from "next/navigation";
import { HomeHero } from "@/components/HomeHero";
import { getSession } from "@/lib/auth";

export default async function HomePage() {
  const user = await getSession();
  if (user) redirect("/contribute");
  return <HomeHero />;
}
