"use client";

import { AlertCircle, ArrowLeft, Check, Circle, Link2Off, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { PasswordInput } from "@/components/auth/auth-inputs";
import { AuthLayout } from "@/components/layout/auth-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { passwordProblems } from "@/lib/password";
import { cn } from "@/lib/utils";

function Requirement({ met, children }: { met: boolean; children: React.ReactNode }) {
  return (
    <li className={cn("flex items-center gap-1.5", met ? "text-status-good-text" : "text-muted-foreground")}>
      {met ? <Check className="size-3.5" aria-hidden /> : <Circle className="size-3" aria-hidden />}
      {children}
      <span className="sr-only">{met ? " (met)" : " (not met yet)"}</span>
    </li>
  );
}

function ResetForm() {
  const { t } = useI18n();
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<{ text: string; badLink: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const back = (
    <Link href="/login" className="inline-flex items-center gap-1.5 font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" aria-hidden /> {t("Back to sign in")}
    </Link>
  );

  if (!token || error?.badLink) {
    return (
      <AuthLayout title="This link can't be used" aside={back}>
        <div className="grid gap-5 text-sm">
          <span className="flex size-12 items-center justify-center rounded-full bg-status-critical/10 text-status-critical">
            <Link2Off className="size-6" aria-hidden />
          </span>
          <p className="text-muted-foreground">
            {token
              ? "This password reset link has expired or was already used. Links work once, for 30 minutes."
              : "This password reset link is incomplete. Open the full link from the email, or request a new one."}
          </p>
          <Button asChild className="h-11">
            <Link href="/forgot-password">Request a new link</Link>
          </Button>
        </div>
      </AuthLayout>
    );
  }

  const problems = passwordProblems(password);
  const longEnough = password.length >= 8;
  const mixed = password.length > 0 && !problems.includes("Mix letters with numbers or symbols.");
  const mismatch = confirm.length > 0 && confirm !== password;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    if (problems.length) {
      setError({ text: problems.join(" "), badLink: false });
      return;
    }
    if (password !== confirm) {
      setError({ text: t("The passwords do not match."), badLink: false });
      return;
    }
    setBusy(true);
    try {
      await api("/auth/password-reset/confirm", { method: "POST", body: { token, new_password: password }, noRestaurant: true });
      router.replace("/login?reason=reset");
    } catch (e) {
      setError({ text: errorMessage(e), badLink: e instanceof ApiError && e.code === "invalid_token" });
      setBusy(false);
    }
  }

  return (
    <AuthLayout title="Choose a new password" subtitle="You'll use it to sign in on every device." aside={back}>
      <form onSubmit={submit} noValidate>
        <fieldset disabled={busy} className="grid gap-5">
          <div className="grid gap-1.5">
            <Label htmlFor="password">{t("New password")}</Label>
            <PasswordInput
              id="password"
              autoComplete="new-password"
              autoFocus
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(null);
              }}
            />
            <ul className="mt-1 grid gap-1 text-xs" aria-label="Password requirements">
              <Requirement met={longEnough}>At least 8 characters</Requirement>
              <Requirement met={mixed}>Letters mixed with numbers or symbols</Requirement>
            </ul>
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="confirm">{t("Confirm password")}</Label>
            <PasswordInput
              id="confirm"
              autoComplete="new-password"
              value={confirm}
              aria-invalid={mismatch}
              onChange={(e) => {
                setConfirm(e.target.value);
                setError(null);
              }}
            />
            {mismatch ? <p className="text-xs font-medium text-status-critical">{t("The passwords do not match.")}</p> : null}
          </div>
          {error ? (
            <div role="alert" className="flex animate-pop gap-3 rounded-lg border border-status-critical/30 bg-status-critical/8 px-3.5 py-3 text-sm">
              <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" aria-hidden />
              <p>{error.text}</p>
            </div>
          ) : null}
          <Button type="submit" size="lg" className="h-11 w-full text-[15px]" disabled={!password || !confirm}>
            {busy ? <Loader2 className="animate-spin" aria-hidden /> : null} {t("Update password")}
          </Button>
        </fieldset>
      </form>
    </AuthLayout>
  );
}

export default function ResetPasswordPage() {
  // The token comes from the URL, which is only known in the browser.
  return (
    <Suspense fallback={null}>
      <ResetForm />
    </Suspense>
  );
}
