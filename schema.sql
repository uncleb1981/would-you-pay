-- Good Idea / Bad Idea — Supabase setup.
-- Paste this whole file into Supabase → SQL Editor → New query → Run. Safe to re-run.

create table if not exists public.ideas (
  id          uuid primary key default gen_random_uuid(),
  text        text not null check (char_length(text) between 3 and 140),
  description text not null default '' check (char_length(description) <= 280),
  up          integer not null default 0,
  down        integer not null default 0,
  created_at  timestamptz not null default now()
);

create table if not exists public.votes (
  idea_id uuid not null references public.ideas(id) on delete cascade,
  voter   text not null check (char_length(voter) between 8 and 64),
  value   smallint not null check (value in (1, -1)),
  primary key (idea_id, voter)
);

-- Visitors can read ideas and post new ones (text + description only, so they
-- can't seed fake vote counts). Votes are only reachable through the functions below.
alter table public.ideas enable row level security;
alter table public.votes enable row level security;

drop policy if exists "anyone can read ideas" on public.ideas;
create policy "anyone can read ideas" on public.ideas for select using (true);
drop policy if exists "anyone can post ideas" on public.ideas;
create policy "anyone can post ideas" on public.ideas for insert with check (up = 0 and down = 0);

revoke all on public.ideas from anon, authenticated;
grant select on public.ideas to anon, authenticated;
grant insert (text, description) on public.ideas to anon, authenticated;
revoke all on public.votes from anon, authenticated;

-- Set, change, or clear (p_value = 0) one browser's vote, keeping the counts in sync.
create or replace function public.cast_vote(p_idea uuid, p_voter text, p_value int)
returns setof public.ideas
language plpgsql security definer set search_path = public
as $$
declare prev smallint;
begin
  if p_value not in (1, -1, 0) or char_length(p_voter) not between 8 and 64 then
    raise exception 'bad vote';
  end if;

  perform 1 from ideas where id = p_idea for update;
  if not found then raise exception 'no such idea'; end if;

  delete from votes where idea_id = p_idea and voter = p_voter returning value into prev;
  if p_value <> 0 then
    insert into votes (idea_id, voter, value) values (p_idea, p_voter, p_value);
  end if;

  update ideas set
    up   = up   - (case when prev = 1  then 1 else 0 end) + (case when p_value = 1  then 1 else 0 end),
    down = down - (case when prev = -1 then 1 else 0 end) + (case when p_value = -1 then 1 else 0 end)
  where id = p_idea;

  return query select * from ideas where id = p_idea;
end $$;

create or replace function public.my_votes(p_voter text)
returns table (idea_id uuid, value smallint)
language sql stable security definer set search_path = public
as $$ select idea_id, value from votes where voter = p_voter $$;

revoke all on function public.cast_vote(uuid, text, int) from public;
revoke all on function public.my_votes(text) from public;
grant execute on function public.cast_vote(uuid, text, int) to anon, authenticated;
grant execute on function public.my_votes(text) to anon, authenticated;

-- A few starter ideas so the page isn't empty on day one (only added if the table is empty).
insert into public.ideas (text, description, created_at)
select * from (values
  ('A 4-day work week for everyone', 'Same pay, one more day of weekend.', now() - interval '10 hours'),
  ('Replace all stairs with slides', 'Faster going down. Going up is your problem.', now() - interval '15 hours'),
  ('Pineapple belongs on pizza', 'Sweet + salty. Fight me.', now() - interval '5 hours'),
  ('Ban reply-all on company email', 'Only managers get the button.', now() - interval '20 hours')
) as seed(text, description, created_at)
where not exists (select 1 from public.ideas);
