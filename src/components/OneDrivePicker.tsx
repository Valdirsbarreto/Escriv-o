"use client";

/**
 * OneDrivePicker — abre o seletor de arquivos do OneDrive via Microsoft Graph.
 * Usa o OneDrive File Picker SDK v8 (popup nativo da Microsoft).
 * Ao selecionar um arquivo, obtém a URL de download e chama onFileSelected.
 */

import { useState } from "react";
import { CloudUpload, Loader2 } from "lucide-react";

const ONEDRIVE_CLIENT_ID = "5434c90f-ee0d-4f23-8645-6b4f7ca172d4";
const ONEDRIVE_TENANT_ID = "a960e527-6c8c-440a-a15d-14d7e906b709";

interface OneDriveFile {
  nome: string;
  downloadUrl: string;
  tamanho: number;
}

interface Props {
  onFileSelected: (file: OneDriveFile) => void;
  disabled?: boolean;
}

// Obtém token de acesso via popup MSAL implícito com redirect para /auth/onedrive
async function obterToken(): Promise<string> {
  return new Promise((resolve, reject) => {
    const redirectUri = `${window.location.origin}/auth/onedrive`;
    const scope = encodeURIComponent("https://graph.microsoft.com/Files.Read User.Read");
    const url =
      `https://login.microsoftonline.com/${ONEDRIVE_TENANT_ID}/oauth2/v2.0/authorize` +
      `?client_id=${ONEDRIVE_CLIENT_ID}` +
      `&response_type=token` +
      `&redirect_uri=${encodeURIComponent(redirectUri)}` +
      `&scope=${scope}` +
      `&response_mode=fragment` +
      `&prompt=select_account`;

    const popup = window.open(url, "mslogin", "width=520,height=640,left=200,top=80");
    if (!popup) {
      reject(new Error("Popup bloqueado. Permita popups para este site."));
      return;
    }

    // Ouve o postMessage enviado pela página /auth/onedrive
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "onedrive_token") return;
      window.removeEventListener("message", onMessage);
      clearTimeout(timeout);
      if (event.data.token) {
        resolve(event.data.token);
      } else {
        reject(new Error(`Autenticação falhou: ${event.data.error || "erro desconhecido"}`));
      }
    };
    window.addEventListener("message", onMessage);

    // Detecta se o usuário fechou o popup manualmente
    const closedTimer = setInterval(() => {
      if (popup.closed) {
        clearInterval(closedTimer);
        window.removeEventListener("message", onMessage);
        reject(new Error("Login cancelado."));
      }
    }, 600);

    // Timeout de 3 minutos
    const timeout = setTimeout(() => {
      clearInterval(closedTimer);
      window.removeEventListener("message", onMessage);
      if (!popup.closed) popup.close();
      reject(new Error("Tempo de login esgotado."));
    }, 180000);
  });
}

// Abre o seletor OneDrive via Graph API + iframe picker
async function abrirSeletorOneDrive(token: string): Promise<OneDriveFile> {
  return new Promise((resolve, reject) => {
    // Usa o OneDrive File Picker API v8
    const pickerUrl =
      `https://onedrive.live.com/picker` +
      `?typesAndSources=files` +
      `&filesFilter=.pdf,.png,.jpg,.jpeg` +
      `&select=true` +
      `&sdk=8.0`;

    const popup = window.open(pickerUrl, "onedrivepicker", "width=800,height=600,left=150,top=80");
    if (!popup) {
      reject(new Error("Popup bloqueado. Permita popups para este site."));
      return;
    }

    const onMessage = async (event: MessageEvent) => {
      if (!event.data || typeof event.data !== "object") return;
      // Picker v8 envia comando "authenticate" pedindo token
      if (event.data.type === "initialize" || event.data.command === "authenticate") {
        event.source && (event.source as Window).postMessage(
          { type: "result", result: { token } },
          event.origin,
        );
        return;
      }
      // Picker v8: resultado da seleção
      if (event.data.command === "close") {
        window.removeEventListener("message", onMessage);
        if (!popup.closed) popup.close();
        reject(new Error("Seleção cancelada."));
        return;
      }
      if (event.data.command === "pick") {
        window.removeEventListener("message", onMessage);
        if (!popup.closed) popup.close();
        const item = event.data.items?.[0];
        if (!item) { reject(new Error("Nenhum arquivo selecionado.")); return; }
        // Obtém URL de download via Graph API
        try {
          const resp = await fetch(
            `https://graph.microsoft.com/v1.0/me/drive/items/${item.id}`,
            { headers: { Authorization: `Bearer ${token}` } },
          );
          const data = await resp.json();
          const downloadUrl = data["@microsoft.graph.downloadUrl"] || data.downloadUrl;
          if (!downloadUrl) { reject(new Error("URL de download não disponível.")); return; }
          resolve({
            nome: data.name || item.name || "documento.pdf",
            downloadUrl,
            tamanho: data.size || 0,
          });
        } catch (e) {
          reject(new Error("Erro ao obter URL de download do arquivo."));
        }
      }
    };

    window.addEventListener("message", onMessage);

    // Timeout de 5 minutos
    setTimeout(() => {
      window.removeEventListener("message", onMessage);
      if (!popup.closed) popup.close();
      reject(new Error("Tempo de seleção esgotado."));
    }, 300000);
  });
}

export function OneDrivePicker({ onFileSelected, disabled }: Props) {
  const [status, setStatus] = useState<"idle" | "auth" | "picking" | "erro">("idle");
  const [erro, setErro] = useState<string | null>(null);

  const handleClick = async () => {
    setErro(null);
    try {
      setStatus("auth");
      const token = await obterToken();
      setStatus("picking");
      const file = await abrirSeletorOneDrive(token);
      setStatus("idle");
      onFileSelected(file);
    } catch (e: any) {
      setStatus("erro");
      setErro(e?.message || "Erro desconhecido");
    }
  };

  return (
    <div className="inline-flex flex-col items-start gap-1">
      <button
        onClick={handleClick}
        disabled={disabled || status === "auth" || status === "picking"}
        className="flex items-center gap-2 text-sm bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 px-3 py-2 rounded-lg transition-colors disabled:opacity-50"
        title="Selecionar arquivo do OneDrive"
      >
        {(status === "auth" || status === "picking") ? (
          <Loader2 size={15} className="animate-spin" />
        ) : (
          <CloudUpload size={15} />
        )}
        {status === "auth" ? "Autenticando..." : status === "picking" ? "Aguardando seleção..." : "OneDrive"}
      </button>
      {erro && (
        <p className="text-xs text-red-400 max-w-xs">{erro}</p>
      )}
    </div>
  );
}
