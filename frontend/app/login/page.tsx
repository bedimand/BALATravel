"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await api.login({ email, password });
      router.push("/history");
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Falha ao entrar.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="centered-page">
      <form
        className="trip-wizard"
        onSubmit={handleSubmit}
        style={{ width: "100%", maxWidth: "420px" }}
      >
        <div className="trip-wizard__header">
          <h1>Entrar</h1>
          <p className="lede">Acesse sua conta para ver e planejar suas viagens.</p>
        </div>

        <label>
          <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Email</span>
          <input
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%" }}
          />
        </label>

        <label>
          <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Senha</span>
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%" }}
          />
        </label>

        {error && <p className="error-text">{error}</p>}

        <button type="submit" className="button-primary" disabled={loading}>
          {loading ? "Entrando..." : "Entrar"}
        </button>

        <p style={{ textAlign: "center", fontSize: "0.9rem", color: "var(--muted)" }}>
          Não tem conta? <Link href="/signup">Criar conta</Link>
        </p>
      </form>
    </main>
  );
}
