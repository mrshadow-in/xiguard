import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Xiguard",
  description: "MikroTik CHR DDoS monitoring panel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-bg text-ink antialiased">{children}</body>
    </html>
  );
}
