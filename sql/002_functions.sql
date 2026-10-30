-- 002_functions.sql
create or replace function match_dense(
  p_snapshot text, p_config text, p_query vector(1536), p_k int)
returns table (chunk_id text, score double precision, rank int)
language sql stable
set search_path = public, extensions
as $$
  select c.chunk_id,
         1 - (c.embedding <=> p_query)                                    as score,
         (row_number() over (order by c.embedding <=> p_query, c.chunk_id))::int as rank
  from chunks c
  where c.snapshot_id = p_snapshot and c.chunking_config_id = p_config
  order by c.embedding <=> p_query, c.chunk_id
  limit p_k;
$$;

-- kwq-v1: English terms joined with OR, plus non-stemmed identifier terms joined with OR
create or replace function kw_query(p_text text, p_identifiers text[])
returns tsquery
language plpgsql stable
as $$
declare
  q tsquery := null;
  e text;
  t text;
  tq tsquery;
begin
  e := replace(plainto_tsquery('english', p_text)::text, ' & ', ' | ');
  if e <> '' then
    q := e::tsquery;
  end if;
  if p_identifiers is not null then
    foreach t in array p_identifiers loop
      tq := plainto_tsquery('simple', t);
      if tq::text <> '' then
        q := case when q is null then tq else q || tq end;
      end if;
    end loop;
  end if;
  return q;
end;
$$;

create or replace function match_keyword(
  p_snapshot text, p_config text, p_text text, p_identifiers text[], p_k int)
returns table (chunk_id text, score double precision, rank int)
language sql stable
set search_path = public, extensions
as $$
  with q as (select kw_query(p_text, p_identifiers) as tsq)
  select c.chunk_id,
         ts_rank_cd(c.fts, q.tsq)::double precision as score,
         (row_number() over (order by ts_rank_cd(c.fts, q.tsq) desc, c.chunk_id))::int as rank
  from chunks c, q
  where q.tsq is not null
    and c.snapshot_id = p_snapshot and c.chunking_config_id = p_config
    and c.fts @@ q.tsq
  order by score desc, c.chunk_id
  limit p_k;
$$;
