"use client";

/**
 * Página de callback do OAuth Microsoft (OneDrive).
 * Lê o access_token do hash da URL e o envia ao parent via postMessage, depois fecha o popup.
 */

import { useEffect } from "react";

export default function OneDriveAuthCallback() {
  useEffect(() => {
    const hash = window.location.hash.replace("#", "");
    const params = new URLSearchParams(hash);
    const token = params.get("access_token");
    const error = params.get("error");

    if (token) {
      window.opener?.postMessage({ type: "onedrive_token", token }, window.location.origin);
    } else {
      window.opener?.postMessage({ type: "onedrive_token", error: error || "token_ausente" }, window.location.origin);
    }

    // Fecha o popup após enviar a mensagem
    setTimeout(() => window.close(), 300);
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
      <div className="text-center text-zinc-400 text-sm">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        Autenticando com Microsoft...
      </div>
    </div>
  );
}
