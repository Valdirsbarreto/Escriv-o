"use client";

import { useState, useEffect } from "react";
import { Fingerprint, ShieldCheck, ShieldOff, Loader2 } from "lucide-react";
import { registrarPasskey, temPasskeyRegistrada, removerPasskey, suportaBiometria } from "@/hooks/usePasskey";
import { createClient } from "@/lib/supabase/client";

export function BiometricSetup() {
  const [registrada, setRegistrada] = useState(false);
  const [suporta, setSuporta] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [mensagem, setMensagem] = useState("");
  const [erro, setErro] = useState("");

  useEffect(() => {
    setRegistrada(temPasskeyRegistrada());
    suportaBiometria().then(setSuporta);
  }, []);

  const ativar = async () => {
    setCarregando(true);
    setErro("");
    setMensagem("");
    try {
      const supabase = createClient();
      const { data } = await supabase.auth.getUser();
      if (!data.user) throw new Error("Usuário não autenticado.");

      const nome = data.user.user_metadata?.full_name || data.user.email || "Comissário";
      await registrarPasskey(data.user.id, nome);
      setRegistrada(true);
      setMensagem("Digital registrada com sucesso! Na próxima vez que abrir o app, desbloqueie com a digital.");
    } catch (e: any) {
      if (e.name === "NotAllowedError") {
        setErro("Registro cancelado. Tente novamente.");
      } else {
        setErro(e.message || "Erro ao registrar a digital.");
      }
    } finally {
      setCarregando(false);
    }
  };

  const desativar = () => {
    removerPasskey();
    setRegistrada(false);
    setMensagem("Biometria desativada neste dispositivo.");
  };

  if (!suporta) {
    return (
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4">
        <div className="flex items-center gap-2 text-zinc-500 text-sm">
          <Fingerprint size={16} />
          <span>Biometria não disponível neste dispositivo ou navegador.</span>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Fingerprint size={18} className={registrada ? "text-green-400" : "text-zinc-400"} />
          <div>
            <p className="text-sm font-semibold text-zinc-200">Desbloqueio por Digital</p>
            <p className="text-xs text-zinc-500">
              {registrada ? "Ativo neste dispositivo" : "Desativado"}
            </p>
          </div>
        </div>
        {registrada ? (
          <span className="text-xs bg-green-500/10 text-green-400 border border-green-500/20 px-2 py-0.5 rounded-full">
            Ativo
          </span>
        ) : (
          <span className="text-xs bg-zinc-800 text-zinc-500 px-2 py-0.5 rounded-full">
            Inativo
          </span>
        )}
      </div>

      {mensagem && (
        <p className="text-xs text-green-400 bg-green-500/10 border border-green-500/20 rounded-md px-3 py-2">
          {mensagem}
        </p>
      )}
      {erro && (
        <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-md px-3 py-2">
          {erro}
        </p>
      )}

      <p className="text-xs text-zinc-600">
        {registrada
          ? "O app pedirá sua digital ao ser aberto no celular."
          : "Registre sua digital para desbloquear o app sem precisar fazer login toda vez."}
      </p>

      {registrada ? (
        <button
          onClick={desativar}
          className="flex items-center gap-2 text-sm text-red-400 hover:text-red-300 transition-colors"
        >
          <ShieldOff size={14} />
          Remover digital deste dispositivo
        </button>
      ) : (
        <button
          onClick={ativar}
          disabled={carregando}
          className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-sm rounded-lg px-4 py-2 transition-colors"
        >
          {carregando ? (
            <Loader2 size={14} className="animate-spin" />
          ) : (
            <ShieldCheck size={14} />
          )}
          {carregando ? "Aguardando digital..." : "Registrar minha digital"}
        </button>
      )}
    </div>
  );
}
