import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render as baseRender, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChartCard } from "@/components/charts/charts";
import { ErrorState, QueryState } from "@/components/shared/query-state";
import { StatCard } from "@/components/shared/stat-card";
import { ModifierDialog } from "@/features/pos/modifier-dialog";
import { ApiError } from "@/lib/api";
import type { Product } from "@/types/api";

const login = vi.fn();
const demoLogin = vi.fn();
const logout = vi.fn();
const replace = vi.fn();
const apiMock = vi.fn();
const auth = { me: undefined as unknown };
let searchParams = new URLSearchParams();
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ login, demoLogin, logout, me: auth.me }) }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  api: (...args: unknown[]) => apiMock(...args),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  useSearchParams: () => searchParams,
}));

// Every render gets its own query cache (the login form asks whether demo sign-in is on).
function render(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return baseRender(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

// Imported after the mocks above are registered.
const { LoginForm } = await import("@/app/login/login-form");

async function fillAndSubmit(email: string, password: string) {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

describe("LoginForm", () => {
  beforeEach(() => {
    login.mockReset();
    demoLogin.mockReset();
    logout.mockReset();
    replace.mockReset();
    apiMock.mockReset();
    apiMock.mockResolvedValue({ enabled: false, restaurant_name: null, roles: [] });
    auth.me = undefined;
    searchParams = new URLSearchParams();
  });

  it("shows field errors without calling the server", async () => {
    render(<LoginForm />);
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter your email address")).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Email"), "not-an-email");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("Enter a valid email address")).toBeInTheDocument();
    expect(login).not.toHaveBeenCalled();
  });

  it("signs in (trimming the email) and goes to the first page the role allows", async () => {
    login.mockResolvedValue({ user: { is_platform_admin: false }, memberships: [{ permissions: ["kitchen:read"] }] });
    render(<LoginForm />);
    await fillAndSubmit("  kitchen@smartpos.demo ", "secret-1");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/kitchen"));
    expect(login).toHaveBeenCalledWith("kitchen@smartpos.demo", "secret-1", true);
    expect(await screen.findByRole("button", { name: /Signed in/ })).toBeDisabled();
  });

  it("passes 'keep me signed in' to the server", async () => {
    login.mockResolvedValue({ user: { is_platform_admin: false }, memberships: [{ permissions: ["orders:read"] }] });
    render(<LoginForm />);
    await userEvent.click(screen.getByRole("checkbox", { name: "Keep me signed in" }));
    await fillAndSubmit("a@b.co", "secret-1");
    await waitFor(() => expect(login).toHaveBeenCalledWith("a@b.co", "secret-1", false));
  });

  it("sends an administrator without any restaurant to Administration", async () => {
    login.mockResolvedValue({ user: { is_platform_admin: true }, memberships: [] });
    render(<LoginForm />);
    await fillAndSubmit("ops@example.com", "secret-1");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/admin"));
  });

  it("shows and hides the password", async () => {
    render(<LoginForm />);
    const field = screen.getByLabelText("Password");
    expect(field).toHaveAttribute("type", "password");
    await userEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(field).toHaveAttribute("type", "text");
    await userEvent.click(screen.getByRole("button", { name: "Hide password" }));
    expect(field).toHaveAttribute("type", "password");
  });

  it("explains a wrong password, refocuses it, and clears the message when typing", async () => {
    login.mockRejectedValue(new ApiError(401, "invalid_credentials", "Invalid email or password."));
    render(<LoginForm />);
    await fillAndSubmit("a@b.co", "wrong-1");
    expect(await screen.findByRole("alert")).toHaveTextContent("Email or password is incorrect");
    await waitFor(() => expect(screen.getByLabelText("Password")).toHaveFocus());
    await userEvent.type(screen.getByLabelText("Password"), "x");
    expect(screen.queryByText("Email or password is incorrect")).not.toBeInTheDocument();
  });

  it("pauses sign-in with a countdown when rate limited", async () => {
    login.mockRejectedValue(new ApiError(429, "rate_limited", "Too many attempts.", { retry_after: 90 }));
    render(<LoginForm />);
    await fillAndSubmit("a@b.co", "wrong-1");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Too many sign-in attempts");
    expect(alert).toHaveTextContent("1:30");
    expect(screen.getByRole("button", { name: "Sign in" })).toBeDisabled();
    // Typing does not hide an active pause.
    await userEvent.type(screen.getByLabelText("Password"), "x");
    expect(screen.getByText("Too many sign-in attempts")).toBeInTheDocument();
  });

  it("says why the visitor is back on the sign-in page", () => {
    searchParams = new URLSearchParams("reason=session&next=%2Finventory");
    render(<LoginForm />);
    expect(screen.getByRole("status")).toHaveTextContent("Your session ended");
  });

  it("offers to continue or switch account when already signed in", async () => {
    auth.me = {
      user: { full_name: "Mali Srisuk", email: "manager@smartpos.demo", is_platform_admin: false },
      memberships: [{ restaurant_name: "Baan Test", role: "MANAGER", permissions: ["orders:read"] }],
    };
    render(<LoginForm />);
    expect(screen.getByText("Mali Srisuk")).toBeInTheDocument();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use another account" }));
    expect(logout).toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(replace).toHaveBeenCalledWith("/dashboard");
    // The panel stays (with progress) while the app opens, instead of flashing the empty form.
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  });

  it("offers one-click demo roles only when the server enables them", async () => {
    render(<LoginForm />);
    await waitFor(() => expect(apiMock).toHaveBeenCalledWith("/auth/demo", { noRestaurant: true }));
    expect(screen.queryByText("Try the live demo")).not.toBeInTheDocument();

    apiMock.mockResolvedValue({
      enabled: true,
      restaurant_name: "Baan Siam (Demo)",
      roles: [
        { role: "MANAGER", label: "Manager", description: "Dashboard and reports" },
        { role: "CASHIER", label: "Cashier", description: "POS and orders" },
      ],
    });
    demoLogin.mockResolvedValue({ user: { is_platform_admin: false }, memberships: [{ permissions: ["orders:create"] }] });
    render(<LoginForm />);
    await userEvent.click(await screen.findByRole("button", { name: /Cashier/ }));
    expect(demoLogin).toHaveBeenCalledWith("CASHIER");
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/pos"));
    expect(login).not.toHaveBeenCalled();
  });
});

