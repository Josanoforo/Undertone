# Built with Codex

## Long

Undertone was built through a coordinated, evidence-led workflow. Each scoped assignment named an outcome and the files its worker could change. A Codex CLI worker implemented that slice, recorded focused checks and limits in a handoff, and a coordinator reviewed the evidence before the next slice moved forward. A “worker” means one Codex CLI execution responsible for a bounded task; a “handoff” records changes, checks and remaining limits.

The working agreement set a maximum of four concurrent workers and one writer per file. Sessions kept evidence and handoffs beside their work, making ownership and review visible. The examples below come from different points in development; they do not imply that every file or decision came from one worker.

An early backend handoff records ten passing HTTP tests and a Python compile check, while noting that ASR model setup and Twitch/OBS review remained pending at that stage (`sessions/mesa-02/M02-D01/HANDOFF.md`). Later implementation records describe browser capture feeding local faster-whisper speech recognition on CPU, tested with synthetic file input. That evidence does not establish physical microphone or Twitch audio capture (`app/docs/planificacion/LEVEL1_IMPLEMENTACION.md`, L1-02). A separate delivery record documents an approved version appearing in the live Twitch player and its withdrawn state replacing it with “Waiting” (`app/docs/planificacion/LEVEL1_IMPLEMENTACION.md`, L1-07). This supports the documented Browser Source route.

Codex CLI workers handled bounded implementation, checks, corrections and documentation. Jonás chose the product direction and retained human decisions and commitments; the coordinator scoped tasks and reviewed evidence. The project record also preserves distinct historical authorship for the ASR files and their later review and integration. The work therefore makes no blanket claim that Codex wrote every part of Undertone.

The result is a process whose claims can be traced to implementation and delivery records. Each test and observed demonstration supports only the route and cases it carefully covered. Human review kept the public account aligned with the recorded evidence.

At the verified app repository HEAD, the history contains 17 commits: from `322d5c5` on October 28 to `39fb99c` on November 2. The test directory contains 75 regular files, including fixtures and documentation; this count describes files present, not tests run or passed.

[CODEX SESSION ID: to be filled by Jonás via /status]

## Short

Undertone was built in scoped Codex CLI tasks. Each assignment named its outcome and file ownership; a Codex worker implemented the task, recorded focused checks and limits in a handoff, and a coordinator reviewed the evidence before work continued. The project agreement set a four-worker concurrency limit and one writer per file.

Evidence includes an early backend handoff with ten passing HTTP tests, later synthetic-input browser capture through local faster-whisper ASR, and an observed approved/withdrawn Browser Source journey on Twitch. These results apply to their documented cases. The app history contains 17 commits at the verified HEAD, and `app/tests/` contains 75 files, including fixtures and documentation—not a count of tests run. Jonás chose the product direction and retained human decisions; the coordinator scoped and reviewed. The project record preserves separate historical authorship and review for the ASR files, so no claim is made that Codex wrote every part.

[CODEX SESSION ID: to be filled by Jonás via /status]

## Voiceover sentences (each designed for ≤15 seconds)

1. “We built Undertone in scoped Codex CLI tasks, with checks, written handoffs, and human review.”
2. “Codex workers handled bounded implementation; Jonás chose the product direction and kept the decisions.”
3. “The evidence covers synthetic-input local transcription and an observed Twitch overlay journey.”

<!-- sources
AGENTS.md — workflow, four-worker maximum, one writer per file, historical ASR authorship.
sessions/mesa-02/M02-D01/HANDOFF.md — recorded compile check and 10/10 HTTP tests; early pending items.
app/docs/planificacion/LEVEL1_IMPLEMENTACION.md — L1-02 synthetic browser capture and local ASR limits; L1-07 observed approved/withdrawn Twitch route.
app/server/asr.py — faster-whisper import and CPU/int8 configuration (lines 202–219).
reports/encargos-codex/devpost/02_NARRATIVA_CODEX.md — requested content and formats.
Metrics verified read-only 2026-11-02 ~12:55 CDMX: app HEAD 39fb99c; 17 commits total. First commit 322d5c5 (2026-10-28); latest commit 39fb99c (2026-11-02, “Consolidate detached local startup and focused diagnostics”). Commands run from `app/`: `git rev-list --count HEAD`, `git log -1 --format='%h %cs %s'`, and `git log --reverse --format='%h %cs %s'` (first line). Each command used a per-command trusted-directory setting; no local path is included here and global Git configuration was not changed.
-->





