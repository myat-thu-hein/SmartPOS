"use client";

import { AlertCircle, ArrowLeft, Clock, Loader2, Mail, MailCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { IconInput } from "@/components/auth/auth-inputs";
import { AuthLayout } from "@/components/layout/auth-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const IS_DEV = process.env.NODE_ENV !== "production";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<{ text: string; rate: boolean } | null>(null);
  const [touched, setTouched] = useState(false);
  const trimmed = email.trim();
  const invalid = touched && !EMAIL.test(trimmed);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setTouched(true);
    if (!EMAIL.test(trimmed)) return;
    setError(null);
    setState("sending");
    try {
      await api("/auth/password-reset/request", { method: "POST", body: { email: trimmed }, noRestaurant: true });
      setState("sent");
    } catch (e) {
      const rate = e instanceof ApiError && e.status === 429;
      setError({
        rate,
        text: rate ? "Too many requests for this email. Wait a few minutes, then try again." : errorMessage(e),
      });
      setState("idle");
    }
  }

  const back = (
    <Link href="/login" className="inline-flex items-center gap-1.5 font-medium text-muted-foreground hover:text-foreground">
      <ArrowLeft className="size-4" aria-hidden /> {t("Back to sign in")}
    </Link>
  );

  if (state === "sent") {
    return (
      <AuthLayout title="Check your inbox" aside={back}>
        <div className="grid gap-5 text-sm">
          <span className="flex size-12 items-center justify-center rounded-full bg-status-good/12 text-status-good-text">
            <MailCheck className="size-6" aria-hidden />
          </span>
          <p className="text-muted-foreground">
            If an account exists for <span className="font-medium text-foreground">{trimmed}</span>, we&apos;ve sent a
            link to choose a new password. It works once and expires in 30 minutes.
          </p>
          {IS_DEV ? (
            <p className="rounded-lg border border-dashed bg-muted/40 p-3 text-xs text-muted-foreground">
              Local development: without SMTP settings the link is printed in the backend log.
            </p>
          ) : null}
          <Button variant="outline" className="h-11" onClick={() => setState("idle")}>
            Use a different email
          </Button>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="Reset your password"
      subtitle="Enter your account email and we'll send you a link to choose a new password."
      aside={back}
    >
      <form onSubmit={submit} noValidate>
        <fieldset disabled={state === "sending"} className="grid gap-5">
          <div className="grid gap-1.5">
            <Label htmlFor="email">{t("Email")}</Label>
            <IconInput
              icon={Mail}
              id="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              autoFocus
              placeholder="name@restaurant.com"
              value={email}
              aria-invalid={invalid}
              onChange={(e) => {
                setEmail(e.target.value);
                setError(null);
              }}
              onBlur={() => setTouched(true)}
            />
            {invalid ? (
              <p role="alert" className="text-xs font-medium text-status-critical">
                {t(trimmed ? "Enter a valid email address" : "Enter your email address")}
              </p>
            ) : null}
          </div>
          {error ? (
            <div role="alert" className="flex animate-pop gap-3 rounded-lg border border-status-critical/30 bg-status-critical/8 px-3.5 py-3 text-sm">
              {error.rate ? (
                <Clock className="mt-0.5 size-4 shrink-0 text-status-warning" aria-hidden />
              ) : (
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-status-critical" aria-hidden />
              )}
              <p>{error.text}</p>
            </div>
          ) : null}
          <Button type="submit" size="lg" className="h-11 w-full text-[15px]">
            {state === "sending" ? <Loader2 className="animate-spin" aria-hidden /> : null} {t("Send reset link")}
          </Button>
        </fieldset>
      </form>
    </AuthLayout>
  );
}
