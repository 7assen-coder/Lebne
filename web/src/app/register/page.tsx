import Link from "next/link";
import { redirect } from "next/navigation";
import { RegisterWizard } from "@/components/RegisterWizard";
import { getSession } from "@/lib/auth";

export default async function RegisterPage() {
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
      <RegisterWizard />
      <p className="mt-8 text-center text-sm text-[var(--muted)]">
        Have an account?{" "}
        <Link href="/login" className="font-semibold text-[var(--accent)]">
          Sign in
        </Link>
      </p>
    </main>
  );
}
