import type { Metadata, Viewport } from "next";
import LookFindProvider from "./contexts/lookfind-context";
import "./globals.css";
import "./test-search.css";
import "./collections.css";
import "./account.css";
import "./responsive.css";

export const metadata: Metadata = {
  title: "LookFind | 이미지 기반 유사 의류 검색",
  description: "사진으로 비슷한 상의 상품을 찾아보세요.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <main className="lookfind"><LookFindProvider>{children}</LookFindProvider></main>
      </body>
    </html>
  );
}
