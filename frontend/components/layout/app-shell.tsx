"use client";

import {
  Building2,
  Check,
  ChevronsUpDown,
  KeyRound,
  Languages,
  Loader2,
  LogOut,
  Menu,
  Monitor,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Sun,
  UtensilsCrossed,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { ChangePasswordDialog } from "@/components/layout/change-password-dialog";
import { CommandPalette } from "@/components/layout/command-palette";
import { LiveToasts } from "@/components/layout/live-toasts";
import { LiveStatusIndicator, NotificationCenter } from "@/components/layout/notification-center";
import { routePermission, SidebarNav } from "@/components/layout/sidebar-nav";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetDescription, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ErrorState } from "@/components/shared/query-state";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { homePath } from "@/lib/navigation";
import { useTheme } from "@/lib/theme";
import { humanize } from "@/lib/format";
import { cn } from "@/lib/utils";

function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <Link
      href="/"
      aria-label="SmartPOS AI home"
      className={cn("flex h-16 shrink-0 items-center gap-2.5 font-semibold", collapsed ? "justify-center px-2" : "px-5")}
    >
      <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-card">
        <UtensilsCrossed className="size-4" aria-hidden />
      </span>
      {collapsed ? null : (
        <span className="tracking-tight">
          SmartPOS <span className="text-primary">AI</span>
        </span>
      )}
    </Link>
  );
}

const COLLAPSE_KEY = "smartpos.sidebarCollapsed";

/** Desktop sidebar width preference, remembered in this browser only. */
function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return typeof window !== "undefined" && window.localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setCollapsed((value) => {
      try {
        window.localStorage.setItem(COLLAPSE_KEY, value ? "0" : "1");
      } catch {
        // Storage unavailable: the choice lasts for this visit.
      }
      return !value;
    });
  return [collapsed, toggle];
}

