# Changelog

All notable changes to Fluent will be documented in this file.

## [0.4.3] — 2026-10-28

### Fixed

Phone-level scoring marked correct Japanese as wrong. Rescoring a real session:
correct takes now score 100, real errors (o→a, short vowels, b→v, a dropped
vowel) still count.

- **Japanese is phonemized from its spoken reading** (fugashi + UniDic `pron`),
  so particle は / こんにちは are /wa/ and を is /o/; the word label stays as
  written.
- **Long vowels:** espeak's doubled vowel (o̞o̞, ää) is compared as long (oː).
- **Japanese allophones are not errors:** ɯ/u, ç/h, ɕ/ʃ, tɕ/tʃ, ʑ/ʒ, dʑ/dʒ, the
  tap r (ɽ/ɾ/r/l), and open/close variants of the five vowels. Scoring is
  language-aware (`score_phonemes(..., lang)`); other languages are unchanged.
- **Devoiced ɯ / i** after a voiceless consonant (です → des, ます → mas) is not
  a missed sound.
- **Trailing noise:** three or more extra phones after the target are reported
  as `extra_after` and not scored.
- **Alignment:** difflib replaced by a minimum-cost alignment (near miss 0.5,
  other mismatch 1, insert/delete 1), so a near miss lines up with the sound it
  replaced. `ç` keeps its cedilla, and `ᵝ` is dropped.
- tɕ/tʃ and dʑ/dʒ count as near misses in every language.

## [0.4.2] — 2026-10-28

### Fixed

- **Phone-level scoring returned 0 on espeak-ng 1.50.** `--ipa=3` does not
  separate phones there, so each word was compared as one blob. Now uses
  `--ipa --sep=_`. Also fixes the Spanish/Dutch G2P tests on that version.
- **Japanese pronunciation scoring.** Words split on CJK punctuation (、。！？);
  espeak's narrow marks (o̞, ä) and moraic ɴ match the recognizer's o / a / n;
  ɕ/ʃ and ʑ/ʒ count as near misses. Length (ː) and the nasal tilde still count.
- **Word-level score for Japanese.** `score_against` compares readings via
  fugashi + UniDic, so Whisper's ご飯 matches the lesson's ごはん; scripts
  without spaces fall back to character comparison.
- Older espeak-ng writes a trill as two taps (ɾ ɾ); merged into r.

## [0.4.1] — 2026-10-28

### Added

- **Recording ticks.** `voice-listen.py` plays a short high tick when recording
  starts and a lower one when it stops, so the learner knows when to speak.
  New `tick()` helper in `fluent_voice.py`; `FLUENT_MIC_TICK=0` turns it off.

### Changed

- **Practice skills can be started from the `/fluent-learn` menu.** Removed
  `disable-model-invocation: true` from `fluent-vocab`, `-writing`, `-speaking`,
  `-reading`, `-review`, `-listening` and `-pronunciation`, so picking a menu
  option hands off directly instead of asking the learner to type a second
  command. Their instructions still say to start only on an explicit request.
  `fluent-setup` (can reset progress) and `fluent-learn` stay gated.

## [0.4.0] — 2026-10-28

