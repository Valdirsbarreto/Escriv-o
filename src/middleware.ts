import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const ALLOWED_EMAIL = process.env.NEXT_PUBLIC_ALLOWED_EMAIL || "";

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          );
          supabaseResponse = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          );
        },
      },
    }
  );

  const { data: { user } } = await supabase.auth.getUser();
  const pathname = request.nextUrl.pathname;

  // Rotas públicas — não precisam de auth
  const isPublic =
    pathname.startsWith("/login") ||
    pathname.startsWith("/auth/callback");

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    return NextResponse.redirect(url);
  }

  // Usuário autenticado mas e-mail não permitido
  const allowedEmail = ALLOWED_EMAIL.trim().toLowerCase();
  if (user && allowedEmail && user.email?.toLowerCase() !== allowedEmail) {
    await supabase.auth.signOut();
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("erro", "acesso_negado");
    return NextResponse.redirect(url);
  }

  // Usuário já autenticado tentando acessar /login
  if (user && pathname.startsWith("/login")) {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    return NextResponse.redirect(url);
  }

  return supabaseResponse;
}

export const config = {
  // Rodar apenas nas rotas protegidas e de autenticação — evita Edge Function em assets e rotas públicas
  matcher: [
    "/",
    "/inqueritos/:path*",
    "/intimacoes/:path*",
    "/painel/:path*",
    "/login",
    "/auth/callback",
  ],
};
