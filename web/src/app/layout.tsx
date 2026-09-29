import type { ReactNode } from "react";
import Link from "next/link";
import "./globals.css";

export const metadata = { title: "OpsPilot", description: "AI-powered SRE incident investigation" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <nav>
          <strong>OpsPilot</strong>
          <Link href="/">Overview</Link>
          <Link href="/incidents">Incidents</Link>
          <Link href="/services">Services</Link>
          <Link href="/deployments">Deployments</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
