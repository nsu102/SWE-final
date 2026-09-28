import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Find the top — 상의 유사 상품 검색",
  description: "전신 사진에서 상의를 분리해 비슷한 상품을 찾습니다.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
