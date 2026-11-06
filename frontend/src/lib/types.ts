export type PipelineId = "baseline" | "intermediate" | "advanced";
export const PIPELINES: { id: PipelineId; name: string; desc: string }[] = [
  { id: "baseline", name: "Baseline", desc: "Fixed-size chunks, dense search" },
  { id: "intermediate", name: "Intermediate", desc: "Structure-aware chunks, dense search" },
  { id: "advanced", name: "Advanced", desc: "Structure-aware chunks, hybrid search, RRF, rerank" },
];

export type StageItem = { chunk_id: string; score: number; rank: number };
export type Chunk = { chunk_id: string; title: string; section_path: string; source_url: string; content: string };
export type PipelineResult = {
  stages: Record<string, StageItem[]>;
  top5: Chunk[];
  answer: string;
  abstained: boolean;
  correctness?: string | null;
  metrics?: Record<string, number>;
  latency_ms: Record<string, number>;
  est_cost_usd: number | null;
};
export type Preset = {
  question_id: string;
  question: string;
  question_type: string;
  answerable: boolean;
  human_review_status: string;
  pipelines: Record<PipelineId, PipelineResult>;
};
export type PresetsResponse = { run_id: string; presets: Preset[]; label: "measured" };
export type Aggregate = {
  pipeline_id: string; metric: string; value: number | null; n: number; ci_low: number | null; ci_high: number | null;
};
export type BenchmarkResponse = {
  run_id: string; created_at: string; snapshot_id: string;
  models: Record<string, string>;
  dataset: { dataset_version: string; n_questions: number; n_human_reviewed: number };
  judge_validation: Record<string, { n: number; agreement: number; kappa?: number; provisional?: boolean }>;
  aggregates: Aggregate[];
};

