import { Suspense } from "react";

import { AppShell, ShellLoading } from "@/components/layout/app-shell";
import { AuthProvider } from "@/lib/auth";
import { RealtimeProvider } from "@/lib/realtime";

// Authenticated pages wait for the session check (and load their data in the
// browser), so navigations into them are allowed to block briefly.
export const instant = false;

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <AuthProvider>
      {/* Live updates: keeps every screen in sync with changes made elsewhere. */}
      <RealtimeProvider>
        {/* The shell reads the pathname, which is only known in the browser for
            dynamic routes such as /orders/[id]. */}
        <Suspense fallback={<ShellLoading />}>
          <AppShell>{children}</AppShell>
        </Suspense>
      </RealtimeProvider>
    </AuthProvider>
  );
}