_Personal fork of [m98/fluent](https://github.com/m98/fluent) by LuFennema. Everything below 0.3.0 is upstream's work._

### Added

- Marketplace renamed `m98` → `lufennema`; install with `claude plugin marketplace add LuFennema/fluent && claude plugin install fluent@lufennema`. Remove the upstream marketplace first if you had it (`claude plugin marketplace remove m98`).

- **Voice features — local text-to-speech, microphone and speech-to-text.**
  New module `.claude/hooks/fluent_voice.py` with three CLIs: `voice-say.py`
  (speak text), `voice-listen.py` (record, transcribe, optionally score
  against an expected sentence) and `voice-doctor.py` (detect backends,
  print install hints per OS, `--test` plays a sentence, `--download-voice`
  pre-fetches the neural model). Backends are auto-detected — TTS: **Kokoro**
  (neural, best quality: en/es/fr/it/pt-BR/hi/ja/zh), **Piper** (neural, 40+
  languages, ~20-80 MB voice downloaded on first use), then macOS `say`,
  `espeak-ng`/`espeak`/`spd-say`, Windows SAPI, `pyttsx3`; mic: `sounddevice`, `ffmpeg`, `sox`, `arecord`; STT:
  `faster-whisper`, `openai-whisper`, whisper.cpp — and any engine can be
  plugged in with `FLUENT_TTS_CMD` / `FLUENT_STT_CMD`. Nothing leaves the
  machine; recordings are deleted after transcription.
- **`/fluent-listening`** — audio dictation, gap-fill and comprehension
  items spoken with TTS; `replay` / `slower` / `skip` controls; errors are
  logged as sounds, not spellings. Needs TTS only.
- **`/fluent-pronunciation`** — repeat-after-me with minimal pairs,
  sentences and shadowing; word-level similarity score from the transcript
  with articulatory coaching for each missed sound; best-of-two retries.
- **`/fluent-voice-setup`** — diagnostics and guided install (auto-invokes
  on "does voice work?").
- **`/fluent-speaking voice`** — spoken conversation mode: the tutor's
  lines are played aloud and the learner answers into the microphone;
  transcripts are evaluated like typed answers plus a light pronunciation
  note. `preferences.voice: true` in the profile makes it the default.
- `/fluent-learn` menu gains Listening and Pronunciation options when the
  audio stack is available; the adaptive mix may include listening items.
- **Phone-level pronunciation scoring** (`fluent_phonemes.py`). The target
  sentence is phonemized with espeak-ng (system binary or the pip-only
  `espeakng-loader`), the recording is run through an acoustic wav2vec2
  phoneme recognizer (`facebook/wav2vec2-xlsr-53-espeak-cv-ft`, no language
  model), and the two phone sequences are aligned and attributed to words.
  `voice-listen.py --expect` now returns `phonemes: {score, per_word,
  weak_words, top_confusions, target_ipa, heard_ipa}` next to the lenient
  Whisper word-level `score`. `/fluent-pronunciation` coaches from the
  phone-level result (e.g. `/r/ → /ɾ/ in perro`) and falls back to word level
  with a notice. Optional: without the recognizer the target IPA is still shown.
- **Voice server** (`fluent_server.py`, `voice-server.py start|stop|status`).
  A localhost JSON-lines server keeps Kokoro, Whisper and the phoneme model
  loaded between sentences; clients fall back to the one-shot path when it
  isn't running. Starts on first neural use, exits after 30 idle minutes,
  token-protected, `FLUENT_VOICE_SERVER=0` disables.
- **TTS sentence cache**: neural audio is cached in `<data_dir>/.voice/cache`
  keyed by engine/voice/rate/text (200 MB LRU cap), so repeated review items
  replay instantly.
- **Listening variety**: `voice-say.py --voice random` (per-language voice
  pools for Kokoro, downloaded Piper voices and macOS `say`), `--variety`
  (random voice + 0.9-1.1× speed) and `--noise 0..1` (pink-noise café/street
  mix, numpy). `/fluent-listening` gains a `harder` control and turns these on
  as the learner levels up.
- `voice-listen.py --prompt` passes an `initial_prompt` (names, session
  vocabulary) to Whisper for conversation turns in `/fluent-speaking voice`;
  it is deliberately ignored together with `--expect`.
- `voice-doctor.py` reports the phonemizer, the phoneme recognizer, whether
  phone-level scoring is on, and the voice server state.
- Tests: `tests/test_voice.py` (33) and `tests/test_phonemes.py` (22) cover
  language mapping, scoring, engine selection/fallback, Piper download,
  phoneme alignment, a live server with stub models, the cache, noise mixing
  and all CLIs with simulated engines.

### Changed

- Skill count 12 → 15. New mastery/skill keys `listening` and
  `pronunciation` flow through the existing `update-db.py` payload.
- `.gitignore` excludes `data/.voice/` recordings.

## [0.3.0] — 2026-06-15

### Added

- Milestones support in the `update-db.py` session payload. The new
  `milestones[]` field accepts either a bare string or an object
  `{ "milestone": <required non-empty string>, "date": <optional YYYY-MM-DD,
  defaults to the session date> }`. Each milestone is recorded in both
  `session-log.milestones[]` and `learner-profile.achievements[]`. Validation
  rejects malformed entries (exit `1`, no files written); an unparseable
  `date` falls back to the session date.

## [0.2.1] — 2026-06-11

### Fixed

- Hooks no longer fail on Windows with `No such file or directory` (#5).
  Plugin hook commands in `hooks.json` used the bash default-value syntax
  `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}`, which Claude Code's own
  variable substitution does not understand on Windows — it replaced the
  variable names but left the `:-` separators literal, producing a single
  garbage path. Hook commands now use plain `${CLAUDE_PLUGIN_ROOT}` (always
  set for plugin hooks) and invoke scripts via an explicit `python3`/`bash`
  interpreter so they don't depend on shebang handling under Git Bash.

## [0.2.0] — 2026-05-14

### Breaking changes

All 12 skills renamed with a `fluent-` prefix to prevent collisions with other
plugins and Claude Code built-ins. Update any muscle memory or external
references.

| Old | New |
|-----|-----|
| `/setup` | `/fluent-setup` |
| `/learn` | `/fluent-learn` |
| `/review` | `/fluent-review` |
| `/vocab` | `/fluent-vocab` |
| `/writing` | `/fluent-writing` |
| `/speaking` | `/fluent-speaking` |
| `/reading` | `/fluent-reading` |
| `/progress` | `/fluent-progress` |
| `sm2-calculator` | `fluent-sm2-calculator` |
| `db-updater` | `fluent-db-updater` |
| `feedback-formatter` | `fluent-feedback-formatter` |
| `session-analyzer` | `fluent-session-analyzer` |

New session result files use `/results/fluent-{skill}-session-{NNN}.md`.
Existing files using the older `{skill}-session-{NNN}.md` naming are still
read by `fluent-session-analyzer` — no migration required.

### Fixed

- Plugin install no longer fails on first DB read. Skills now invoke helper
  scripts via `${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/...`
  so the path resolves regardless of CWD.
- Added missing `.claude/hooks/ensure_data_dir.py` referenced by
  `fluent-setup`.

### Migration

```bash
claude plugin update fluent@lufennema
```

Then use the new slash commands. Your data (`~/.claude/fluent-data/` or
`./data/`) is unchanged.

## [0.1.0] — 2026-03-15

Initial release.
