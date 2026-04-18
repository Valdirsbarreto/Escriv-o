"use client";

import { useState, useEffect, useCallback } from "react";
import { Fingerprint, ShieldCheck, AlertCircle, Loader2 } from "lucide-react";
import { autenticarPasskey, temPasskeyRegistrada } from "@/hooks/usePasskey";
import { createClient } from "@/lib/supabase/client";

type Estado = "verificando" | "bloqueado" | "autenticando" | "desbloqueado";

export function BiometricLock() {
  const [estado, setEstado] = useState<Estado>("verificando");
  const [erro, setErro] = useState("");
  const [tentativas, setTentativas] = useState(0);

  useEffect(() => {
    async function checar() {
      // Só bloqueia se: passkey registrada + usuário logado
      if (!temPasskeyRegistrada()) {
        setEstado("desbloqueado");
        return;
      }

      const supabase = createClient();
      const { data } = await supabase.auth.getSession();
      if (data.session) {
        setEstado("bloqueado");
      } else {
        // Sessão expirada — deixa o middleware redirecionar para login
        setEstado("desbloqueado");
      }
    }
    checar();
  }, []);

  const desbloquear = useCallback(async () => {
    if (estado !== "bloqueado") return;
    setEstado("autenticando");
    setErro("");

    try {
      const ok = await autenticarPasskey();
      if (ok) {
        setEstado("desbloqueado");
      } else {
        const t = tentativas + 1;
        setTentativas(t);
        setErro(t >= 3 ? "Muitas tentativas. Tente novamente em instantes." : "Autenticação cancelada.");
        setEstado("bloqueado");
      }
    } catch (e: any) {
      setErro("Erro na biometria. Toque novamente.");
      setEstado("bloqueado");
    }
  }, [estado, tentativas]);

  // Auto-dispara ao montar se já estiver bloqueado (UX mais fluida)
  useEffect(() => {
    if (estado === "bloqueado") {
      // Pequeno delay para o OS abrir o prompt de forma mais natural
      const t = setTimeout(() => desbloquear(), 300);
      return () => clearTimeout(t);
    }
  }, [estado]); // eslint-disable-line

  if (estado === "verificando" || estado === "desbloqueado") return null;

  return (
    <div className="fixed inset-0 z-[9999] bg-zinc-950 flex flex-col items-center justify-center gap-10 select-none">
      {/* Logo */}
      <div className="flex flex-col items-center gap-3">
        <div className="w-16 h-16 rounded-2xl bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
          <ShieldCheck size={32} className="text-blue-400" />
        </div>
        <div className="text-center">
          <h1 className="text-2xl font-bold text-zinc-100 tracking-tight">Escrivão AI</h1>
          <p className="text-sm text-zinc-500 mt-1">Sistema bloqueado</p>
        </div>
      </div>

      {/* Botão de digital */}
      <div className="flex flex-col items-center gap-4">
        <button
          onClick={desbloquear}
          disabled={estado === "autenticando"}
          className={`
            w-28 h-28 rounded-full border-2 flex items-center justify-center
            transition-all duration-200 active:scale-95
            ${estado === "autenticando"
              ? "border-blue-500/60 bg-blue-500/15 cursor-wait"
              : erro
              ? "border-red-500/50 bg-red-500/10 hover:bg-red-500/15"
              : "border-blue-500/40 bg-blue-500/10 hover:bg-blue-500/20 hover:border-blue-500/60"
            }
          `}
          aria-label="Desbloquear com biometria"
        >
          {estado === "autenticando" ? (
            <Loader2 size={48} className="text-blue-400 animate-spin" />
          ) : erro ? (
            <Fingerprint size={48} className="text-red-400" />
          ) : (
            <Fingerprint size={48} className="text-blue-400" />
          )}
        </button>

        {erro ? (
          <div className="flex items-center gap-2 text-sm text-red-400">
            <AlertCircle size={14} />
            <span>{erro}</span>
          </div>
        ) : (
          <p className="text-sm text-zinc-500">
            {estado === "autenticando" ? "Verificando..." : "Toque para desbloquear"}
          </p>
        )}
      </div>
    </div>
  );
}
