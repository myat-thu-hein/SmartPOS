import {
  BarChart3,
  Bot,
  Boxes,
  ChefHat,
  ClipboardList,
  CookingPot,
  FileSpreadsheet,
  LayoutDashboard,
  LayoutGrid,
  type LucideIcon,
  Settings,
  Shield,
  ShoppingCart,
  TrendingUp,
  Truck,
  UserCog,
  Users,
  UtensilsCrossed,
  ReceiptText,
} from "lucide-react";

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  /** The user must hold this permission in the active restaurant. */
  permission: string;
  section: "Operations" | "Inventory" | "Insights" | "Management";
}

// The backend enforces the same permissions; hiding items is only for clarity.
export const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", icon: LayoutDashboard, permission: "orders:read", section: "Operations" },
  { label: "POS", href: "/pos", icon: ShoppingCart, permission: "orders:create", section: "Operations" },
  { label: "Orders", href: "/orders", icon: ReceiptText, permission: "orders:read", section: "Operations" },
  { label: "Tables", href: "/tables", icon: LayoutGrid, permission: "tables:read", section: "Operations" },
  { label: "Kitchen Display", href: "/kitchen", icon: ChefHat, permission: "kitchen:read", section: "Operations" },
  { label: "Customers", href: "/customers", icon: Users, permission: "customers:read", section: "Operations" },
  { label: "Menu", href: "/menu", icon: UtensilsCrossed, permission: "menu:write", section: "Inventory" },
  { label: "Recipes", href: "/recipes", icon: CookingPot, permission: "recipes:read", section: "Inventory" },
  { label: "Inventory", href: "/inventory", icon: Boxes, permission: "inventory:read", section: "Inventory" },
  { label: "Suppliers", href: "/suppliers", icon: Truck, permission: "suppliers:read", section: "Inventory" },
  {
    label: "Purchase Orders",
    href: "/purchase-orders",
    icon: ClipboardList,
    permission: "purchasing:read",
    section: "Inventory",
  },
  { label: "Analytics", href: "/analytics", icon: BarChart3, permission: "analytics:read", section: "Insights" },
  { label: "Forecasting", href: "/forecasting", icon: TrendingUp, permission: "forecast:read", section: "Insights" },
  { label: "AI Assistant", href: "/assistant", icon: Bot, permission: "ai:use", section: "Insights" },
  { label: "Reports", href: "/reports", icon: FileSpreadsheet, permission: "reports:read", section: "Insights" },
  { label: "User Management", href: "/users", icon: UserCog, permission: "staff:manage", section: "Management" },
  { label: "Settings", href: "/settings", icon: Settings, permission: "settings:write", section: "Management" },
  { label: "Administration", href: "/admin", icon: Shield, permission: "platform:admin", section: "Management" },
];

export function visibleNavItems(permissions: Iterable<string>): NavItem[] {
  const set = new Set(permissions);
  return NAV_ITEMS.filter((item) => set.has(item.permission));
}

/** Where a user lands after signing in, based on what they can do. */
export function homePath(permissions: Iterable<string>): string {
  const items = visibleNavItems(permissions);
  return items[0]?.href ?? "/no-access";
}
