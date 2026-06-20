import type { Metadata } from "next";
import "./globals.css";
import "./ui-overrides.css";

export const metadata: Metadata = {
  title: "LiveLine Console",
  description: "Stage 0 project skeleton",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
