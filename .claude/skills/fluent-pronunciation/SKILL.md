---
name: fluent-pronunciation
description: Run a repeat-after-me pronunciation session — the tutor speaks a word or sentence with local text-to-speech, the learner says it into the microphone, local speech-to-text (Whisper) transcribes it, and the skill scores how close it was and explains which sounds were off. Triggered only when the learner types /fluent-pronunciation. Needs TTS, a microphone and a speech-to-text backend (run /fluent-voice-setup if missing). Updates all databases at the end.
allowed-tools: Read, Write, Bash
disable-model-invocation: true
---

# Pronunciation Practice (Microphone)

## Overview

Real spoken output, scored locally. Loop per item: Claude **speaks the model** → learner **repeats into the mic** → Whisper **transcribes** → `voice-listen.py --expect` returns a **word-level similarity** → Claude turns the mismatches into phonetic feedback.

A transcription miss is a proxy for a pronunciation problem: if the recognizer heard *"vier"* when the target was *"vuur"*, the learner's `uu` is drifting toward `ie`. That is the signal we coach on.

Three item types, interleaved:
1. **Minimal pairs** — two words differing in one sound (`man / maan`, `pero / perro`). The sharpest diagnostic.
2. **Sentences** — 5-12 words, with the week's weak sounds and due vocabulary.
3. **Shadowing** — a longer line (15-20 words) spoken at 0.9×, learner repeats with the same rhythm. B1+.

## When to Use

Trigger only on `/fluent-pronunciation`. Gated (`disable-model-invocation: true`).

Any level from A1 — pronunciation is the one skill that benefits from starting on day one.

## Instructions

### 1. Load context and check the audio stack

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/read-db.py"
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py" --json
```

All three checks (`tts`, `microphone`, `speech-to-text`) must be `ok`. If not: one line saying which is missing, hand off to `/fluent-voice-setup`, stop.

Need from the DBs: name, level, target_language, `mastery-db.skills_mastery.pronunciation` (treat missing as 1), `mistakes-db` entries with category `pronunciation` or `listening`, due vocabulary.

### 2. Opening

```markdown
# 🎙️ {target_language} Pronunciation Practice

Hallo {name}!

I'll say a word or sentence, then **you say it back into your microphone**. I transcribe what I hear and tell you which sounds landed and which drifted.

**How a turn works:**
1. You hear the model (🔊)
2. You see `🎙️ speak now` in the terminal → say it
3. Recording stops ~1.5 s after you go quiet (or after 15 s)

**Controls:** `replay` · `slower` · `again` (re-record the same item) · `skip`

**Level:** {CEFR} · **Items:** ~12 · **Duration:** 10-15 min

Quiet room helps. Ready? 🎧
```

Wait for confirmation. On the first ever session, run one throwaway item ("say your name") so they see the recording flow before it counts.

### 3. Build the item list

~12 items: 4 minimal pairs, 6 sentences, 2 shadowing (A1-A2: 6 pairs, 6 short sentences, no shadowing).

Sources, in priority order:
- `mistakes-db` pronunciation/listening patterns → minimal pairs for exactly those sounds.
- Due vocabulary → sentences containing those words.
- Language-specific hard sounds for the learner's native language (see Language Reference).

### 4. Run one item

Speak the model (do **not** print it yet for minimal pairs and sentences — the learner should imitate sound, not read; print it for shadowing since rhythm is the goal):

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-say.py" --quiet --lang "{target_language}" "{target_text}"
```

Show the prompt and immediately record:

```markdown
## 🎙️ Item {N}/{total} — {Minimal pair | Sentence | Shadowing}

{Shadowing only: the text}
{Minimal pair: "Say both words."}

Listen… now repeat.
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-listen.py" --lang "{target_language}" --max-seconds 15 --expect "{target_text}"
```

The JSON gives `transcript`, `confidence` (0-1 when the backend reports it), and `score: {similarity, missed, heard_instead}`.

Error handling:
- `ok: false` with a recording error → say "I couldn't open the microphone", run the doctor, hand off to `/fluent-voice-setup`.
- Empty transcript / `recording.seconds < 0.4` → "I didn't catch anything — the mic may have cut off early. Say `again`."
- `confidence < 0.4` and similarity < 50 → treat as unclear rather than wrong: ask for one `again` before scoring.

### 5. Score and coach

Thresholds on `score.similarity`:
- **≥ 90** → ✅ correct
- **70-89** → 🟡 close — item correct if the only misses are function words; otherwise one retry allowed, best of two counts
- **< 70** → ❌ — explain, retry once, best of two counts

Feedback template:

```markdown
{✅ Clear! | 🟡 Close | ❌ Let's fix one sound}

**Target:** "{target_text}"
**I heard:** "{transcript}"
**Match:** {similarity}%

{For each pair (missed → heard_instead), one line of phonetic coaching:}
- **{missed}** came out as *{heard_instead}* → {what to do with the mouth/tongue, one concrete instruction, e.g. "round your lips tighter and keep them still for `uu` — `ie` is what you get when they relax"}

{If relevant: the recognizer's own uncertainty — "the transcription was unsure here, so take this one lightly"}

🔊 Listen once more and try again? (`again`)
```

Keep coaching **articulatory and concrete** (lips, tongue position, length, stress, pitch). Never say just "wrong".

### 6. Adapt

