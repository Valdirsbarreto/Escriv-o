"use client";

import { useEffect, useState, useCallback } from "react";
import { X, CheckCheck, Copy, Check, AlertTriangle, Info, AlertCircle, Trash2 } from "lucide-react";
import { useAppStore } from "@/store/app";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { getAlertas, getAlertasContagem, marcarAlertaLido, marcarTodosAlertasLidos, deletarTodosAlertas } from "@/lib/api";

interface Alerta {
  id: string;
  tipo: string;
  nivel: string;
  titulo: string;
  mensagem: string;
  identificador: string | null;
  lido: boolean;
  created_at: string;
}

function tempoRelativo(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h}h`;
  return `há ${Math.floor(h / 24)}d`;
}

function NivelIcon({ nivel }: { nivel: string }) {
  if (nivel === "critico") return <AlertCircle size={16} className="text-red-400 shrink-0 mt-0.5" />;
  if (nivel === "alerta") return <AlertTriangle size={16} className="text-yellow-400 shrink-0 mt-0.5" />;
  return <Info size={16} className="text-green-400 shrink-0 mt-0.5" />;
}

function AlertaCard({
  alerta,
  onMarcarLido,
}: {
  alerta: Alerta;
  onMarcarLido: (id: string) => void;
}) {
  const [copiado, setCopiado] = useState(false);

  const copiarParaClaude = () => {
    const texto = [
      "Escrivão reportou um problema:",
      "",
      alerta.titulo,
      "",
      alerta.mensagem,
      ...(alerta.identificador ? [`\nRef: ${alerta.identificador} | ${alerta.created_at}`] : []),
    ].join("\n");

    navigator.clipboard.writeText(texto).then(() => {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    });
  };

  const borderColor =
    alerta.nivel === "critico"
      ? "border-red-500/30 bg-red-500/5"
      : alerta.nivel === "alerta"
      ? "border-yellow-500/30 bg-yellow-500/5"
      : "border-green-500/30 bg-green-500/5";

  return (
    <div className={`rounded-lg border p-3 space-y-2 ${borderColor}`}>
      <div className="flex items-start gap-2">
        <NivelIcon nivel={alerta.nivel} />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-zinc-100 leading-snug">{alerta.titulo}</p>
          <p className="text-xs text-zinc-400 mt-0.5">{tempoRelativo(alerta.created_at)}</p>
        </div>
        <button
          onClick={() => onMarcarLido(alerta.id)}
          title="Marcar como lido"
          className="text-zinc-500 hover:text-zinc-300 shrink-0 p-0.5"
        >
          <X size={14} />
        </button>
      </div>

      <p className="text-xs text-zinc-300 whitespace-pre-wrap leading-relaxed pl-6">
        {alerta.mensagem}
      </p>

      <div className="pl-6">
        <button
          onClick={copiarParaClaude}
          className="flex items-center gap-1.5 text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          {copiado ? <Check size={12} /> : <Copy size={12} />}
          {copiado ? "Copiado!" : "Copiar para o Claude"}
        </button>
      </div>
    </div>
  );
}

export function AlertasDrawer() {
  const { isAlertasOpen, setAlertasOpen, alertasNaoLidos, setAlertasNaoLidos } = useAppStore();
  const [alertas, setAlertas] = useState<Alerta[]>([]);
  const [carregando, setCarregando] = useState(false);

  const atualizarContagem = useCallback(async () => {
    try {
      const { nao_lidos } = await getAlertasContagem();
      setAlertasNaoLidos(nao_lidos);
    } catch {
      // silencioso — badge apenas não atualiza
    }
  }, [setAlertasNaoLidos]);

  // Poll da contagem a cada 60s
  useEffect(() => {
    atualizarContagem();
    const interval = setInterval(atualizarContagem, 60000);
    return () => clearInterval(interval);
  }, [atualizarContagem]);

  // Carrega lista ao abrir
  useEffect(() => {
    if (!isAlertasOpen) return;
    setCarregando(true);
    getAlertas()
      .then((data) => setAlertas(data))
      .catch(() => setAlertas([]))
      .finally(() => setCarregando(false));
  }, [isAlertasOpen]);

  const handleMarcarLido = async (id: string) => {
    try {
      await marcarAlertaLido(id);
      setAlertas((prev) => prev.filter((a) => a.id !== id));
      setAlertasNaoLidos(Math.max(0, alertasNaoLidos - 1));
    } catch {
      // silencioso
    }
  };

  const handleMarcarTodosLidos = async () => {
    try {
      await marcarTodosAlertasLidos();
      setAlertas([]);
      setAlertasNaoLidos(0);
    } catch {
      // silencioso
    }
  };

  const handleLimparTodos = async () => {
    try {
      await deletarTodosAlertas();
      setAlertas([]);
      setAlertasNaoLidos(0);
    } catch {
      // silencioso
    }
  };

  return (
    <Sheet open={isAlertasOpen} onOpenChange={setAlertasOpen}>
      <SheetContent
        side="right"
        className="w-full sm:max-w-md bg-zinc-900 border-zinc-800 flex flex-col p-0"
        showCloseButton={false}
      >
        <SheetHeader className="flex flex-row items-center justify-between p-4 border-b border-zinc-800 shrink-0">
          <SheetTitle className="text-zinc-100 text-base font-semibold">
            Alertas do Sistema
          </SheetTitle>
          <div className="flex items-center gap-2">
            {alertas.length > 0 && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleMarcarTodosLidos}
                  className="text-xs text-zinc-400 hover:text-zinc-200 gap-1.5 h-7 px-2"
                >
                  <CheckCheck size={13} />
                  Marcar lidos
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleLimparTodos}
                  className="text-xs text-red-400/70 hover:text-red-400 gap-1.5 h-7 px-2"
                  title="Apagar todos os alertas permanentemente"
                >
                  <Trash2 size={13} />
                  Limpar
                </Button>
              </>
            )}
            <button
              onClick={() => setAlertasOpen(false)}
              className="text-zinc-500 hover:text-zinc-300 p-1"
            >
              <X size={18} />
            </button>
          </div>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {carregando && (
            <p className="text-sm text-zinc-500 text-center py-8">Carregando alertas...</p>
          )}

          {!carregando && alertas.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center space-y-2">
              <div className="w-12 h-12 rounded-full bg-green-500/10 border border-green-500/20 flex items-center justify-center">
                <Check size={22} className="text-green-400" />
              </div>
              <p className="text-sm font-medium text-zinc-300">Nenhum alerta pendente</p>
              <p className="text-xs text-zinc-500">Sistema operando normalmente ✅</p>
            </div>
          )}

          {!carregando &&
            alertas.map((alerta) => (
              <AlertaCard
                key={alerta.id}
                alerta={alerta}
                onMarcarLido={handleMarcarLido}
              />
            ))}
        </div>

        <div className="p-4 border-t border-zinc-800 shrink-0">
          <p className="text-xs text-zinc-600 text-center">
            Para ajuda remota: cole o alerta copiado em{" "}
            <span className="text-blue-400">claude.ai</span>
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}
