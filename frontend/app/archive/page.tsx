import type { Metadata } from "next";
import ArchiveView from "../components/archive-view";

export const metadata: Metadata = { title: "ARCHIVE | LookFind" };

export default function ArchivePage() {
  return <ArchiveView />;
}
