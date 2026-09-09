import type { Metadata } from "next";
import { DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";

const dmSans = DM_Sans({
  subsets: ["latin"],
  variable: "--font-dm-sans",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Gridiron AI | General Manager",
  description: "Autonomous Fantasy Football Multi-Agent Platform & General Manager",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${dmSans.variable} ${jetbrainsMono.variable}`}>
      <body>
        <div style={layoutStyles.container}>
          <Sidebar />
          <main style={layoutStyles.main}>{children}</main>
        </div>
      </body>
    </html>
  );
}

const layoutStyles: Record<string, React.CSSProperties> = {
  container: {
    display: "flex",
    width: "100vw",
    height: "100vh",
    overflow: "hidden",
    backgroundColor: "var(--bg-base)",
  },
  main: {
    flex: 1,
    height: "100vh",
    overflowY: "auto",
    display: "flex",
    flexDirection: "column",
    backgroundColor: "var(--bg-base)",
  },
};
