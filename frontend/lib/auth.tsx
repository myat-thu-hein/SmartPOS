"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, ApiError, getStoredRestaurantId, onUnauthorized, setRestaurantId } from "@/lib/api";
import type { DemoRoleName, LoginResponse, Me, Membership } from "@/types/api";

interface AuthValue {
  me: Me | undefined;
  isLoading: boolean;
  error: unknown;
  membership: Membership | undefined;
  restaurantId: string | null;
  permissions: Set<string>;
  can: (permission: string) => boolean;
  selectRestaurant: (id: string) => void;
  /** remember=false: the browser forgets the session when it closes. */
  login: (email: string, password: string, remember?: boolean) => Promise<LoginResponse>;
  /** One-click sign-in to the demo restaurant (only when the server enables it). */
  demoLogin: (role: DemoRoleName) => Promise<LoginResponse>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

function pickRestaurant(memberships: Membership[], preferred: string | null): string | null {
  if (preferred && memberships.some((m) => m.restaurant_id === preferred)) return preferred;
  return memberships[0]?.restaurant_id ?? null;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const [restaurantId, setRestaurant] = useState<string | null>(null);

  const meQuery = useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => api<Me>("/auth/me", { noRestaurant: true }),
    retry: (count, error) => !(error instanceof ApiError && error.status === 401) && count < 2,
    staleTime: 60_000,
  });

  // Choose the active restaurant once memberships are known.
  useEffect(() => {
    if (!meQuery.data) return;
    const chosen = pickRestaurant(meQuery.data.memberships, restaurantId ?? getStoredRestaurantId());
    setRestaurantId(chosen);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync with the API client's tenant header
    setRestaurant(chosen);
  }, [meQuery.data, restaurantId]);

  useEffect(
    () =>
      onUnauthorized(() => {
        // On the sign-in page a 401 from /auth/me just means "not signed in yet".
        if (window.location.pathname.startsWith("/login")) return;
        queryClient.clear();
        // reason=session lets the sign-in page explain why the user is back there.
        router.replace(`/login?reason=session&next=${encodeURIComponent(window.location.pathname)}`);
      }),
    [queryClient, router],
  );

  const selectRestaurant = useCallback(
    (id: string) => {
      setRestaurantId(id);
      setRestaurant(id);
      // Everything cached belongs to the previous restaurant.
      queryClient.removeQueries({ predicate: (q) => q.queryKey[0] !== "auth" });
    },
    [queryClient],
  );

  const startSession = useCallback(
    (result: LoginResponse) => {
      queryClient.clear();
      queryClient.setQueryData(["auth", "me"], { user: result.user, memberships: result.memberships });
      const chosen = pickRestaurant(result.memberships, getStoredRestaurantId());
      setRestaurantId(chosen);
      setRestaurant(chosen);
      return result;
    },
    [queryClient],
  );

  const login = useCallback(
    async (email: string, password: string, remember = true) =>
      startSession(
        await api<LoginResponse>("/auth/login", {
          method: "POST",
          body: { email, password, remember },
          noRestaurant: true,
        }),
      ),
    [startSession],
  );

  const demoLogin = useCallback(
    async (role: DemoRoleName) =>
      startSession(await api<LoginResponse>("/auth/demo-login", { method: "POST", body: { role }, noRestaurant: true })),
    [startSession],
  );

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST", noRestaurant: true });
    } finally {
      queryClient.clear();
      setRestaurantId(null);
      setRestaurant(null);
      router.replace("/login?reason=signedout");
    }
  }, [queryClient, router]);

  const membership = meQuery.data?.memberships.find((m) => m.restaurant_id === restaurantId);
  const isPlatformAdmin = !!meQuery.data?.user.is_platform_admin;
  // A platform admin with no restaurant yet can still reach Administration to create one.
  const permissions = useMemo(
    () => new Set(membership?.permissions ?? (isPlatformAdmin ? ["platform:admin"] : [])),
    [membership, isPlatformAdmin],
  );

  const value: AuthValue = {
    me: meQuery.data,
    isLoading: meQuery.isPending,
    error: meQuery.error,
    membership,
    restaurantId,
    permissions,
    can: (permission) => permissions.has(permission),
    selectRestaurant,
    login,
    demoLogin,
    logout,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
