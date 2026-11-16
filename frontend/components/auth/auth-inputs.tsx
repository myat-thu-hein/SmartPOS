"use client";

import { ArrowBigUpDash, Eye, EyeOff, Lock, type LucideIcon } from "lucide-react";
import { useState, type ComponentProps, type KeyboardEvent } from "react";

import { Input } from "@/components/ui/input";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const FIELD = "h-11 rounded-lg bg-background pl-10 text-[15px] md:text-sm dark:bg-input/20";

/** Text input with a leading icon, sized for touch screens (44 px). */
export function IconInput({ icon: Icon, className, ...props }: ComponentProps<"input"> & { icon: LucideIcon }) {
  return (
    <div className="relative">
      <Icon
        className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input className={cn(FIELD, className)} {...props} />
    </div>
  );
}

/**
 * Password field with a show/hide toggle and a Caps Lock warning. Accepts the
 * props react-hook-form's register() returns (ref, name, onChange, onBlur).
 */
export function PasswordInput({ className, onKeyDown, onKeyUp, onBlur, ...props }: ComponentProps<"input">) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const detect = (event: KeyboardEvent<HTMLInputElement>) => {
    if (typeof event.getModifierState === "function") setCapsLock(event.getModifierState("CapsLock"));
  };
  return (
    <div className="grid gap-1.5">
      <div className="relative">
        <Lock
          className="pointer-events-none absolute top-1/2 left-3.5 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type={visible ? "text" : "password"}
          className={cn(FIELD, "pr-12", className)}
          onKeyDown={(event) => {
            detect(event);
            onKeyDown?.(event);
          }}
          onKeyUp={(event) => {
            detect(event);
            onKeyUp?.(event);
          }}
          onBlur={(event) => {
            setCapsLock(false);
            onBlur?.(event);
          }}
          {...props}
        />
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? t("Hide password") : t("Show password")}
          aria-pressed={visible}
          aria-controls={props.id}
          disabled={props.disabled}
          className="absolute top-1/2 right-1.5 flex size-8 -translate-y-1/2 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none disabled:opacity-50"
        >
          {visible ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
        </button>
      </div>
      {capsLock ? (
        <p role="status" className="flex items-center gap-1.5 text-xs font-medium text-foreground">
          <ArrowBigUpDash className="size-3.5 text-status-warning" aria-hidden /> {t("Caps Lock is on")}
        </p>
      ) : null}
    </div>
  );
}
