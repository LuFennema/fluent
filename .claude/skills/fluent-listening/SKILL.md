---
name: fluent-listening
description: Run an interactive listening-comprehension session — the tutor speaks sentences and short dialogues aloud with local text-to-speech, the learner types what they heard (dictation) or answers comprehension questions, and gets per-item feedback. Triggered when the learner types /fluent-listening or picks it from the /fluent-learn menu. Needs a text-to-speech backend (run /fluent-voice-setup if missing). Updates all databases at the end.
allowed-tools: Read, Write, Bash
---

# Listening Practice (Audio)

## Overview

The first Fluent skill that produces **sound**. Claude generates target-language audio with the local TTS backend and the learner responds by typing. Three exercise modes, interleaved:

1. **Dictation** — hear a sentence, type it exactly. Tests sound→spelling mapping and grammar recognition.
2. **Comprehension** — hear a 3-5 sentence passage or dialogue, answer a question about it. Tests meaning.
3. **Gap-fill** — hear a sentence, see it on screen with one word blanked, type the missing word. Good for numbers, verb endings, articles.

The learner never sees the text before answering (active recall from audio). Replays are allowed and tracked.

## When to Use

Trigger this skill when the learner types `/fluent-listening`, picks it from the `/fluent-learn` menu, or explicitly asks to start this practice. Never start it from an ambiguous message — a 15-20 min interactive session that writes 6 databases must be what the learner asked for.

Skip below A1 mastery 2 for dictation; use gap-fill with single words instead.

## Instructions

### 1. Load context and check audio

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/read-db.py"
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py" --json
```

Need: `learner-profile` (name, level, target_language), `mastery-db.skills_mastery.listening` (may not exist yet — treat as level 1), `mistakes-db` top patterns, due vocabulary from `spaced-repetition`.

If the doctor's `tts` check is not `ok`: say so in one line, hand off to `/fluent-voice-setup`, and stop. Do not fall back to a text-only session under this command — that would log listening practice that never happened.

### 2. Opening

```markdown
# 🎧 {target_language} Listening Practice

Hallo {name}!

I'll **speak** sentences and short dialogues out loud. You type what you hear, or answer a question about it. You won't see the text until after you answer.

**Controls** (type any of these instead of an answer):
- `replay` — hear it again
- `slower` — hear it again at 0.8× speed
- `skip` — show the text and move on
- `harder` — different voices, varied speed, background noise

**Level:** {CEFR} · **Duration:** 10-15 min · **Items:** ~10

Make sure your sound is on. 🔊 Ready?
```

Wait for confirmation.

### 3. Build the item list

~10 items, interleaved: 5 dictation, 3 comprehension, 2 gap-fill (A1-A2 → 3 dictation, 2 comprehension, 5 gap-fill).

Content priorities:
- Due vocabulary from `spaced-repetition.json` → embed in dictation sentences.
- Top 2 patterns from `mistakes-db` → sentences that exercise exactly those (e.g. if the learner confuses `de/het`, dictation sentences dense with articles).
- Sentence length by level: A1 4-6 words · A2 6-9 · B1 9-14 · B2+ 14+ and dialogues with two speakers.
- Natural speech: contractions, fillers, numbers, times, names.

### 4. Play one item

Speak **without printing the sentence**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-say.py" --quiet --lang "{target_language}" "{sentence}"
```

**Variety (the point of listening practice).** One voice at one speed in silence trains the ear for exactly one speaker. Once the learner clears 3 items in a row at normal speed, or at B1+ from the start, add `--variety` (random voice for the language + speed 0.9-1.1×), and from B2 or on `harder`, `--noise 0.1` (café) / `--noise 0.2` (street). Keep dictation items clean; put variety on comprehension items first. Don't repeat the same voice on consecutive dialogue lines — pass `--voice random` per line, or alternate two explicit voices (Kokoro Spanish: `ef_dora` / `em_alex`). Noise and alternate voices need a neural engine (Kokoro/Piper); with an OS voice the flags are ignored and the result says so. `replay` keeps the same voice and settings as the original play — re-run with the same explicit `--voice` and `--rate` the first call reported.

Pre-warm the engine at session start (no-op if already running) so items play without a pause:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-server.py" start
```

For dialogues, call once per line so the pause between speakers is natural; alternate `--voice` when the engine has two voices for the language (Kokoro: e.g. `ef_dora` / `em_alex`; macOS: see `say -v ?`), otherwise prefix lines with a spoken name.

Then show only the prompt:

```markdown
## 🎧 Item {N}/{total} — {Dictation | Comprehension | Gap-fill}

