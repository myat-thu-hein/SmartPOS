import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingRows } from "@/components/shared/query-state";

import { PosScreen } from "./pos-screen";

export const metadata: Metadata = { title: "POS" };

export default function PosPage() {
  return (
    <Suspense fallback={<LoadingRows rows={8} />}>
      <PosScreen />
    </Suspense>
  );
}
