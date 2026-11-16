"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { NAV_ITEMS, visibleNavItems } from "@/lib/navigation";
import { cn } from "@/lib/utils";

const SECTIONS = ["Operations", "Inventory", "Insights", "Management"] as const;

export function SidebarNav({ onNavigate, collapsed = false }: { onNavigate?: () => void; collapsed?: boolean }) {
  const pathname = usePathname();
  const { permissions } = useAuth();
  const { t } = useI18n();
  const items = visibleNavItems(permissions);
  return (
    <nav aria-label="Main" className={cn("flex flex-col gap-5 pb-6", collapsed ? "px-2" : "px-3")}>
      {SECTIONS.map((section) => {
        const sectionItems = items.filter((i) => i.section === section);
        if (!sectionItems.length) return null;
        return (
          <div key={section} className="flex flex-col gap-0.5">
            {collapsed ? (
              <span className="mx-auto mb-1 h-px w-6 bg-sidebar-border" aria-hidden />
            ) : (
              <p className="px-3 pb-1 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                {t(section)}
              </p>
            )}
            {sectionItems.map((item) => {
              const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
              const Icon = item.icon;
              const label = t(item.label);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  aria-label={collapsed ? label : undefined}
                  title={collapsed ? label : undefined}
                  className={cn(
                    "group relative flex items-center gap-3 rounded-lg py-2 text-sm font-medium text-sidebar-foreground/75 transition-colors hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
                    collapsed ? "justify-center px-2" : "px-3",
                    active && "bg-sidebar-accent text-sidebar-accent-foreground",
                  )}
                >
                  {active ? (
                    <span className="absolute inset-y-1.5 -left-2 w-1 rounded-r-full bg-primary" aria-hidden />
                  ) : null}
                  <Icon
                    className={cn("size-4 shrink-0 transition-colors", active ? "text-primary" : "text-muted-foreground group-hover:text-current")}
                    aria-hidden
                  />
                  {collapsed ? null : <span className="truncate">{label}</span>}
                </Link>
              );
            })}
          </div>
        );
      })}
    </nav>
  );
}

export function routePermission(pathname: string): string | null {
  const match = NAV_ITEMS.filter((i) => pathname === i.href || pathname.startsWith(`${i.href}/`)).sort(
    (a, b) => b.href.length - a.href.length,
  )[0];
  return match?.permission ?? null;
}
