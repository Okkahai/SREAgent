"use client";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

/** Re-renders the server components every few seconds so the page stays live. */
export default function Refresh({ seconds = 10 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const t = setInterval(() => router.refresh(), seconds * 1000);
    return () => clearInterval(t);
  }, [router, seconds]);
  return null;
}
