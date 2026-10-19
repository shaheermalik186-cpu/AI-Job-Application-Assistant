is in Supabase Dashboard > SQL Editor.
-- Uses Supabase Auth and Row Level Security so each user can access only their own applications.
create extension if not exists pgcrypto;

create table if not exists public.applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null,
  company text not null default '',
  url text not null default '',
  status text not null default 'Saved' check (status in ('Saved','Planning to Apply','Applied','Interview','Assessment','Offer','Rejected')),
  applied_on date not null default current_date,
  notes text not null default '',
  created_at timestamptz not null default now()
);

alter table public.applications enable row level security;

drop policy if exists "Users can view their own applications" on public.applications;
create policy "Users can view their own applications" on public.applications
  for select to authenticated using (auth.uid() = user_id);

drop policy if exists "Users can insert their own applications" on public.applications;
create policy "Users can insert their own applications" on public.applications
  for insert to authenticated with check (auth.uid() = user_id);

drop policy if exists "Users can update their own applications" on public.applications;
create policy "Users can update their own applications" on public.applications
  for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "Users can delete their own applications" on public.applications;
create policy "Users can delete their own applications" on public.applications
  for delete to authenticated using (auth.uid() = user_id);

grant select, insert, update, delete on public.applications to authenticated;
