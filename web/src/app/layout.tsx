import type { ReactNode } from "react";

export const metadata = { title: "OpsPilot", description: "AI-powered SRE incident investigation" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0, background: "#0b1020", color: "#e6e9f2" }}>
        {children}
      </body>
    </html>
  );
}
