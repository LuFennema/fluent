---
name: fluent-pronunciation
description: Run a repeat-after-me pronunciation session — the tutor speaks a word or sentence with local text-to-speech, the learner says it into the microphone, and the skill scores it at the phone level (acoustic phoneme recognizer vs. espeak-ng target IPA) with Whisper as a word-level fallback, then explains which sounds were off. Triggered when the learner types /fluent-pronunciation or picks it from the /fluent-learn menu. Needs TTS, a microphone and a speech-to-text backend (run /fluent-voice-setup if missing). Updates all databases at the end.
allowed-tools: Read, Write, Bash
---

# Pronunciation Practice (Microphone)

## Overview

Real spoken output, scored locally. Loop per item: Claude **speaks the model** → learner **repeats into the mic** → `voice-listen.py --expect` returns **two scores**:

- `phonemes` — **the one to trust.** An acoustic phoneme recognizer (wav2vec2, no language model) writes down the sounds the learner actually produced; espeak-ng gives the sounds the sentence should have; the two are aligned phone by phone and attributed to words. `phonemes.score` 0-100, `per_word[].accuracy`, `weak_words`, `top_confusions` (e.g. `expected "r", heard "ɾ"`), `target_ipa` / `heard_ipa`.
- `score` — the Whisper transcript compared word by word. Lenient: Whisper is a language model and quietly corrects *pero*→*perro* when *perro* fits the sentence. Use it only when `phonemes.available` is false.

When `phonemes` is present but `available: false`, it still carries `target_ipa` — show it to the learner anyway; seeing /ˈpero/ vs /ˈpeɾo/ is useful even without scoring.

Three item types, interleaved:
1. **Minimal pairs** — two words differing in one sound (`man / maan`, `pero / perro`). The sharpest diagnostic.
2. **Sentences** — 5-12 words, with the week's weak sounds and due vocabulary.
3. **Shadowing** — a longer line (15-20 words) spoken at 0.9×, learner repeats with the same rhythm. B1+.

## When to Use

Trigger this skill when the learner types `/fluent-pronunciation`, picks it from the `/fluent-learn` menu, or explicitly asks to start this practice. Never start it from an ambiguous message — a 15-20 min interactive session that writes 6 databases must be what the learner asked for.

Any level from A1 — pronunciation is the one skill that benefits from starting on day one.

## Instructions

### 1. Load context and check the audio stack

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/read-db.py"
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py" --json
```

All three required checks (`tts`, `microphone`, `speech-to-text`) must be `ok`. If not: one line saying which is missing, hand off to `/fluent-voice-setup`, stop.

Note `phoneme_scoring` in the same JSON. If false, tell the learner once at the opening that scoring is word-level today and that `/fluent-voice-setup` explains how to turn on phone-level scoring; then carry on.

Pre-warm the models so the first item doesn't stall (safe no-op if already running):

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-server.py" start
```

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

The JSON gives `transcript`, `confidence`, `score: {similarity, missed, heard_instead}` and, when available, `phonemes: {score, per_word, weak_words, top_confusions, target_ipa, heard_ipa}`. Never pass `--prompt` here — biasing the recognizer toward the target would hide exactly the errors we're measuring.

Error handling:
- `ok: false` with a recording error → say "I couldn't open the microphone", run the doctor, hand off to `/fluent-voice-setup`.
- Empty transcript / `recording.seconds < 0.4` → "I didn't catch anything — the mic may have cut off early. Say `again`."
- `confidence < 0.4` and similarity < 50 → treat as unclear rather than wrong: ask for one `again` before scoring.

### 5. Score and coach

Use `phonemes.score` when `phonemes.available` is true, else `score.similarity`. Thresholds:
- **≥ 90** → ✅ correct
- **70-89** → 🟡 close — item correct if the only issues are near misses (`near: true`, e.g. vowel length) or function words; otherwise one retry allowed, best of two counts
- **< 70** → ❌ — explain, retry once, best of two counts

Feedback template (phone-level):

```markdown
{✅ Clear! | 🟡 Close | ❌ Let's fix one sound}

**Target:** "{target_text}"  /{target_ipa}/
**You said:** /{heard_ipa}/   (Whisper heard: "{transcript}")
**Match:** {phonemes.score}%   {per word: perro 75% · corre 100% …}

{For each entry in top_confusions (max 2), one line of articulatory coaching:}
- **/{expected}/ → /{heard}/** in *{word}* → {what to do with lips/tongue/length/stress — one concrete instruction}

🔊 Listen once more and try again? (`again`)
```

