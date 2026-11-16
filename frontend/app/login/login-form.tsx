"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  ArrowRight,
  Check,
  CheckCircle2,
  ChefHat,
  Clock,
  Info,
  Loader2,
  Mail,
  ShieldCheck,
  ShoppingCart,
  UserRound,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { IconInput, PasswordInput } from "@/components/auth/auth-inputs";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { api, ApiError, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { humanize } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { homePath } from "@/lib/navigation";
import { cn } from "@/lib/utils";
import type { DemoInfo, DemoRoleName, Me } from "@/types/api";

export const loginSchema = z.object({
  email: z.string().trim().min(1, "Enter your email address").pipe(z.email("Enter a valid email address")),
  password: z.string().min(1, "Enter your password"),
});
type LoginValues = z.infer<typeof loginSchema>;

type FormError =
  | { kind: "credentials" }
  | { kind: "rate"; retryAt: number; at: number }
  | { kind: "network" }
  | { kind: "other"; message: string };

function safeNext(): string | null {
  const next = new URLSearchParams(window.location.search).get("next");
  // Only same-site relative paths (prevents open redirects).
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

function landingPath(me: Pick<Me, "user" | "memberships">): string {
  // An administrator without any restaurant yet starts in Administration.
  const permissions = me.memberships[0]?.permissions ?? (me.user.is_platform_admin ? ["platform:admin"] : []);
  return safeNext() ?? homePath(permissions);
}

function toFormError(error: unknown): FormError {
  if (error instanceof ApiError) {
    if (error.status === 429 || error.code === "rate_limited") {
      const details = (error.details ?? {}) as { retry_after?: number };
      const seconds = typeof details.retry_after === "number" && details.retry_after > 0 ? details.retry_after : 60;
      const at = Date.now();
      return { kind: "rate", retryAt: at + seconds * 1000, at };
    }
    if (error.status === 401) return { kind: "credentials" };
    if (error.status === 0) return { kind: "network" };
  }
  return { kind: "other", message: errorMessage(error) };
}

function clock(totalSeconds: number): string {
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Why the visitor is on the sign-in page, from ?reason= (session ended, signed out, password reset). */
function StatusBanner() {
  const { t } = useI18n();
  const reason = useSearchParams().get("reason");
  const banners = {
    session: { icon: Info, tone: "border-series-1/30 bg-series-1/8", iconTone: "text-series-1", title: "Your session ended", text: "Sign in again to continue where you left off." },
    signedout: { icon: CheckCircle2, tone: "border-status-good/30 bg-status-good/8", iconTone: "text-status-good-text", title: "You're signed out", text: "Sign in again whenever you're ready." },
    reset: { icon: CheckCircle2, tone: "border-status-good/30 bg-status-good/8", iconTone: "text-status-good-text", title: "Password updated", text: "Sign in with your new password." },
  } as const;
  const banner = reason && reason in banners ? banners[reason as keyof typeof banners] : null;
  if (!banner) return null;
  const Icon = banner.icon;
  return (
    <div role="status" className={cn("mb-6 flex gap-3 rounded-lg border px-3.5 py-3 text-sm", banner.tone)}>
      <Icon className={cn("mt-0.5 size-4 shrink-0", banner.iconTone)} aria-hidden />
      <div>
        <p className="font-medium">{t(banner.title)}</p>
        <p className="text-muted-foreground">{t(banner.text)}</p>
      </div>
    </div>
  );
}

function FormAlert({ error, now }: { error: FormError; now: number }) {
  const { t } = useI18n();
  if (error.kind === "rate") {
    const remaining = Math.max(0, Math.ceil((error.retryAt - now) / 1000));
    return (
      <div role="alert" className="flex animate-pop gap-3 rounded-lg border border-status-warning/50 bg-status-warning/10 px-3.5 py-3 text-sm">
        <Clock className="mt-0.5 size-4 shrink-0 text-status-warning" aria-hidden />
        <div>
          <p className="font-medium">{t("Too many sign-in attempts")}</p>
          <p className="text-muted-foreground">
            {remaining > 0 ? (
              <>
                {t("Sign-in is paused for this account. Try again in")}{" "}
                <span className="font-medium text-foreground tabular">{clock(remaining)}</span>.
              </>
            ) : (
              t("You can try again now.")
            )}
          </p>
        </div>
      </div>
    );
  }
  const content =
    error.kind === "credentials"
      ? { icon: AlertCircle, title: t("Email or password is incorrect"), text: t("Check both and try again. Passwords are case-sensitive.") }
      : error.kind === "network"
        ? { icon: WifiOff, title: t("Can't reach SmartPOS"), text: t("Check your connection and try again.") }
        : { icon: AlertCircle, title: t("Sign-in failed"), text: error.message };
  const Icon = content.icon;
  return (
    <div role="alert" className="flex animate-pop gap-3 rounded-lg border border-status-critical/30 bg-status-critical/8 px-3.5 py-3 text-sm">
      <Icon className="mt-0.5 size-4 shrink-0 text-status-critical" aria-hidden />
      <div>
        <p className="font-medium">{content.title}</p>
        <p className="text-muted-foreground">{content.text}</p>
      </div>
    </div>
  );
}

function initials(name: string): string {
  return (
    name
      .replace(/[^\p{L}\s]/gu, "")
      .split(/\s+/)
      .filter(Boolean)
      .map((p) => p[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?"
  );
}

/** Shown when a session already exists: continue, or switch account (useful on shared tills). */
function SignedInPanel({ me, continuing, onContinue }: { me: Me; continuing: boolean; onContinue: () => void }) {
  const { t } = useI18n();
  const { logout } = useAuth();
  const membership = me.memberships[0];
  return (
    <div className="grid gap-5">
      <p className="-mt-2 text-sm font-medium text-status-good-text">{t("You're already signed in")}</p>
      <div className="flex items-center gap-3 rounded-xl border bg-muted/40 p-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary text-sm font-semibold text-primary-foreground">
          {initials(me.user.full_name)}
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium">{me.user.full_name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {me.user.email}
            {membership ? ` · ${membership.role ? humanize(membership.role) : ""} at ${membership.restaurant_name}` : ""}
          </p>
        </div>
      </div>
      <Button size="lg" className="h-11 w-full" onClick={onContinue} disabled={continuing}>
        {continuing ? <Loader2 className="animate-spin" aria-hidden /> : null} {t("Continue")}
        {continuing ? null : <ArrowRight aria-hidden />}
      </Button>
      <Button variant="ghost" className="w-full" onClick={() => void logout()} disabled={continuing}>
        {t("Use another account")}
      </Button>
    </div>
  );
}

const DEMO_ICONS: Record<DemoRoleName, typeof UserRound> = { MANAGER: UserRound, CASHIER: ShoppingCart, KITCHEN: ChefHat };

function useDemoInfo() {
  return useQuery({
    queryKey: ["auth", "demo"],
    queryFn: () => api<DemoInfo>("/auth/demo", { noRestaurant: true }),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

/** One-click access to the demo restaurant, shown only when the server enables it. */
function DemoAccess({ disabled, onSignedIn, onError }: { disabled: boolean; onSignedIn: (me: Me) => void; onError: (e: unknown) => void }) {
  const { t } = useI18n();
  const { demoLogin } = useAuth();
  const [pending, setPending] = useState<DemoRoleName | null>(null);
  const demo = useDemoInfo();
  if (!demo.data?.enabled) return null;
  return (
    <section aria-labelledby="demo-heading" className="grid gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 id="demo-heading" className="text-sm font-semibold">
          {t("Try the live demo")}
        </h2>
        <span className="rounded-full bg-accent px-2 py-0.5 text-[11px] font-medium text-accent-foreground">{t("No account needed")}</span>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {demo.data.roles.map((r) => {
          const Icon = DEMO_ICONS[r.role];
          return (
            <button
              key={r.role}
              type="button"
              disabled={disabled || pending !== null}
              title={r.description}
              aria-label={`${r.label}: ${r.description}`}
              onClick={async () => {
                setPending(r.role);
                try {
                  onSignedIn(await demoLogin(r.role));
                } catch (error) {
                  onError(error);
                  setPending(null);
                }
              }}
              className="group flex flex-col items-center gap-2 rounded-xl border bg-background px-2 py-3 text-center transition-all hover:-translate-y-0.5 hover:border-primary/50 hover:shadow-card focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:pointer-events-none disabled:opacity-60 motion-reduce:transform-none"
            >
              <span className="flex size-9 items-center justify-center rounded-lg bg-accent text-accent-foreground transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                {pending === r.role ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Icon className="size-4" aria-hidden />}
              </span>
              <span className="text-sm font-medium">{r.label}</span>
            </button>
          );
        })}
      </div>
      <div className="flex items-center gap-3 py-1 text-xs text-muted-foreground" aria-hidden>
        <span className="h-px flex-1 bg-border" /> {t("or sign in with email")} <span className="h-px flex-1 bg-border" />
      </div>
    </section>
  );
}

const DEV_ACCOUNTS = ["manager", "cashier", "kitchen", "admin"] as const;

export function LoginForm({ showDemoHint = false }: { showDemoHint?: boolean }) {
  const { login, me } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [formError, setFormError] = useState<FormError | null>(null);
  const [remember, setRemember] = useState(true);
  // Where a successful sign-in came from: the form/demo buttons, or the signed-in panel.
  const [redirecting, setRedirecting] = useState<"form" | "panel" | null>(null);
  // Only used while sign-in is paused; a rate-limit error sets it (no clock read during prerender).
  const [now, setNow] = useState(0);
  const demoEnabled = !!useDemoInfo().data?.enabled;
  const {
    register,
    handleSubmit,
    setFocus,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { email: "", password: "" } });

  // Tick once a second while sign-in is paused, so the countdown and button stay current.
  const retryAt = formError?.kind === "rate" ? formError.retryAt : null;
  useEffect(() => {
    if (retryAt === null) return;
    const id = setInterval(() => {
      setNow(Date.now());
      if (Date.now() >= retryAt) clearInterval(id);
    }, 1000);
    return () => clearInterval(id);
  }, [retryAt]);
  const paused = retryAt !== null && retryAt > now;

  const finish = (signedIn: Me, source: "form" | "panel" = "form") => {
    setRedirecting(source);
    router.replace(landingPath(signedIn));
  };

  const fail = (error: unknown) => {
    const next = toFormError(error);
    if (next.kind === "rate") setNow(next.at);
    setFormError(next);
    if (next.kind === "credentials") {
      // Keep the email, put the cursor back in the password with its text selected.
      setFocus("password");
      requestAnimationFrame(() => (document.getElementById("password") as HTMLInputElement | null)?.select());
    }
  };

  async function onSubmit(values: LoginValues) {
    setFormError(null);
    try {
      finish(await login(values.email, values.password, remember));
    } catch (error) {
      fail(error);
    }
  }

  // Typing again clears a stale error, but never hides an active pause.
  const clearError = () => setFormError((current) => (current?.kind === "rate" ? current : null));

  // A session already exists (and this page did not just create it).
  if (me && redirecting !== "form" && !isSubmitting) {
    return <SignedInPanel me={me} continuing={redirecting === "panel"} onContinue={() => finish(me, "panel")} />;
  }

  const busy = isSubmitting || redirecting !== null;
  const fieldError = (message?: string) =>
    message ? (
      <p role="alert" className="text-xs font-medium text-status-critical">
        {t(message)}
      </p>
    ) : null;

  return (
    <div className="grid">
      <Suspense fallback={null}>
        <StatusBanner />
      </Suspense>
      <DemoAccess disabled={busy} onSignedIn={finish} onError={fail} />
      <form onSubmit={handleSubmit(onSubmit)} noValidate className={cn(demoEnabled && "mt-3")}>
        <fieldset disabled={busy} className="grid gap-5">
          <div className="grid gap-1.5">
            <Label htmlFor="email">{t("Email")}</Label>
            <IconInput
              icon={Mail}
              id="email"
              type="email"
              inputMode="email"
              autoComplete="username"
              autoCapitalize="none"
              autoCorrect="off"
              spellCheck={false}
              placeholder="name@restaurant.com"
              autoFocus
              aria-invalid={!!errors.email || formError?.kind === "credentials"}
              {...register("email", { onChange: clearError })}
            />
            {fieldError(errors.email?.message)}
          </div>
          <div className="grid gap-1.5">
            <div className="flex items-center justify-between gap-2">
              <Label htmlFor="password">{t("Password")}</Label>
              <Link href="/forgot-password" className="text-xs font-medium text-primary hover:underline focus-visible:underline">
                {t("Forgot password?")}
              </Link>
            </div>
            <PasswordInput
              id="password"
              autoComplete="current-password"
              aria-invalid={!!errors.password || formError?.kind === "credentials"}
              {...register("password", { onChange: clearError })}
            />
            {fieldError(errors.password?.message)}
          </div>

          <label className="flex w-fit cursor-pointer items-center gap-2.5 text-sm select-none">
            <Checkbox checked={remember} onCheckedChange={(v) => setRemember(v === true)} aria-label={t("Keep me signed in")} />
            <span>{t("Keep me signed in")}</span>
          </label>

          {formError ? <FormAlert error={formError} now={now} /> : null}

          <Button type="submit" size="lg" className="h-11 w-full text-[15px]" disabled={paused}>
            {redirecting ? (
              <>
                <Check aria-hidden /> {t("Signed in")}
              </>
            ) : isSubmitting ? (
              <>
                <Loader2 className="animate-spin" aria-hidden /> {t("Signing in…")}
              </>
            ) : (
              t("Sign in")
            )}
          </Button>
        </fieldset>
      </form>

      {showDemoHint && !demoEnabled ? (
        <div className="mt-6 rounded-xl border border-dashed bg-muted/40 p-4">
          <p className="flex items-center gap-1.5 text-xs font-semibold">
            <ShieldCheck className="size-3.5 text-primary" aria-hidden /> {t("Demo accounts")}
            <span className="font-normal text-muted-foreground">· local development</span>
          </p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {DEV_ACCOUNTS.map((key) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setValue("email", `${key}@smartpos.demo`);
                  clearError();
                  setFocus("password");
                }}
                className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium transition-colors hover:border-primary/50 hover:text-primary"
              >
                {key[0].toUpperCase() + key.slice(1)}
              </button>
            ))}
          </div>
          <p className="mt-2.5 text-xs text-muted-foreground">
            Fills the email. The password is the <code className="rounded bg-muted px-1">DEMO_PASSWORD</code> in your{" "}
            <code className="rounded bg-muted px-1">.env</code>; changing it and re-running the seed updates the accounts.
          </p>
        </div>
      ) : null}
    </div>
  );
}