{Dictation: "Type exactly what you heard:"}
{Comprehension: the question, in the target language, with native translation for A1-A2}
{Gap-fill: the sentence with ______ where the word was}

**Your answer:**
```

Handle controls: `replay` → run voice-say again, note `replays += 1` for the item; `slower` → add `--rate 0.8`; `skip` → reveal, mark incorrect, continue.

### 5. Evaluate

**Dictation** — compare word by word (ignore case and final punctuation; treat accents/diacritics as a 🟡 moderate error, not a miss):

```markdown
{✅ Perfect! | 🟡 Almost | ❌ Not quite}

**You heard:** "{their_answer}"
**It was:**    "{sentence}"

{Diff line: each wrong/missing word in **bold**, extra words ~~struck~~}

{For each miss, one line: what the sound was, why it is tricky — e.g. "`ui` in *huis* sounds like /œy/, nothing like English"}

**Score:** {correct_words}/{total_words} words {→ item correct if ≥ 90%}
```

**Comprehension** — correct if the meaning matches; show the full transcript after answering, highlight the sentence that held the answer.

**Gap-fill** — exact word match; near-miss (wrong ending) is 🟡 with the ending rule explained.

Count an item with 2+ replays as correct but flag `needed_replays` in the session file — it feeds the next session's speed choice. Record per item which voice, rate and noise were used; a miss at 1.1× with noise is not the same gap as a miss at 0.8× in silence.

Use `fluent-feedback-formatter` severity tags for consistency.

### 6. Adapt mid-session

- 3 perfect in a row → next sentences +2 words, or normal speed if you were at 0.8×, or switch on `--variety` if not yet on, or add `--noise 0.1`.
- 2 misses in a row → shorter sentences, offer `slower` proactively, repeat the troublesome sound in the next item.

### 7. Session summary

```markdown
## 🎉 Listening Session Complete!

**Items:** {N} · **Accuracy:** {percent}% · **Replays used:** {count}

### Sounds you nailed
- {sound/pattern}

### Sounds to train
- {sound} — heard as "{what they typed}" in "{sentence}"

### New words you heard today
- {word} — {meaning}

**Next time:** {one concrete suggestion — e.g. "numbers and times at normal speed"}
```

### 8. Update databases

Use `fluent-db-updater`:

- `command_used: "/fluent-listening"`, `skills_practiced: ["listening"]`
- `skill_scores.listening: {exercises: N, correct: count, time_minutes}`
- `errors[]` — `category: "listening"`, `pattern_id` names the sound or feature missed (e.g. `listening_ui_diphthong`, `listening_final_t`, `listening_numbers_13_vs_30`), `your_answer` = what they typed, `correct_answer` = the sentence
- `vocabulary_reviewed[]` — words from the SR queue that appeared, with quality 5 if transcribed correctly first try, 3 with replays, 1 if missed
- `focus_next_session[]` — top sound to train

Save the transcript list and results to `/results/fluent-listening-session-{NNN}.md` (include each sentence, what the learner typed, replays).

## Examples

### Dictation (Dutch A2)

Claude runs `voice-say.py --quiet --lang Dutch "Morgen ga ik met de trein naar Utrecht."` and shows:

> ## 🎧 Item 3/10 — Dictation
>
> Type exactly what you heard:
>
> **Your answer:**

Learner: "Morgen ga ik met de trein naar Utrech"

> 🟡 Almost!
>
> **You heard:** "Morgen ga ik met de trein naar Utrech"
> **It was:**    "Morgen ga ik met de trein naar Utrecht."
>
> Morgen ga ik met de trein naar **Utrecht**
>
> - 🟢 Final `-cht`: the `t` is there but barely released after `ch` — listen for the tiny stop at the end. Common with *acht*, *nacht*, *licht* too.
>
> **Score:** 7/8 words → ✅ counted correct

### Comprehension (Spanish B1)

Claude speaks two lines (`voice-say.py` twice, one per speaker), then:

> ## 🎧 Item 6/10 — Comprehension
>
> ¿A qué hora quedan y dónde?
>
> **Your answer:**

## Critical Rules

- **Never print the sentence before the learner answers.** The whole point is audio-first recall. Use `--quiet` so the script's JSON doesn't echo the text either.
- **Always confirm TTS works before the opening** — hand off to `/fluent-voice-setup` otherwise.
- **One item at a time**, wait for the answer.
- **Replays are free and encouraged** — count them, never shame them.
- **Explain the sound, not just the spelling.** A listening miss is a phonology gap; the feedback names the sound.
- **Start only on request.** Slash command, `/fluent-learn` menu pick, or an explicit ask — never from an ambiguous message.
