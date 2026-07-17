import Link from "next/link";
import { redirect } from "next/navigation";
import { LoginForm } from "@/components/LoginForm";
import { getSession } from "@/lib/auth";

export default async function LoginPage() {
  const user = await getSession();
  if (user) redirect("/contribute");

  return (
    <main className="page-shell max-w-lg justify-center">
      <Link
        href="/"
        className="font-brand type-brand tracking-tight"
        style={{ marginBottom: "var(--space-4)" }}
      >
        Lebne
      </Link>
      <LoginForm />
      <p className="mt-8 text-center text-sm text-[var(--muted)]">
        New here?{" "}
        <Link href="/register" className="font-semibold text-[var(--accent)]">
          Join
        </Link>
      </p>
    </main>
  );
}
