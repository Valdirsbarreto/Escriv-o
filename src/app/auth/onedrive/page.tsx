"use client";

/**
 * Callback OAuth Microsoft — PKCE flow.
 * Recebe o código de autorização, troca pelo access_token usando o code_verifier
 * salvo no sessionStorage, envia o token ao parent via postMessage e fecha.
 */

import { useEffect, useState } from "react";

const ONEDRIVE_CLIENT_ID = "5434c90f-ee0d-4f23-8645-6b4f7ca172d4";
const ONEDRIVE_TENANT_ID = "a960e527-6c8c-440a-a15d-14d7e906b709";

export default function OneDriveAuthCallback() {
  const [status, setStatus] = useState("Trocando código por token...");

  useEffect(() => {
    const run = async () => {
      const params = new URLSearchParams(window.location.search);
      const code = params.get("code");
      const error = params.get("error");
      const errorDesc = params.get("error_description");

      if (error) {
        setStatus(`Erro: ${error}`);
        window.opener?.postMessage(
          { type: "onedrive_token", error: errorDesc || error },
          window.location.origin,
        );
        setTimeout(() => window.close(), 2000);
        return;
      }

      if (!code) {
        setStatus("Código de autorização não encontrado.");
        window.opener?.postMessage(
          { type: "onedrive_token", error: "codigo_ausente" },
          window.location.origin,
        );
        setTimeout(() => window.close(), 2000);
        return;
      }

      const verifier = sessionStorage.getItem("pkce_verifier");
      if (!verifier) {
        setStatus("Sessão expirada. Feche e tente novamente.");
        window.opener?.postMessage(
          { type: "onedrive_token", error: "verifier_ausente" },
          window.location.origin,
        );
        setTimeout(() => window.close(), 2000);
        return;
      }

      // Trocar code pelo access_token
      try {
        const redirectUri = `${window.location.origin}/auth/onedrive`;
        const body = new URLSearchParams({
          client_id: ONEDRIVE_CLIENT_ID,
          grant_type: "authorization_code",
          code,
          redirect_uri: redirectUri,
          code_verifier: verifier,
          scope: "https://graph.microsoft.com/Files.Read User.Read offline_access",
        });

        const resp = await fetch(
          `https://login.microsoftonline.com/${ONEDRIVE_TENANT_ID}/oauth2/v2.0/token`,
          {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: body.toString(),
          },
        );

        const data = await resp.json();
        sessionStorage.removeItem("pkce_verifier");
        sessionStorage.removeItem("pkce_state");

        if (data.access_token) {
          setStatus("Autenticado! Abrindo seletor...");
          window.opener?.postMessage(
            { type: "onedrive_token", token: data.access_token },
            window.location.origin,
          );
        } else {
          setStatus(`Falha: ${data.error_description || data.error || "token não recebido"}`);
          window.opener?.postMessage(
            { type: "onedrive_token", error: data.error_description || data.error },
            window.location.origin,
          );
        }
      } catch (e: any) {
        setStatus(`Erro na troca de token: ${e.message}`);
        window.opener?.postMessage(
          { type: "onedrive_token", error: e.message },
          window.location.origin,
        );
      }

      setTimeout(() => window.close(), 500);
    };

    run();
  }, []);

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
      <div className="text-center text-zinc-400 text-sm">
        <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
        {status}
      </div>
    </div>
  );
}
