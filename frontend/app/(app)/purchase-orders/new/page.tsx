"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { PurchaseOrderEditor } from "@/features/purchasing/po-editor";

export default function NewPurchaseOrderPage() {
  const router = useRouter();
  return (
    <>
      <Button asChild variant="ghost" size="sm" className="mb-2 -ml-2">
        <Link href="/purchase-orders">
          <ArrowLeft /> Purchase orders
        </Link>
      </Button>
      <PageHeader
        title="New purchase order"
        description="Saved as a draft. Nothing is sent to the supplier until a manager submits it."
      />
      <PurchaseOrderEditor onSaved={(po) => router.push(`/purchase-orders/${po.id}`)} onCancel={() => router.push("/purchase-orders")} />
    </>
  );
}
