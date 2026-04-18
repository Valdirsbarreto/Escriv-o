import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Sidebar } from "@/components/Sidebar";
import { CopilotoDrawer } from "@/components/CopilotoDrawer";

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
      <body className={`${inter.className} min-h-screen bg-zinc-950 text-zinc-50 antialiased`}>
        <TooltipProvider>
          <div className="flex bg-zinc-950 min-h-screen">
            <Sidebar />
            <main className="flex-1 w-full bg-zinc-950/50 max-h-screen overflow-y-auto overflow-x-hidden">
              {children}
            </main>
            <CopilotoDrawer />
          </div>
        </TooltipProvider>
      </body>
    </html>
  );
}
