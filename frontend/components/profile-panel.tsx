"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import { useRequireAuth } from "@/lib/use-require-auth";
import type { UserProfile } from "@/lib/types";

export function ProfilePanel() {
  const authed = useRequireAuth();
  const [user, setUser] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!authed) return;
    api.me().then(setUser).catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar perfil.");
    });
  }, [authed]);

  return (
    <section className="panel profile-panel">
      <h1>Perfil</h1>
      {error ? <p className="error-text">{error}</p> : null}
      {user ? (
        <>
          <p>
            <strong>{user.name}</strong>
          </p>
          <p>{user.email}</p>
          <p>
            Locale: {user.locale} | Moeda: {user.currency}
          </p>
          <button
            type="button"
            className="button-secondary"
            onClick={() => api.logout()}
            style={{ marginTop: "1rem", alignSelf: "flex-start" }}
          >
            Sair
          </button>
        </>
      ) : null}
    </section>
  );
}
