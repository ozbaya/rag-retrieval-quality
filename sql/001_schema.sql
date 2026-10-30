-- 001_schema.sql  (run once in the Supabase SQL editor)
create extension if not exists vector with schema extensions;

create table if not exists corpus_snapshots (
  snapshot_id           text primary key,
  corpus                text not null,
  source_type           text not null check (source_type in ('git','crawl')),
  source_ref            text not null,
  normalization_version text not null,
  doc_count             int  not null,
  content_sha256        text not null,
  created_at            timestamptz not null default now()
);

create table if not exists documents (
  snapshot_id     text not null references corpus_snapshots on delete cascade,
  doc_id          text not null,
  doc_version     text not null,
  source_url      text not null,
  source_path     text not null,
  title           text,
  normalized_text text not null,
  primary key (snapshot_id, doc_id)
);

create table if not exists chunking_configs (
  chunking_config_id text primary key,
  strategy           text not null check (strategy in ('fixed','structured')),
  params             jsonb not null
);

create table if not exists chunks (
  chunk_id           text primary key,
  snapshot_id        text not null,
  doc_id             text not null,
  doc_version        text not null,
  chunking_config_id text not null references chunking_configs,
  ordinal            int  not null,
  char_start         int  not null,
  char_end           int  not null,
  section_path       text,
  header_prefix      text not null default '',
  content            text not null,
  index_text         text not null,
  token_count        int  not null,
  embedding_model    text not null,
  embedding          vector(1536) not null,
  fts tsvector generated always as (
    setweight(to_tsvector('english', index_text), 'A') ||
    setweight(to_tsvector('simple',  index_text), 'B')
  ) stored,
  foreign key (snapshot_id, doc_id) references documents (snapshot_id, doc_id) on delete cascade,
  check (char_start >= 0 and char_end > char_start)
);
create index if not exists chunks_fts_idx   on chunks using gin (fts);
create index if not exists chunks_scope_idx on chunks (snapshot_id, chunking_config_id);

create table if not exists eval_datasets (
  dataset_version  text primary key,
  snapshot_id      text not null references corpus_snapshots,
  file_sha256      text not null,
  n_questions      int  not null,
  n_human_reviewed int  not null,
  created_at       timestamptz not null default now()
);

create table if not exists eval_questions (
  dataset_version text not null references eval_datasets on delete cascade,
  question_id     text not null,
  payload         jsonb not null,
  primary key (dataset_version, question_id)
);

create table if not exists benchmark_runs (
  run_id              text primary key,
  created_at          timestamptz not null default now(),
  git_sha             text not null,
  snapshot_id         text not null references corpus_snapshots,
  dataset_version     text not null references eval_datasets,
  pipeline_configs    jsonb not null,
  embedding_model     text not null,
  embedding_dims      int  not null,
  rerank_model        text not null,
  generation_model    text not null,
  judge_model         text not null,
  prompt_versions     jsonb not null,
  coverage_threshold  numeric not null,
  pricing_table_version text not null,
  notes               text
);

create table if not exists run_results (
  run_id            text not null references benchmark_runs on delete cascade,
  question_id       text not null,
  pipeline_id       text not null check (pipeline_id in ('baseline','intermediate','advanced')),
  retrieval         jsonb not null,
  context_chunk_ids text[] not null,
  context_tokens    int not null,
  answer            text not null,
  abstained         boolean not null,
  judge_outputs     jsonb,
  metrics           jsonb not null,
  usage             jsonb not null,
  latency_ms        jsonb not null,
  est_cost_usd      numeric,
  primary key (run_id, question_id, pipeline_id)
);

create table if not exists run_aggregates (
  run_id      text not null references benchmark_runs on delete cascade,
  pipeline_id text not null,
  metric      text not null,
  value       numeric,
  n           int not null,
  ci_low      numeric,
  ci_high     numeric,
  primary key (run_id, pipeline_id, metric)
);

-- Block Supabase's auto-generated REST API (anon/authenticated keys) from these tables.
-- Your scripts and the backend connect as the table owner (postgres), which bypasses RLS.
alter table corpus_snapshots enable row level security;
alter table documents        enable row level security;
alter table chunking_configs enable row level security;
alter table chunks           enable row level security;
alter table eval_datasets    enable row level security;
alter table eval_questions   enable row level security;
alter table benchmark_runs   enable row level security;
alter table run_results      enable row level security;
alter table run_aggregates   enable row level security;
