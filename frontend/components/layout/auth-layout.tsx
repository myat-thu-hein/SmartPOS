"use client";

import { ChefHat, Moon, Package, ReceiptText, ShieldCheck, ShoppingCart, Sparkles, Sun, TrendingUp, UtensilsCrossed, Zap } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { useI18n, type Language } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const FEATURES = [
  { icon: Zap, title: "Live across every screen", text: "Orders reach the kitchen, tables and dashboard in about a second." },
  { icon: TrendingUp, title: "Forecasts you can check", text: "Backtested demand models and reorder suggestions with their maths." },
  { icon: Sparkles, title: "Explainable insights", text: "Stock-out risk, best sellers and add-ons from your own sales." },
];

// The restaurant's day as the product follows it (a description, not data).
const FLOW = [
  { icon: ShoppingCart, label: "Order" },
  { icon: ChefHat, label: "Kitchen" },
  { icon: Package, label: "Stock" },
  { icon: TrendingUp, label: "Forecast" },
  { icon: ReceiptText, label: "Reorder" },
];

function Logo({ inverted = false }: { inverted?: boolean }) {
  return (
    <Link href="/login" className="flex items-center gap-2.5 font-semibold tracking-tight" aria-label="SmartPOS AI">
      <span
        className={cn(
          "flex size-9 items-center justify-center rounded-xl",
          inverted ? "bg-white/12 ring-1 ring-white/20" : "bg-primary text-primary-foreground shadow-card",
        )}
      >
        <UtensilsCrossed className="size-[18px]" aria-hidden />
      </span>
      <span className="text-lg">
        SmartPOS <span className={inverted ? "text-emerald-200" : "text-primary"}>AI</span>
      </span>
    </Link>
  );
}

function BrandPanel() {
  const { t } = useI18n();
  return (
    <aside
      className="relative hidden overflow-hidden text-white lg:flex lg:flex-col lg:justify-between lg:gap-8 lg:p-10 xl:p-14"
      style={{
        backgroundImage:
          // Fallbacks keep the white text readable even if the theme tokens are missing.
          "linear-gradient(160deg, var(--auth-panel-from, #062e2a) 0%, var(--auth-panel-via, #0b5950) 55%, var(--auth-panel-to, #0f6e63) 100%)",
      }}
    >
      {/* Depth without imagery: a faint grid that fades out, and two soft lights. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse at 20% 10%, black 15%, transparent 65%)",
        }}
      />
      <div aria-hidden className="pointer-events-none absolute -top-32 -right-24 size-[460px] rounded-full bg-emerald-300/15 blur-3xl" />
      <div aria-hidden className="pointer-events-none absolute -bottom-40 -left-24 size-[420px] rounded-full bg-teal-200/10 blur-3xl" />

      <div className="relative">
        <Logo inverted />
      </div>

      <div className="relative max-w-xl">
        <p className="mb-4 inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium ring-1 ring-white/15">
          <span className="size-1.5 rounded-full bg-emerald-300" aria-hidden /> {t("Restaurant point of sale")}
        </p>
        <h2 className="text-4xl leading-[1.1] font-semibold tracking-tight text-balance xl:text-5xl">
          {t("Run your restaurant from order to reorder.")}
        </h2>
        <p className="mt-4 max-w-md text-[15px] leading-relaxed text-white/75">
          {t("Sell, cook, count stock and plan purchasing in one place, with every number traceable to the orders behind it.")}
        </p>

        {/* The workflow strip; hidden on short screens so nothing crowds the headline. */}
        <ol className="mt-10 flex items-center gap-1.5 [@media(max-height:760px)]:hidden" aria-label="How SmartPOS follows the day">
          {FLOW.map(({ icon: Icon, label }, i) => (
            <li key={label} className="flex items-center gap-1.5">
              <span className="flex flex-col items-center gap-1.5">
                <span className="flex size-10 items-center justify-center rounded-xl bg-white/10 ring-1 ring-white/15">
                  <Icon className="size-[18px]" aria-hidden />
                </span>
                <span className="text-[11px] font-medium text-white/70">{t(label)}</span>
              </span>
              {i < FLOW.length - 1 ? <span aria-hidden className="mb-5 h-px w-5 bg-white/25 xl:w-8" /> : null}
            </li>
          ))}
        </ol>

        <ul className="mt-10 grid gap-5 [@media(max-height:900px)]:hidden">
          {FEATURES.map(({ icon: Icon, title, text }) => (
            <li key={title} className="flex gap-3.5">
              <span className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg bg-white/10 ring-1 ring-white/15">
                <Icon className="size-4" aria-hidden />
              </span>
              <span>
                <span className="block text-sm font-medium">{t(title)}</span>
                <span className="block text-sm text-white/70">{t(text)}</span>
              </span>
            </li>
          ))}
        </ul>
      </div>

      <p className="relative text-sm text-white/60">ระบบขายหน้าร้านและบริหารร้านอาหารอัจฉริยะ</p>
    </aside>
  );
}

