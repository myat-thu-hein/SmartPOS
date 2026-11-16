import type { Metadata } from "next";
import { Suspense } from "react";

import { LoadingRows } from "@/components/shared/query-state";

import { ReceiptScreen } from "./receipt-screen";

export const metadata: Metadata = { title: "Receipt" };

// The screen reads the id with useParams(), so it renders on the client inside Suspense.
export default function Page() {
  return (
    <Suspense fallback={<LoadingRows rows={6} />}>
      <ReceiptScreen />
    </Suspense>
  );
}
