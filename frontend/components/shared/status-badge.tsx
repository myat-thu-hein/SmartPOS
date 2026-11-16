import {
  Ban,
  CheckCircle2,
  CircleDashed,
  CircleDot,
  Clock,
  CookingPot,
  PackageCheck,
  PackageOpen,
  Send,
  Sparkles,
  Undo2,
  Wallet,
  XCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { humanize } from "@/lib/format";
import type {
  KitchenStatus,
  OrderStatus,
  PaymentStatus,
  PurchaseOrderStatus,
  RecommendationStatus,
  TableStatus,
} from "@/types/api";

type Variant = "default" | "secondary" | "outline" | "success" | "warning" | "danger" | "info";
type Spec = { variant: Variant; icon: LucideIcon; label?: string };

function StatusBadge({ value, map }: { value: string; map: Record<string, Spec> }) {
  const spec = map[value] ?? { variant: "outline", icon: CircleDot };
  const Icon = spec.icon;
  return (
    <Badge variant={spec.variant}>
      <Icon aria-hidden />
      {spec.label ?? humanize(value)}
    </Badge>
  );
}

const ORDER: Record<OrderStatus, Spec> = {
  DRAFT: { variant: "outline", icon: CircleDashed },
  CONFIRMED: { variant: "info", icon: Send },
  PREPARING: { variant: "warning", icon: CookingPot },
  READY: { variant: "success", icon: Sparkles },
  COMPLETED: { variant: "secondary", icon: CheckCircle2 },
  CANCELLED: { variant: "danger", icon: Ban },
};

const PAYMENT: Record<PaymentStatus, Spec> = {
  UNPAID: { variant: "outline", icon: Clock },
  PARTIALLY_PAID: { variant: "warning", icon: Wallet, label: "Part paid" },
  PAID: { variant: "success", icon: CheckCircle2 },
  PARTIALLY_REFUNDED: { variant: "warning", icon: Undo2, label: "Part refunded" },
  REFUNDED: { variant: "danger", icon: Undo2 },
};

const TABLE: Record<TableStatus, Spec> = {
  AVAILABLE: { variant: "success", icon: CheckCircle2 },
  OCCUPIED: { variant: "info", icon: CircleDot },
  RESERVED: { variant: "warning", icon: Clock },
  CLEANING: { variant: "secondary", icon: Sparkles },
};

const PO: Record<PurchaseOrderStatus, Spec> = {
  DRAFT: { variant: "outline", icon: CircleDashed },
  SUBMITTED: { variant: "info", icon: Send },
  PARTIALLY_RECEIVED: { variant: "warning", icon: PackageOpen, label: "Part received" },
  RECEIVED: { variant: "success", icon: PackageCheck },
  CANCELLED: { variant: "danger", icon: XCircle },
};

const REC: Record<RecommendationStatus, Spec> = {
  PENDING: { variant: "warning", icon: Clock },
  APPROVED: { variant: "success", icon: CheckCircle2 },
  MODIFIED: { variant: "info", icon: CheckCircle2 },
  REJECTED: { variant: "danger", icon: XCircle },
  COMPLETED: { variant: "secondary", icon: PackageCheck, label: "PO created" },
};

const KITCHEN: Record<KitchenStatus, Spec> = {
  NEW: { variant: "info", icon: Send },
  PREPARING: { variant: "warning", icon: CookingPot },
  READY: { variant: "success", icon: Sparkles },
  COMPLETED: { variant: "secondary", icon: CheckCircle2 },
};

export const OrderStatusBadge = ({ status }: { status: OrderStatus }) => <StatusBadge value={status} map={ORDER} />;
export const PaymentStatusBadge = ({ status }: { status: PaymentStatus }) => (
  <StatusBadge value={status} map={PAYMENT} />
);
export const TableStatusBadge = ({ status }: { status: TableStatus }) => <StatusBadge value={status} map={TABLE} />;
export const PurchaseOrderStatusBadge = ({ status }: { status: PurchaseOrderStatus }) => (
  <StatusBadge value={status} map={PO} />
);
export const RecommendationStatusBadge = ({ status }: { status: RecommendationStatus }) => (
  <StatusBadge value={status} map={REC} />
);
export const KitchenStatusBadge = ({ status }: { status: KitchenStatus }) => (
  <StatusBadge value={status} map={KITCHEN} />
);
