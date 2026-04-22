-- ============================================================================
-- Scan feedback log
--
-- Records the outcome of every scan: what the scanner returned as the top
-- match, what the user ultimately confirmed, and what signals drove the call.
-- Used to (a) spot systemic failure modes (e.g. a particular set where OCR
-- reliably picks the wrong year-variant) and (b) eventually feed a learned
-- confidence calibrator.
--
-- One row per scan outcome. `user_final_card_id` is NULL when the user
-- dismisses without adding anything; `was_top_correct` is NULL in that same
-- case (we don't know if the top guess was right).
-- ============================================================================

create table scan_feedback (
  id                    uuid primary key default gen_random_uuid(),
  user_id               uuid references auth.users(id) on delete set null,
  created_at            timestamptz not null default now(),

  -- What the scanner returned as top
  top_match_card_id     text references cards(id) on delete set null,
  top_match_confidence  numeric,
  scan_method           text not null default '',   -- 'ocr' | 'visual' | 'combined' | 'none'

  -- What the user did
  user_final_card_id    text references cards(id) on delete set null,
  was_top_correct       boolean,                    -- NULL if user dismissed
  outcome               text not null,              -- 'add_top' | 'add_other' | 'search_manual' | 'dismiss'

  -- Raw signals for debugging + future calibration training
  ocr_text              text not null default '',
  ocr_language          text not null default '',
  candidate_count       int not null default 0
);

create index scan_feedback_user_idx on scan_feedback(user_id, created_at desc);
create index scan_feedback_top_card_idx on scan_feedback(top_match_card_id) where top_match_card_id is not null;

alter table scan_feedback enable row level security;

-- Users can only see/write their own feedback rows. Anonymous scans are
-- allowed (user_id may be null) — no one but the owning session sees them.
create policy "Users read own scan feedback"
  on scan_feedback for select using (auth.uid() = user_id);

create policy "Users insert own scan feedback"
  on scan_feedback for insert with check (auth.uid() = user_id or user_id is null);
