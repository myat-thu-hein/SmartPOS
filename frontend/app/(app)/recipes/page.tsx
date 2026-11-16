import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingRows } from "@/components/shared/query-state";

import { RecipesScreen } from "./recipes-screen";

export const metadata: Metadata = { title: "Recipes" };

export default function RecipesPage() {
  return (
    <Suspense fallback={<LoadingRows rows={8} />}>
      <RecipesScreen />
    </Suspense>
  );
}
