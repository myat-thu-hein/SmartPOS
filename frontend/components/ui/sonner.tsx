"use client";

import { Toaster as Sonner, type ToasterProps } from "sonner";

function Toaster(props: ToasterProps) {
  return (
    <Sonner
      className="toaster group"
      richColors
      closeButton
      position="top-right"
      // Below the 64px top bar, so toasts never cover the notification bell or account menu.
      offset={{ top: 76, right: 16 }}
      mobileOffset={{ top: 72, right: 12, left: 12 }}
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
        } as React.CSSProperties
      }
      {...props}
    />
  );
}

export { Toaster };