function RestaurantSwitcher() {
  const { me, membership, selectRestaurant } = useAuth();
  const memberships = me?.memberships ?? [];
  if (!membership) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" className="max-w-56 justify-between gap-2 px-2.5 sm:px-3" aria-label="Switch restaurant">
          <Building2 aria-hidden />
          <span className="hidden truncate md:inline">{membership.restaurant_name}</span>
          {memberships.length > 1 ? <ChevronsUpDown className="opacity-50" aria-hidden /> : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>Restaurants</DropdownMenuLabel>
        {memberships.map((m) => (
          <DropdownMenuItem key={m.restaurant_id} onSelect={() => selectRestaurant(m.restaurant_id)}>
            {m.restaurant_id === membership.restaurant_id ? <Check /> : <span className="size-4" />}
            <span className="truncate">{m.restaurant_name}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const { me, membership, logout } = useAuth();
  const { language, setLanguage, t } = useI18n();
  const { theme, setTheme } = useTheme();
  const [changingPassword, setChangingPassword] = useState(false);
  if (!me) return null;
  const role = me.user.is_platform_admin ? "Administrator" : membership?.role ? humanize(membership.role) : "";
  const initials =
    me.user.full_name
      .replace(/[^\p{L}\s]/gu, "")
      .split(/\s+/)
      .filter(Boolean)
      .map((p) => p[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "?";
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" className="gap-2 px-2" aria-label="Account menu">
            <span className="flex size-8 items-center justify-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">
              {initials}
            </span>
            <span className="hidden text-left leading-tight md:block">
              <span className="block text-sm font-medium">{me.user.full_name}</span>
              <span className="block text-xs text-muted-foreground">{role}</span>
            </span>
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel className="font-normal">
            <span className="block font-medium">{me.user.full_name}</span>
            <span className="block truncate text-xs text-muted-foreground">{me.user.email}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="flex items-center gap-2 text-xs text-muted-foreground">
            <Languages className="size-3.5" /> {t("Language")}
          </DropdownMenuLabel>
          <DropdownMenuItem onSelect={() => setLanguage("en")}>
            {language === "en" ? <Check /> : <span className="size-4" />} English
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setLanguage("th")}>
            {language === "th" ? <Check /> : <span className="size-4" />} ภาษาไทย
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {(
            [
              ["light", "Light", Sun],
              ["dark", "Dark", Moon],
              ["system", "System", Monitor],
            ] as const
          ).map(([value, label, Icon]) => (
            <DropdownMenuItem key={value} onSelect={() => setTheme(value)}>
              <Icon /> {label}
              {theme === value ? <Check className="ml-auto" /> : null}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setChangingPassword(true)}>
            <KeyRound /> Change password
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => logout()}>
            <LogOut /> {t("Sign out")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ChangePasswordDialog open={changingPassword} onOpenChange={setChangingPassword} />
    </>
  );
}

function AccessDenied() {
  const { permissions } = useAuth();
  return (
    <div className="mx-auto max-w-lg py-16">
      <ErrorState error={new Error("Your role does not include access to this page.")} />
      <div className="mt-4 text-center">
        <Button asChild variant="outline">
          <Link href={homePath(permissions)}>Go to my start page</Link>
        </Button>
      </div>
    </div>
  );
}

export function ShellLoading() {
  return (
    <div className="flex min-h-dvh items-center justify-center text-muted-foreground">
      <Loader2 className="mr-2 size-5 animate-spin" /> Loading SmartPOS…
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { me, isLoading, error, membership, permissions } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [collapsed, toggleCollapsed] = useSidebarCollapsed();

  if (isLoading) return <ShellLoading />;
  if (error || !me) {
    return (
      <div className="mx-auto max-w-lg py-24">
        <ErrorState error={error ?? new Error("Not signed in.")} />
        <div className="mt-4 text-center">
          <Button asChild>
            <Link href="/login">Sign in</Link>
          </Button>
        </div>
      </div>
    );
  }
  if (!membership && !me.user.is_platform_admin) {
    return (
      <div className="mx-auto max-w-lg py-24 text-center">
        <ErrorState error={new Error("Your account is not assigned to any active restaurant yet. Ask a manager or administrator.")} />
      </div>
    );
  }
  const required = routePermission(pathname);
  const allowed = !required || permissions.has(required);

  return (
    <div className="flex min-h-dvh">
      <aside
        className={cn(
          "no-print sticky top-0 hidden h-dvh shrink-0 flex-col border-r border-sidebar-border bg-sidebar transition-[width] duration-200 ease-out lg:flex",
          collapsed ? "w-[72px]" : "w-64",
        )}
      >
        <Brand collapsed={collapsed} />
        <div className="min-h-0 flex-1 overflow-y-auto pt-2">
          <SidebarNav collapsed={collapsed} />
        </div>
        <div className={cn("flex items-center border-t border-sidebar-border p-2", collapsed ? "justify-center" : "justify-between")}>
          {collapsed ? null : <span className="px-3 text-[11px] text-muted-foreground">SmartPOS AI</span>}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleCollapsed}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="no-print sticky top-0 z-30 flex h-16 items-center gap-2 border-b bg-background/85 px-3 backdrop-blur-md sm:gap-3 sm:px-6">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
                <Menu />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 overflow-y-auto bg-sidebar p-0">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <SheetDescription className="sr-only">Main navigation</SheetDescription>
              <Brand />
              <SidebarNav onNavigate={() => setOpen(false)} />
            </SheetContent>
          </Sheet>
          <RestaurantSwitcher />
          <div className="flex min-w-0 flex-1 justify-center px-1">
            <CommandPalette />
          </div>
          <div className="flex items-center gap-1 sm:gap-2">
            <DemoBadge />
            <LiveStatusIndicator />
            {membership ? <NotificationCenter /> : null}
            <UserMenu />
          </div>
        </header>
        <main className="flex-1 px-4 py-6 sm:px-6 lg:px-8">
          <div key={pathname} className="mx-auto w-full max-w-[1600px] animate-rise">
            {allowed ? children : <AccessDenied />}
          </div>
        </main>
        {membership ? <LiveToasts /> : null}
      </div>
    </div>
  );
}

function DemoBadge() {
  const { membership } = useAuth();
  if (!membership?.is_demo) return null;
  return (
    <Badge variant="warning" className="hidden sm:inline-flex" title="This restaurant contains synthetic demo data">
      Demo data
    </Badge>
  );
}