Word-level fallback (no phoneme recognizer): same template with `score.similarity`, `missed` → `heard_instead` pairs, and `target_ipa` if present.

Interpretation rules:
- `substitute` with `near: true` = right sound, wrong length/quality → coach **length** ("hold it twice as long").
- `delete` at word end = dropped final consonant → coach **release** ("finish the `t`").
- `insert` of `ə` between consonants = epenthesis (common for Spanish/Japanese speakers) → coach **clusters** ("no vowel between `s` and `t`").
- The same `expected→heard` pair in two items = the session's focus sound; add a minimal pair for it next.
- If `heard_phones` is far shorter than `target_phones` (< 60%), the mic probably cut off → `again`, don't score.

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
- `errors[]` — `category: "pronunciation"`, `pattern_id` from the confusion pair (e.g. `pronunciation_r_to_ɾ`, `pronunciation_aː_to_ɑ`, `pronunciation_final_t_dropped`), `your_answer` = `heard_ipa`, `correct_answer` = `target_ipa`, `context` = the word
- `vocabulary_reviewed[]` — due words that appeared: quality 5 if ≥ 90 first try, 4 on retry, 2 if < 70 twice
- `focus_next_session[]` — top sound

Save per-item target / transcript / similarity to `/results/fluent-pronunciation-session-{NNN}.md`. Recordings themselves are **not** kept (`voice-listen.py` deletes the WAV unless `--keep`).

## Examples

### Minimal pair (Dutch, native Spanish speaker)

Claude speaks `"man, maan"` with `--quiet`, then records. Result: `phonemes.score: 83`, `top_confusions: [{expected: "aː", heard: "ɑ"}]`, `weak_words: ["maan"]`, `target_ipa: "mɑn maːn"`, `heard_ipa: "mɑnmɑn"`. (Whisper's transcript was "man maan" — it guessed the second word from context, which is exactly why we don't score on it.)

> 🟡 Close
>
> **Target:** "man, maan"  /mɑn maːn/
> **You said:** /mɑn mɑn/   (Whisper heard: "man maan")
> **Match:** 83%   man 100% · maan 67%
>
> - **/aː/ → /ɑ/** in *maan* → you made the short vowel twice. The long `aa` is nearly twice as long and the mouth opens wider — hold it: *maaaan*. Spanish has no length contrast, so exaggerate it at first.
>
> 🔊 Listen once more and try again? (`again`)

### Sentence (Spanish A2)

Target `"El perro corre por el parque."` → `phonemes.score: 95`, `per_word: perro 75%`, `top_confusions: [{expected: "r", heard: "ɾ"}]`, `target_ipa: "el pero kore poɾ el paɾke"`, `heard_ipa: "elpeɾokorepoɾelpaɾke"`.

> 🟡 Close
>
> **Target:** "El perro corre por el parque."  /el pero kore poɾ el paɾke/
> **You said:** /el peɾo kore poɾ el paɾke/
> **Match:** 95%   perro 75% · everything else 100%
>
> - **/r/ → /ɾ/** in *perro* → single tap instead of the trill. Tongue tip loose behind the top teeth, push air until it vibrates — try *rrr* alone first, then *perro*.
>
> *corre* was a clean trill, so you have the sound — it's the `pe-` onset that's rushing it. 🔊 `again`?

## Critical Rules

- **All three backends must be ok before the opening.** Hand off to `/fluent-voice-setup` otherwise — never run a text-only "pronunciation" session.
- **Don't print the target before recording** (except shadowing). Imitate sound, not spelling.
- **Trust `phonemes` over `score`.** Whisper hides pronunciation errors; the phoneme recognizer doesn't. Fall back to word-level only when phone-level is unavailable, and say so once.
- **Scores are still a proxy.** Recognizers make mistakes too; when `confidence` is low or `heard_phones` is suspiciously short, offer `again` rather than marking a miss.
- **Coach articulation, not just the word.** Every miss gets one concrete instruction about lips, tongue, length, stress or pitch.
- **Best of two counts.** One retry per item, no more — keep momentum.
- **Audio stays local and is deleted.** Say so if asked.
- **Start only on request.** Slash command, `/fluent-learn` menu pick, or an explicit ask — never from an ambiguous message.

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
