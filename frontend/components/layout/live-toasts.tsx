"use client";

import { usePathname, useRouter } from "next/navigation";
import { toast } from "sonner";

import { useAuth } from "@/lib/auth";
import { useLiveEvents, type LiveEvent } from "@/lib/realtime";

/** Toasts for changes made by other people (your own actions already confirm themselves). */
export function LiveToasts() {
  const { me, can } = useAuth();
  const pathname = usePathname();
  const router = useRouter();

  useLiveEvents((event: LiveEvent) => {
    const mine = !!me && event.actor_user_id === me.user.id;
    const data = event.data as Record<string, string | null | undefined>;
    const number = data.display_number ? `#${data.display_number}` : "";

    if (event.type === "notification.created") {
      // Stock alerts matter even when your own sale caused them; routine notices only from others.
      const severity = data.severity ?? "info";
      if (mine && severity === "info") return;
      const show = severity === "critical" ? toast.error : severity === "warning" ? toast.warning : toast.info;
      const link = data.link;
      show(data.title ?? "New notification", {
        id: `notification-${event.entity_id}`,
        description: data.body ?? undefined,
        action: link ? { label: "View", onClick: () => router.push(link) } : undefined,
      });
      return;
    }
    if (mine) return;

    const onKitchen = pathname.startsWith("/kitchen");
    if (event.type === "order.ready" && !onKitchen && can("orders:create")) {
      const id = event.entity_id;
      toast.success(`Order ${number} is ready`, {
        id: `ready-${id}`,
        description: data.table_id ? "Ready to serve at the table." : "Ready for pickup.",
        action: id ? { label: "Open", onClick: () => router.push(`/orders/${id}`) } : undefined,
      });
    } else if (event.type === "order.confirmed" && onKitchen) {
      toast.info(`New order ${number}`, { id: `new-${event.entity_id}`, description: "Added to the queue." });
    }
  });

  return null;
}
