"use client";

const STORAGE_KEY = "escrivao_passkey_id";

function b64url(bytes: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(bytes)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=/g, "");
}

function b64urlDecode(s: string): ArrayBuffer {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(b64);
  const buf = new ArrayBuffer(binary.length);
  const view = new Uint8Array(buf);
  for (let i = 0; i < binary.length; i++) {
    view[i] = binary.charCodeAt(i);
  }
  return buf;
}

/** Verifica se o browser suporta WebAuthn com autenticador de plataforma (biometria). */
export async function suportaBiometria(): Promise<boolean> {
  if (typeof window === "undefined") return false;
  if (!window.PublicKeyCredential) return false;
  try {
    return await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable();
  } catch {
    return false;
  }
}

/** Verifica se há passkey registrada neste dispositivo. */
export function temPasskeyRegistrada(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem(STORAGE_KEY);
}

/**
 * Registra a biometria do dispositivo para este usuário.
 * Salva o credential ID no localStorage.
 */
export async function registrarPasskey(userId: string, userName: string): Promise<void> {
  const challenge = crypto.getRandomValues(new Uint8Array(32));

  const cred = (await navigator.credentials.create({
    publicKey: {
      challenge,
      rp: {
        name: "Escrivão AI",
        id: window.location.hostname,
      },
      user: {
        id: new TextEncoder().encode(userId),
        name: userName,
        displayName: userName,
      },
      pubKeyCredParams: [
        { alg: -7, type: "public-key" },   // ES256
        { alg: -257, type: "public-key" }, // RS256
      ],
      authenticatorSelection: {
        authenticatorAttachment: "platform",
        userVerification: "required",
        residentKey: "preferred",
      },
      timeout: 60000,
    },
  })) as PublicKeyCredential | null;

  if (!cred) throw new Error("Registro cancelado pelo usuário.");

  localStorage.setItem(STORAGE_KEY, b64url(cred.rawId));
}

/**
 * Solicita autenticação biométrica.
 * Retorna true se o usuário autenticou com sucesso.
 */
export async function autenticarPasskey(): Promise<boolean> {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (!stored) return false;

  const credentialId = b64urlDecode(stored);
  const challenge = crypto.getRandomValues(new Uint8Array(32));

  try {
    const assertion = await navigator.credentials.get({
      publicKey: {
        challenge,
        rpId: window.location.hostname,
        allowCredentials: [{ id: credentialId, type: "public-key" }],
        userVerification: "required",
        timeout: 60000,
      },
    });
    return !!assertion;
  } catch {
    return false;
  }
}

/** Remove a passkey registrada (desativa biometria neste dispositivo). */
export function removerPasskey(): void {
  localStorage.removeItem(STORAGE_KEY);
}
