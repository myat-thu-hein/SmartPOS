import { ShieldOff } from "lucide-react";
import type { Metadata } from "next";

import { EmptyState } from "@/components/shared/empty-state";

export const metadata: Metadata = { title: "No access" };

export default function NoAccessPage() {
  return (
    <div className="py-16">
      <EmptyState
        icon={ShieldOff}
        title="No pages available for your role"
        description="Your account is signed in, but your role in this restaurant does not include any screens. Ask a manager to check your role."
      />
    </div>
  );
}
