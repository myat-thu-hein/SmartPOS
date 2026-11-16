import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

let permissions = new Set<string>();
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ permissions }) }));
vi.mock("next/navigation", () => ({ usePathname: () => "/kitchen" }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

const { SidebarNav, routePermission } = await import("@/components/layout/sidebar-nav");

describe("SidebarNav", () => {
  it("renders only the links a kitchen user may open and marks the current page", () => {
    permissions = new Set(["menu:read", "kitchen:read", "kitchen:update"]);
    render(<SidebarNav />);
    const links = screen.getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/kitchen"]);
    expect(links[0]).toHaveAttribute("aria-current", "page");
  });

  it("shows management links to managers", () => {
    permissions = new Set(["orders:read", "inventory:read", "settings:write", "staff:manage", "analytics:read"]);
    render(<SidebarNav />);
    expect(screen.getByRole("link", { name: "Inventory" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Administration" })).not.toBeInTheDocument();
  });

  it("maps nested routes to the permission of their section", () => {
    expect(routePermission("/purchase-orders/123")).toBe("purchasing:read");
    expect(routePermission("/orders/abc")).toBe("orders:read");
    expect(routePermission("/no-access")).toBeNull();
  });
});
