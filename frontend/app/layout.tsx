import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";
import { ToastProvider } from "@/components/Toast";

export const metadata: Metadata = {
  title: "SocialGraph — Friend Network System",
  description: "Interactive social network friend graph with BFS paths, recommendations, and analytics.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body>
        <ToastProvider>
          <Navbar />
          <main className="pt-14 min-h-screen">
            {children}
          </main>
        </ToastProvider>
      </body>
    </html>
  );
}