describe("loading and error states", () => {
  it("renders a retry button that refetches", async () => {
    const refetch = vi.fn();
    render(
      <QueryState query={{ isPending: false, isError: true, error: new Error("Network down"), data: undefined, refetch }}>
        {() => <p>data</p>}
      </QueryState>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Network down");
    await userEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(refetch).toHaveBeenCalled();
  });

  it("does not offer a retry for permission errors", () => {
    render(<ErrorState error={new ApiError(403, "forbidden", "Not allowed")} onRetry={() => {}} />);
    expect(screen.getByText("You don't have access to this")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows a loading placeholder while pending", () => {
    render(
      <QueryState query={{ isPending: true, isError: false, error: null, data: undefined, refetch: () => {} }}>
        {() => <p>data</p>}
      </QueryState>,
    );
    expect(screen.getByLabelText("Loading")).toHaveAttribute("aria-busy", "true");
  });
});

describe("dashboard building blocks", () => {
  it("labels deltas with direction and comparison period", () => {
    render(<StatCard label="Today's sales" value="฿1,000.00" delta={-12.5} deltaLabel="vs same time yesterday" />);
    expect(screen.getByText("-12.5%")).toBeInTheDocument();
    expect(screen.getByText("vs same time yesterday")).toBeInTheDocument();
  });

  it("offers a table view for every chart", async () => {
    render(<ChartCard title="Sales" chart={<p>the chart</p>} table={<p>the table</p>} />);
    expect(screen.getByText("the chart")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "table" }));
    expect(screen.getByText("the table")).toBeInTheDocument();
  });
});

describe("POS modifier dialog", () => {
  const product: Product = {
    id: "p1",
    category_id: "c",
    category_name: "Drinks",
    name: "Thai Iced Tea",
    description: null,
    sku: null,
    image_url: null,
    price_minor: 6000,
    is_available: true,
    is_active: true,
    has_recipe: true,
    created_at: "",
    updated_at: "",
    modifier_groups: [
      {
        id: "size",
        name: "Size",
        description: null,
        selection_type: "SINGLE",
        min_select: 1,
        max_select: 1,
        display_order: 0,
        is_active: true,
        options: [
          { id: "regular", group_id: "size", name: "Regular", price_delta_minor: 0, is_default: false, is_active: true, display_order: 0, ingredient_id: null, ingredient_quantity: null },
          { id: "large", group_id: "size", name: "Large", price_delta_minor: 1500, is_default: false, is_active: true, display_order: 1, ingredient_id: null, ingredient_quantity: null },
        ],
      },
    ],
  };

  it("requires the mandatory choice and adds the line with its modifiers", async () => {
    const onAdd = vi.fn();
    render(<ModifierDialog product={product} onClose={() => {}} onAdd={onAdd} />);
    const addButton = screen.getByRole("button", { name: /add/i });
    expect(addButton).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Choose at least 1 for Size.");

    await userEvent.click(screen.getByLabelText(/Large/));
    await userEvent.click(screen.getByRole("button", { name: "Increase quantity" }));
    await userEvent.click(screen.getByRole("button", { name: /add/i }));
    expect(onAdd).toHaveBeenCalledWith(
      expect.objectContaining({
        productId: "p1",
        quantity: 2,
        modifiers: [{ optionId: "large", groupName: "Size", name: "Large", priceDeltaMinor: 1500 }],
      }),
    );
  });
});
