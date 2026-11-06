-- RiftShark result store (Supabase / Postgres). Run once in the SQL editor.
-- Tables: batches (one per batch run), games (one row per game), deck_stats and card_stats (aggregates per batch),
-- replays (slimmed replay JSON for the viewer). Anonymous role may read everything; writes need the service role.

create table if not exists batches (
  id            bigint generated always as identity primary key,
  created_at    timestamptz not null default now(),
  label         text,
  deck_a        text not null,
  deck_b        text not null,
  policy_a      text not null,
  policy_b      text not null,
  games         int  not null,
  draws         int  not null default 0,
  avg_turns     real,
  avg_secs      real,
  engine_commit text,
  summary       jsonb
);

create table if not exists games (
  id         bigint generated always as identity primary key,
  batch_id   bigint references batches(id) on delete cascade,
  seed       int  not null,
  deck0      text not null,
  deck1      text not null,
  winner     int,
  reason     text,
  turns      int,
  points0    int,
  points1    int,
  first      int,
  decisions  int,
  secs       real,
  played0    text[],
  played1    text[]
);
create index if not exists games_batch on games(batch_id);

create table if not exists deck_stats (
  batch_id       bigint references batches(id) on delete cascade,
  deck           text not null,
  games          int,
  wins           int,
  win_rate       real,
  first_games    int,
  first_wins     int,
  first_win_rate real,
  avg_points     real,
  primary key (batch_id, deck)
);

create table if not exists card_stats (
  batch_id             bigint references batches(id) on delete cascade,
  deck                 text not null,
  card                 text not null,
  games                int,
  played               int,
  win_rate_when_played real,
  primary key (batch_id, deck, card)
);

create table if not exists replays (
  id        bigint generated always as identity primary key,
  batch_id  bigint references batches(id) on delete cascade,
  seed      int not null,
  decks     text[],
  winner    int,
  turns     int,
  frames    int,
  data      jsonb not null
);
create index if not exists replays_batch on replays(batch_id);

alter table batches    enable row level security;
alter table games      enable row level security;
alter table deck_stats enable row level security;
alter table card_stats enable row level security;
alter table replays    enable row level security;
create policy "public read" on batches    for select using (true);
create policy "public read" on games      for select using (true);
create policy "public read" on deck_stats for select using (true);
create policy "public read" on card_stats for select using (true);
create policy "public read" on replays    for select using (true);
