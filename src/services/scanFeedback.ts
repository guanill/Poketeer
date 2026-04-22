/**
 * Scan feedback logger.
 *
 * Records what the scanner predicted vs what the user confirmed for every
 * completed scan. The table feeds two things:
 *   1. Offline analysis — which sets / card layouts / languages fail most
 *   2. Future work — training a learned confidence calibrator
 *
 * One row per job, regardless of how many times the handlers fire (a user
 * may click "Add" on several ranked rows before dismissing — only the first
 * add counts as the decisive action). Failures are silent; feedback is
 * telemetry, not a feature the user can see breaking.
 */

import { supabase } from '../lib/supabase';
import type { ScanJob } from '../store/scanStore';

export type ScanOutcome = 'add_top' | 'add_other' | 'search_manual' | 'dismiss';

// Dedup across the session — a job is only logged once, on its decisive action.
const loggedJobs = new Set<string>();

interface FeedbackInput {
  job: ScanJob;
  outcome: ScanOutcome;
  userFinalCardId: string | null;
}

export async function logScanFeedback({ job, outcome, userFinalCardId }: FeedbackInput): Promise<void> {
  if (loggedJobs.has(job.id)) return;
  if (job.status === 'scanning') return;
  loggedJobs.add(job.id);

  const top = job.matches[0] ?? null;
  const wasTopCorrect =
    outcome === 'dismiss' ? null
    : top && userFinalCardId ? top.id === userFinalCardId
    : null;

  const ocrText = job.result?.ocr_text ?? '';
  const langMatch = ocrText.match(/\| lang: ([a-z]+)/);
  const ocrLanguage = langMatch ? langMatch[1] : '';

  try {
    const { data } = await supabase.auth.getUser();
    await supabase.from('scan_feedback').insert({
      user_id: data.user?.id ?? null,
      top_match_card_id: top?.id ?? null,
      top_match_confidence: top?.confidence ?? null,
      scan_method: job.result?.method_used ?? '',
      user_final_card_id: userFinalCardId,
      was_top_correct: wasTopCorrect,
      outcome,
      ocr_text: ocrText,
      ocr_language: ocrLanguage,
      candidate_count: job.matches.length,
    });
  } catch {
    // Silent — feedback is non-critical telemetry.
  }
}
