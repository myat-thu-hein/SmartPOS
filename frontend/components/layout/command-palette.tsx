"use client";

import { CornerDownLeft, Plus, Search, TrendingUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { useAuth } from "@/lib/auth";
import { useI18n } from "@/lib/i18n";
import { visibleNavItems } from "@/lib/navigation";
import { cn } from "@/lib/utils";

interface Command {
  id: string;
  label: string;
  group: string;
  href: string;
  icon: ComponentType<{ className?: string }>;
  keywords?: string;
}

const ACTIONS: (Command & { permission: string })[] = [
  { id: "new-sale", label: "New sale", group: "Actions", href: "/pos", icon: Plus, permission: "orders:create", keywords: "order checkout pos" },
  {
    id: "review-reorders",
    label: "Review reorder suggestions",
    group: "Actions",
    href: "/forecasting?tab=recommendations",
    icon: TrendingUp,
    permission: "recommendations:read",
    keywords: "purchase stock forecast",
  },
];

function isMac() {
  return typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);
}

/** Ctrl/Cmd+K: jump to any page the role allows, or run a common action. */
export function CommandPalette() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key.toLowerCase() === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="flex h-9 w-full max-w-sm items-center gap-2 rounded-lg border bg-muted/40 px-3 text-sm text-muted-foreground transition-colors hover:bg-muted"
        aria-label="Search pages and actions"
        aria-keyshortcuts="Control+K Meta+K"
      >
        <Search className="size-4 shrink-0" aria-hidden />
        <span className="hidden truncate sm:inline">Search or jump to…</span>
        <kbd className="ml-auto hidden rounded border bg-background px-1.5 py-0.5 font-sans text-[11px] md:inline">
          {isMac() ? "⌘" : "Ctrl"} K
        </kbd>
      </button>
      {open ? <PaletteDialog onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function PaletteDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { permissions } = useAuth();
  const { t } = useI18n();
  const [term, setTerm] = useState("");
  const [index, setIndex] = useState(0);
  const listRef = useRef<HTMLUListElement>(null);

  const commands = useMemo<Command[]>(() => {
    const pages = visibleNavItems(permissions).map((item) => ({
      id: item.href,
      label: t(item.label),
      group: "Go to",
      href: item.href,
      icon: item.icon,
      keywords: `${item.label} ${item.section}`,
    }));
    const actions = ACTIONS.filter((a) => permissions.has(a.permission));
    return [...actions, ...pages];
  }, [permissions, t]);

  const results = useMemo(() => {
    const q = term.trim().toLowerCase();
    if (!q) return commands;
    // Label matches beat keyword matches; a label that starts with the term beats one that contains it.
    const rank = (c: Command) => {
      const label = c.label.toLowerCase();
      if (label.startsWith(q) || label.split(/\s+/).some((w) => w.startsWith(q))) return 0;
      if (label.includes(q)) return 1;
      return (c.keywords ?? "").toLowerCase().includes(q) ? 2 : -1;
    };
    return commands
      .map((c, i) => ({ c, i, r: rank(c) }))
      .filter((x) => x.r >= 0)
      .sort((a, b) => a.r - b.r || a.i - b.i)
      .map((x) => x.c);
  }, [commands, term]);

  const run = (command: Command | undefined) => {
    if (!command) return;
    onClose();
    router.push(command.href);
  };

  useEffect(() => {
    listRef.current?.querySelector(`[data-index="${index}"]`)?.scrollIntoView({ block: "nearest" });
  }, [index]);

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="top-[18%] translate-y-0 gap-0 overflow-hidden p-0 sm:max-w-lg" showCloseButton={false}>
        <DialogTitle className="sr-only">Search pages and actions</DialogTitle>
        <DialogDescription className="sr-only">Type to filter, use the arrow keys to choose, Enter to open.</DialogDescription>
        <div className="flex items-center gap-2 border-b px-4">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <input
            autoFocus
            value={term}
            onChange={(e) => {
              setTerm(e.target.value);
              setIndex(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setIndex((i) => Math.min(i + 1, results.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setIndex((i) => Math.max(i - 1, 0));
              } else if (e.key === "Enter") {
                e.preventDefault();
                run(results[index]);
              }
            }}
            placeholder="Search pages and actions…"
            aria-label="Search pages and actions"
            role="combobox"
            aria-expanded
            aria-controls="command-results"
            aria-activedescendant={results[index] ? `command-${results[index].id}` : undefined}
            className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
        </div>
        <ul id="command-results" ref={listRef} role="listbox" className="max-h-80 overflow-y-auto p-2">
          {results.length ? (
            results.map((command, i) => {
              const Icon = command.icon;
              const showGroup = i === 0 || results[i - 1].group !== command.group;
              return (
                <li key={command.id} role="presentation">
                  {showGroup ? (
                    <p className="px-2 pt-2 pb-1 text-[11px] font-medium tracking-wider text-muted-foreground uppercase">
                      {command.group}
                    </p>
                  ) : null}
                  <div
                    id={`command-${command.id}`}
                    role="option"
                    aria-selected={i === index}
                    data-index={i}
                    onMouseMove={() => setIndex(i)}
                    onClick={() => run(command)}
                    className={cn(
                      "flex cursor-pointer items-center gap-3 rounded-md px-2 py-2 text-sm",
                      i === index && "bg-accent text-accent-foreground",
                    )}
                  >
                    <Icon className="size-4 text-muted-foreground" />
                    <span className="flex-1">{command.label}</span>
                    {i === index ? <CornerDownLeft className="size-3.5 text-muted-foreground" aria-hidden /> : null}
                  </div>
                </li>
              );
            })
          ) : (
            <li className="px-2 py-8 text-center text-sm text-muted-foreground">No matching pages or actions.</li>
          )}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
