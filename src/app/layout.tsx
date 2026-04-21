import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/Sidebar";
import { CopilotoDrawer } from "@/components/CopilotoDrawer";
import { AlertasDrawer } from "@/components/AlertasDrawer";
import { MobileNav } from "@/components/MobileNav";
import { SWRegister } from "@/components/SWRegister";
import { BiometricLock } from "@/components/BiometricLock";

const inter = Inter({ subsets: ["latin"] });

export const viewport: Viewport = {
  themeColor: "#09090b",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export const metadata: Metadata = {
  title: "Escrivão AI",
  description: "Assistente Investigativo de Inteligência Policial",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "Escrivão AI",
  },
  formatDetection: { telephone: false },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark">
      <head>
        <link rel="manifest" href="/manifest.webmanifest" />
      </head>
      <body className={`${inter.className} min-h-screen bg-zinc-950 text-zinc-50 antialiased`}>
        <SWRegister />
        <BiometricLock />
        <TooltipProvider>
          {/* Desktop: sidebar lateral + main + drawer */}
          <div className="flex bg-zinc-950 min-h-screen">
            {/* Sidebar só aparece no desktop (md+) */}
            <div className="hidden md:block">
              <Sidebar />
            </div>
            {/* main: no mobile tem padding-bottom para não cobrir a nav inferior */}
            <main className="flex-1 w-full bg-zinc-950/50 max-h-screen overflow-y-auto overflow-x-hidden pb-16 md:pb-0">
              {children}
            </main>
            <CopilotoDrawer />
            <AlertasDrawer />
          </div>
          {/* Nav inferior só no mobile */}
          <MobileNav />
        </TooltipProvider>
      </body>
    </html>
  );
}
