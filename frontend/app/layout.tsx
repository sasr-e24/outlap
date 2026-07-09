import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "OUTLAP — Race HQ",
  description: "Live predictive pit wall for F1: tyre deg, pit windows, race odds.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
