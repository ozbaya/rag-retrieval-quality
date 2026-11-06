import PresetExplorer from "@/components/PresetExplorer";
import AskBox from "@/components/AskBox";
import { backendGet } from "@/lib/backend";
import type { PresetsResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function Home() {
  const data = await backendGet<PresetsResponse>("/presets");
  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-8 px-4 py-8">
      <section className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">RAG retrieval quality, measured</h1>
        <p className="max-w-3xl text-sm text-gray-600">
          Three retrieval configurations answer the same questions over the same Kubernetes documentation snapshot,
          with the same answer model and prompt. Pick a question to compare what each one retrieved, what it answered
          and how it scored.
        </p>
      </section>
      <PresetExplorer presets={data.presets} runId={data.run_id} />
      {process.env.ASK_ENABLED === "1" && (
        <section className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">Try your own question</h2>
          <AskBox />
        </section>
      )}
    </main>
  );
}

