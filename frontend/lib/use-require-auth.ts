"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { getToken } from "@/lib/api";

/**
 * Client-side guard for protected pages. Redirects to /login when there is no
 * access token. Returns `true` once a token is confirmed so callers can defer
 * data loading until the user is known to be authenticated.
 */
export function useRequireAuth(): boolean {
  const router = useRouter();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    if (getToken()) {
      setAuthed(true);
    } else {
      router.replace("/login");
    }
  }, [router]);

  return authed;
}
