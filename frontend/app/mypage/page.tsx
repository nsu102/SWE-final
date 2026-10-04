import type { Metadata } from "next";
import MyPageView from "../components/my-page-view";

export const metadata: Metadata = { title: "MY PAGE | LookFind" };

export default function MyPagePage() {
  return <MyPageView />;
}
