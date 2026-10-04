import { Suspense } from "react";
import type { Metadata } from "next";
import ResultsView from "../components/results-view";

export const metadata: Metadata = { title: "RESULTS | LookFind" };

// ResultsView reads ?history=<id>, so it renders on the client inside a Suspense boundary.
export default function ResultsPage() {
  return <Suspense fallback={<p className="api-status page-status">결과를 불러오고 있습니다…</p>}><ResultsView /></Suspense>;
}
