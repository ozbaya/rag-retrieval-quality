import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "RAG Retrieval Quality Demo",
  description: "Three RAG configurations compared on the same questions, with measured retrieval and answer quality.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-white text-gray-900 antialiased">
        <nav className="border-b">
          <div className="mx-auto flex max-w-7xl gap-6 px-4 py-3 text-sm">
            <Link href="/" className="font-semibold">RAG Quality Demo</Link>
            <Link href="/benchmark">Benchmark</Link>
            <Link href="/how-it-works">How it works</Link>
            <a href={process.env.NEXT_PUBLIC_REPO_URL ?? "#"} className="ml-auto">GitHub</a>
          </div>
        </nav>
        {children}
        <footer className="mx-auto max-w-7xl px-4 py-8 text-xs text-gray-500">
          Built by <a className="underline" href={process.env.NEXT_AO_LINKEDIN ?? "#"}>And Ozbay</a> ·{" "}
          <a className="underline" href={process.env.NEXT_PUBLIC_REPO_URL ?? "#"}>Repo for this app</a> ·{" "}
          <a className="underline" href={process.env.NEXT_AO_GITHUB ?? "#"}>Github</a>
        </footer>
      </body>
    </html>
  );
}

