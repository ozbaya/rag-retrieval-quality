export default function HowItWorks() {
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-8 text-sm leading-6">
      <h1 className="text-2xl font-semibold">How it works</h1>
      <img src="/architecture.png" alt="Architecture diagram" className="rounded border" />
      <h2 className="text-lg font-semibold">Three configurations</h2>
      <ul className="list-disc pl-5">
        <li><b>Baseline:</b> fixed-size chunks (about 400 tokens), dense vector search.</li>
        <li><b>Intermediate:</b> structure-aware chunks split on headings, dense vector search.</li>
        <li><b>Advanced:</b> the same chunks, dense plus keyword search fused with reciprocal rank fusion, then a cross-encoder reranker.</li>
      </ul>
      <p>All three use the same documentation snapshot, questions, answer model, prompt and output limit, and pass the top 5 passages to the answer model.</p>
      <h2 className="text-lg font-semibold">How it is measured</h2>
      <p>Evidence is marked as character ranges in the source documents, so the comparison is fair even though the configurations cut the text differently. Retrieval is scored without any LLM. Answers are scored by a separate judge model, validated against human labels on a sample.</p>
      <img src="/trace.png" alt="Trace showing retrieval, fusion, reranking and generation" className="rounded border" />
      <p className="text-xs text-gray-500">
        Source content: Kubernetes Documentation, © The Kubernetes Authors, licensed under{" "}
        <a className="underline" href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>. Normalized and chunked (modified).
        Full methodology, limitations and per-question results are in the GitHub repository.
      </p>
    </main>
  );
}

