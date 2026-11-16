"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { api, type RequestOptions } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type Query = RequestOptions["query"];

/** GET a restaurant-scoped resource. Cache keys include the active restaurant. */
export function useApi<T>(
  key: readonly unknown[],
  path: string | null,
  query?: Query,
  options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">,
) {
  const { restaurantId } = useAuth();
  return useQuery<T>({
    queryKey: [restaurantId, ...key, query ?? {}],
    queryFn: ({ signal }) => api<T>(path as string, { query, signal }),
    ...options,
    enabled: !!restaurantId && !!path && (options?.enabled ?? true),
  });
}

/** GET a platform-wide (administrator) resource; not scoped to the active restaurant. */
export function usePlatformApi<T>(
  key: readonly unknown[],
  path: string | null,
  query?: Query,
  options?: Omit<UseQueryOptions<T>, "queryKey" | "queryFn">,
) {
  const { me } = useAuth();
  return useQuery<T>({
    queryKey: ["platform", ...key, query ?? {}],
    queryFn: ({ signal }) => api<T>(path as string, { query, signal, noRestaurant: true }),
    ...options,
    enabled: !!me?.user.is_platform_admin && !!path && (options?.enabled ?? true),
  });
}

/**
 * Mutation helper: runs `fn`, shows a success toast, and invalidates queries
 * whose first key segment (after the restaurant id) is listed in `invalidate`.
 */
export function useApiMutation<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  {
    invalidate = [],
    success,
    onSuccess,
    silent = false,
  }: {
    invalidate?: string[];
    success?: string | ((result: TResult) => string);
    onSuccess?: (result: TResult, vars: TVars) => void;
    silent?: boolean;
  } = {},
) {
  const queryClient = useQueryClient();
  return useMutation<TResult, Error, TVars>({
    mutationFn: fn,
    meta: { silent },
    onSuccess: async (result, vars) => {
      if (invalidate.length) {
        await queryClient.invalidateQueries({
          predicate: (q) => invalidate.includes(String(q.queryKey[1])),
        });
      }
      if (success) toast.success(typeof success === "function" ? success(result) : success);
      onSuccess?.(result, vars);
    },
  });
}

export { api };
