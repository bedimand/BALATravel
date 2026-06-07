"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { api } from "@/lib/api";

export default function SignupPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("A senha precisa ter ao menos 8 caracteres.");
      return;
    }
    setLoading(true);
    try {
      await api.signup({ name, email, password });
      router.push("/history");
    } catch (signupError) {
      setError(signupError instanceof Error ? signupError.message : "Falha ao criar conta.");
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
          <h1>Criar conta</h1>
          <p className="lede">Crie uma conta para salvar e separar suas viagens.</p>
        </div>

        <label>
          <span style={{ display: "block", marginBottom: "0.5rem", fontWeight: 600 }}>Nome</span>
          <input
            type="text"
            autoComplete="name"
            required
            minLength={2}
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ width: "100%" }}
          />
        </label>

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
            autoComplete="new-password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%" }}
          />
          <span style={{ display: "block", marginTop: "0.35rem", fontSize: "0.8rem", color: "var(--muted)" }}>
            Minimo de 8 caracteres.
          </span>
        </label>

        {error && <p className="error-text">{error}</p>}

        <button type="submit" className="button-primary" disabled={loading}>
          {loading ? "Criando..." : "Criar conta"}
        </button>

        <p style={{ textAlign: "center", fontSize: "0.9rem", color: "var(--muted)" }}>
          Ja tem conta? <Link href="/login">Entrar</Link>
        </p>
      </form>
    </main>
  );
}
