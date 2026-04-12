"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";
import type { UserProfile } from "@/lib/types";

export function ProfilePanel() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch((loadError) => {
      setError(loadError instanceof Error ? loadError.message : "Falha ao carregar perfil.");
    });
  }, []);

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
          <p>Modo local ativo. Todos os dados ficam salvos no banco local desta instalacao.</p>
        </>
      ) : null}
    </section>
  );
}