/** Language and theme switches, usable before signing in. */
function AuthControls() {
  const { language, setLanguage, t } = useI18n();
  const { setTheme } = useTheme();
  const toggleTheme = () => setTheme(document.documentElement.classList.contains("dark") ? "light" : "dark");
  return (
    <div className="flex items-center gap-2">
      <div role="group" aria-label={t("Language")} className="flex rounded-lg border bg-card p-0.5 text-xs font-medium shadow-card">
        {(
          [
            ["en", "EN"],
            ["th", "ไทย"],
          ] as [Language, string][]
        ).map(([code, label]) => (
          <button
            key={code}
            type="button"
            onClick={() => setLanguage(code)}
            aria-pressed={language === code}
            lang={code}
            className={cn(
              "rounded-md px-2.5 py-1 text-muted-foreground transition-colors hover:text-foreground",
              language === code && "bg-secondary text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={toggleTheme}
        className="flex size-8 items-center justify-center rounded-lg border bg-card text-muted-foreground shadow-card transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        {/* Both icons render; CSS picks one, so server and client markup always match. */}
        <Moon className="size-4 dark:hidden" aria-hidden />
        <Sun className="hidden size-4 dark:block" aria-hidden />
        <span className="sr-only dark:hidden">{t("Switch to dark theme")}</span>
        <span className="sr-only hidden dark:inline">{t("Switch to light theme")}</span>
      </button>
    </div>
  );
}

export function AuthLayout({
  title,
  subtitle,
  children,
  aside,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** Content below the card, e.g. a link back to sign in. */
  aside?: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className="grid min-h-dvh bg-background lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
      <BrandPanel />
      <div className="relative flex min-h-dvh flex-col">
        {/* A soft wash of the brand colour behind the card. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-accent/70 to-transparent dark:from-accent/30"
        />
        <header className="relative flex items-center justify-between gap-3 px-4 py-4 sm:px-8">
          <span className="lg:invisible">
            <Logo />
          </span>
          <AuthControls />
        </header>
        <main className="relative flex flex-1 items-center justify-center px-4 py-6 sm:px-8">
          <div className="w-full max-w-[440px] animate-rise">
            <div className="sm:rounded-2xl sm:border sm:bg-card sm:p-8 sm:shadow-raised">
              <h1 className="text-2xl font-semibold tracking-tight">{t(title)}</h1>
              {subtitle ? <p className="mt-1.5 text-sm text-muted-foreground">{t(subtitle)}</p> : null}
              <div className="mt-7">{children}</div>
            </div>
            {aside ? <div className="mt-5 text-center text-sm">{aside}</div> : null}
          </div>
        </main>
        <footer className="relative flex items-center justify-center gap-1.5 px-4 pb-5 text-center text-xs text-muted-foreground">
          <ShieldCheck className="size-3.5 shrink-0" aria-hidden />
          {t("Protected by encrypted sessions and role-based access")}
        </footer>
      </div>
    </div>
  );
}