- Three ✅ in a row → longer sentences or normal-speed shadowing.
- Same sound missed twice → insert a minimal pair for it next, then a sentence with it twice.

### 7. Session summary

```markdown
## 🎉 Pronunciation Session Complete!

**Items:** {N} · **Clear first try:** {count} · **Average match:** {avg}%

### Sounds that are solid
- {sound} ✅

### Sounds to drill
- **{sound}** — heard as *{x}* in "{word}" · tip: {one line}

### Streak
{streak line}

**Next time:** {sound} with 3 minimal pairs, then into sentences.
```

### 8. Update databases

Use `fluent-db-updater`:

- `command_used: "/fluent-pronunciation"`, `skills_practiced: ["pronunciation"]`
- `skill_scores.pronunciation: {exercises: N, correct: count_clear_or_close, time_minutes}`
- `errors[]` — `category: "pronunciation"`, `pattern_id` names the sound (e.g. `pronunciation_uu_vs_ie`, `pronunciation_rr_trill`, `pronunciation_final_devoicing`, `pronunciation_word_stress`), `your_answer` = transcript, `correct_answer` = target, `context` = the word
- `vocabulary_reviewed[]` — due words that appeared: quality 5 if ≥ 90 first try, 4 on retry, 2 if < 70 twice
- `focus_next_session[]` — top sound

Save per-item target / transcript / similarity to `/results/fluent-pronunciation-session-{NNN}.md`. Recordings themselves are **not** kept (`voice-listen.py` deletes the WAV unless `--keep`).

## Examples

### Minimal pair (Dutch, native Spanish speaker)

Claude speaks `"man, maan"` with `--quiet`, then records. Result: `transcript: "man man"`, `similarity: 50`, `missed: ["maan"]`, `heard_instead: ["man"]`.

> ❌ Let's fix one sound
>
> **Target:** "man, maan"
> **I heard:** "man man"
> **Match:** 50%
>
> - **maan** came out as *man* → the long `aa` is nearly twice as long as `a`, and the mouth opens wider. Hold it: *maaaan*. Spanish has no length contrast, so this one takes deliberate exaggeration at first.
>
> 🔊 Listen once more and try again? (`again`)

### Sentence (Spanish A2)

Target `"El perro corre por el parque."` → transcript `"El pero corre por el parque"`, similarity 83, `missed: ["perro"]`, `heard_instead: ["pero"]`.

> 🟡 Close
>
> **Target:** "El perro corre por el parque."
> **I heard:** "El pero corre por el parque"
> **Match:** 83%
>
> - **perro** came out as *pero* → that's the single-tap `r` instead of the trill `rr`. Tongue tip loose behind the top teeth, push air until it vibrates — try *rrr* alone first, then *perro*.
>
> Everything else was clean, including *corre* — so the trill works when it's between vowels you expect. 🔊 `again`?

## Critical Rules

- **All three backends must be ok before the opening.** Hand off to `/fluent-voice-setup` otherwise — never run a text-only "pronunciation" session.
- **Don't print the target before recording** (except shadowing). Imitate sound, not spelling.
- **Scores are a proxy.** The recognizer makes mistakes too; when `confidence` is low, soften the feedback and offer `again` rather than marking a miss.
- **Coach articulation, not just the word.** Every miss gets one concrete instruction about lips, tongue, length, stress or pitch.
- **Best of two counts.** One retry per item, no more — keep momentum.
- **Audio stays local and is deleted.** Say so if asked.
- **Never auto-invoke.**

## Language Reference

Hard sounds by target language (expand as needed; pick pairs that contrast with the learner's native language):

- **Dutch:** `ui` /œy/, `eu` /øː/, `uu` vs `ie`, `g`/`ch` fricative, `a` vs `aa`, final `-t`. Pairs: `man/maan`, `bot/boot`, `huis/hoes`, `vuur/vier`.
- **Spanish:** trill `rr` vs tap `r`, `b/v` same sound, `j` /x/, `ll/y`, unaspirated `p t k`. Pairs: `pero/perro`, `caro/carro`, `casa/caza` (Spain).
- **French:** nasals `an/on/in`, `u` /y/ vs `ou` /u/, `r` uvular, silent finals, liaison. Pairs: `tu/tout`, `vin/vent`, `dessus/dessous`.
- **German:** `ü/ö`, `ch` (ich vs ach), final devoicing, `z` = /ts/, `w` = /v/. Pairs: `Küche/Kuchen`, `schon/schön`, `Rad/Rat`.
- **English:** `th` both kinds, `i/iː` (ship/sheep), `æ` (cat), word stress, `r` vs `l` for some L1s. Pairs: `ship/sheep`, `thin/tin`, `bat/bet`.
- **Japanese:** vowel length, geminates, pitch accent, `r`. Pairs: `obasan/obaasan`, `kite/kitte`, `hashi` (pitch).
- **Korean:** aspirated/tense/plain stops, `ㅓ/ㅗ`. Pairs: `달/탈/딸`, `어/오`.
- **Portuguese (BR):** nasal diphthongs `ão`, open/closed `é/ê`, `lh/nh`. Pairs: `avô/avó`, `pão/pau`.
- **Arabic:** emphatic consonants, `ع` vs `أ`, `ح` vs `ه`, vowel length. Pairs: `قلب/كلب`, `سار/صار`.
