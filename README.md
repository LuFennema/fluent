# 🌍 Fluent
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Claude Code](https://img.shields.io/badge/Powered%20by-Claude%20Code-blue)](https://code.claude.com)

**The AI Language Learning Kit for Claude Code and others**

*A comprehensive set of rules, guidance, and intelligent tracking systems that transform Claude Code into your personal language tutor. Master any language through adaptive practice powered by proven cognitive science—spaced repetition, active recall, and progress tracking that learns from you.*

https://github.com/user-attachments/assets/66d68aad-210a-452d-b405-b58c13f42f53

---



## 🚀 Quick Start

### 1. Install

```bash
claude plugin marketplace add m98/fluent && claude plugin install fluent@m98
```

One line. Registers the marketplace, installs the plugin. Works globally from any directory after this.

### 2. Start learning

Restart Claude Code, then:

```
/fluent-setup     # onboard: name, target language, level, goals
/fluent-learn     # begin your first session
```

That's it.

---

### Requirements

- [Claude Code](https://code.claude.com) installed
- **Python 3.8+** (most systems already have it — check with `python3 --version`). Install via [python.org](https://www.python.org/downloads/), `brew install python3`, or your distro's package manager. No pip packages needed — Fluent uses only the standard library.
- **Bash** for the PreCompact backup hook (built-in on macOS/Linux; on Windows use WSL or Git Bash).
- **Optional, for voice features** (`/fluent-listening`, `/fluent-pronunciation`, `/fluent-speaking voice`): a text-to-speech engine (built into macOS and Windows; `espeak-ng` on Linux), plus `pip install faster-whisper sounddevice numpy` for microphone + speech recognition. Everything runs locally — see [🔊 Voice features](#-voice-features-local-audio). Run `/fluent-voice-setup` to check what your machine has.

### Verify, update, uninstall

```bash
claude plugin list                    # expect: fluent@m98  enabled
claude plugin update fluent@m98       # pull latest version
claude plugin uninstall fluent@m98    # remove entirely
```

### Alternative: git clone

Prefer to hack on the skills or keep per-project state?

```bash
git clone https://github.com/m98/fluent.git
cd fluent
claude          # launch from repo root
/fluent-setup
```

Learner data lives in `./data/` inside the cloned repo instead of `~/.claude/fluent-data/`.

### Where your data lives

Fluent resolves the data directory in this order — first match wins:

1. `$FLUENT_DATA_DIR` if set (override everything).
2. `$CLAUDE_PROJECT_DIR/data/` if it has `learner-profile.json` (clone mode, running from outside the repo root).
3. `./data/` if it has `learner-profile.json` (clone mode, running inside the repo).
4. `~/.claude/fluent-data/` (plugin-install default).

Set `FLUENT_DATA_DIR` to run multiple learners on one machine:

```bash
export FLUENT_DATA_DIR=~/.fluent/dutch
```

Check where Fluent is currently looking:

```bash
python3 -c "import sys; sys.path.insert(0, '.claude/hooks'); from fluent_paths import data_dir; print(data_dir())"
```

---

## 💡 Why This Actually Works

Most language learning apps fail because they're built for engagement metrics, not actual learning. This system is different.

### 🎯 Three Reasons This Works Where Others Fail:

**1. Zero Distractions, Pure Focus**
- ❌ No ads interrupting your flow
- ❌ No gamification gimmicks designed to waste your time
- ❌ No unreliable fancy UI that breaks
- ✅ Just you, the language, and an AI that adapts to your needs

**2. Infinitely Adaptable Intelligence**
- 🧠 Want to practice job interview phrases? Just ask.
- 🧠 Need help with a specific grammar rule? It explains it.
- 🧠 Want to focus on restaurant vocabulary? It creates exercises instantly.
- 🧠 **You're in control.** The AI does exactly what you need, when you need it.

**3. Your Private, Smart Tutor**
- 📊 **Tracks everything** - Every answer, every mistake, every improvement
- 🔄 **Learns about YOU** - Knows your weak patterns and strengths
- 📈 **Adapts to YOU** - Adjusts difficulty based on your performance
- 🔒 **Private** - All data stays on your machine, no external tracking
- 🎯 **Personal** - Like having a tutor who knows your exact level and learning style

**The Result?** A learning system that feels like a conversation with an expert friend who remembers everything, tracks your progress scientifically, and makes learning actually enjoyable.

---

## 📖 What Is This?

This is a comprehensive, **open-source language learning system** that transforms [Claude Code](https://code.claude.com) into your personal AI language tutor.

The system uses **evidence-based learning methodologies** including:
- **Spaced Repetition (SM-2 algorithm)** - Review at optimal intervals
- **Active Recall** - Test yourself before seeing answers
- **Adaptive Difficulty** - Always challenging, never frustrating
- **Comprehensive Tracking** - Every answer tracked and analyzed

### ✨ Key Features

- 🎯 **Multi-Language Support** - Learn any language (French, Spanish, German, Japanese, Korean, Arabic, Dutch, etc.)
- 📊 **Comprehensive Tracking** - Automatic progress monitoring with detailed statistics
- 🧠 **Spaced Repetition** - SM-2 algorithm schedules reviews just before you forget
- 🎮 **Gamification** - Streaks, achievements, mastery levels (0-5 stars)
- 🔄 **Adaptive Difficulty** - Automatically adjusts to your performance (targets 60-70% success rate)
- 📝 **Multi-Modal Practice** - Writing, speaking, vocabulary, reading, listening
- 🔊 **Real audio** - Hear the language (local text-to-speech), speak it into your mic, and get pronunciation feedback from local speech recognition (Whisper). No cloud, no API keys.
- ⚡ **Immediate Feedback** - Clear explanations with every correction
- 🎨 **Interactive Sessions** - One question at a time, conversational feel
- 📈 **Progress Visualization** - Detailed statistics and trend analysis
- 💾 **Automatic Backups** - Hooks ensure your data is always safe

---

## 📚 How It Works

### The Learning Loop

Every practice session follows this intelligent cycle:

| Step | What Happens | Why It Matters |
|------|--------------|----------------|
| **1. You Practice** | Answer a question in your target language | Active recall forces your brain to retrieve information |
| **2. AI Analyzes** | System evaluates your response instantly | Identifies exactly what you got right or wrong |
| **3. Get Feedback** | Clear explanation of mistakes + correct version | Learning happens when you understand WHY |
| **4. System Tracks** | Updates 4 databases automatically | Remembers your weak spots and strengths |
| **5. Adapts** | Next question matches your current level | Always challenging, never frustrating |

**What Gets Tracked:**
- ✅ **Error Patterns** - Which grammar/vocab you struggle with
- ✅ **Mastery Levels** - Your skill rating (0-5 stars) for each topic
- ✅ **Review Schedule** - When to review based on SM-2 algorithm
- ✅ **Progress Stats** - Accuracy trends, streak days, total practice time

### Evidence-Based Methods

This system implements proven learning science:

**1. Active Recall** - You retrieve from memory before seeing answers
- 🔬 Research shows: **2-3x better retention** than passive review

**2. Spaced Repetition (SM-2 Algorithm)** - Reviews appear just before you forget
- 🔬 Research shows: **Prevents forgetting curve**, optimizes long-term retention

**3. Immediate Feedback** - Mistakes corrected within seconds
- 🔬 Research shows: **Faster learning** when feedback is immediate

**4. Interleaving** - Mix topics to prevent drilling fatigue
- 🔬 Research shows: **Better discrimination** and long-term retention

**5. Comprehensible Input (i+1)** - Content slightly above your level
- 🔬 Research shows: **Optimal learning zone** (Krashen's Input Hypothesis)

**6. Desirable Difficulty** - Targets 60-70% success rate
- 🔬 Research shows: **Too easy = no learning, too hard = frustration**

---

## 🎮 Available Commands & Skills

Fluent is built as **Claude Code skills** — 15 of them. Skills work two ways:

1. **Type the slash command** (`/fluent-learn`, `/fluent-vocab`, etc.) — you explicitly start a session. Learner-facing skills are gated so they only run this way. No accidental 20-minute session triggered by a chat message.
2. **Ask naturally** — read-only skills like `/fluent-progress` auto-trigger when you ask "how am I doing?" or "what's my streak?". Helper skills (SM-2 math, feedback formatter, DB updater, session analyzer) auto-load whenever Claude needs them during a session.

All 15 skills appear in your `/` menu so you can always invoke any of them manually.

### Learner-facing commands

These are the commands you'll use daily. Each is backed by a dedicated skill under `.claude/skills/`.

#### Core Commands

| Command | What It Does | When & Why to Use It |
|---------|--------------|----------------------|
| **`/fluent-setup`** | **One-time onboarding** - Asks you questions about your name, target language, current level, goals, and timeline. Creates your personalized learning profile. | **First time only** - Run this once to set up your account. The system generates a custom learning plan based on your answers. |
| **`/fluent-learn`** | **Adaptive mixed practice** - Combines different exercise types (vocabulary, grammar, sentences) based on your weak areas. Adjusts difficulty in real-time based on your performance. | **Daily core practice** - Your main command for general improvement. The AI decides what you need to practice most. Best after `/fluent-review`. |
| **`/fluent-review`** | **Spaced repetition session** - Shows you items that are due for review today based on the SM-2 algorithm. Focuses on things you learned before that need reinforcement. | **Start every day here!** - Review before learning new content. This is scientifically proven to be the most effective way to retain what you've learned. |

#### Skill-Specific Commands

| Command | What It Does | When & Why to Use It |
|---------|--------------|----------------------|
| **`/fluent-vocab`** | **Flashcard-style vocabulary drills** - Rapid-fire translation practice (target language ↔ native language). Tracks which words you struggle with. | **2-3x per week** - When you need to build vocabulary quickly. Great for preparing for specific topics (travel, business, etc.). |
| **`/fluent-writing`** | **Writing practice** - Practice emails, letters, essays, or forms in your target language. Get detailed corrections with grammar explanations. | **Daily for exam prep** - Essential if you're preparing for language exams. Also great for building confidence in real-world communication. |
| **`/fluent-speaking`** | **Conversation practice** - Role-play scenarios through typed dialogue, or **spoken** with `/fluent-speaking voice`: the tutor talks out loud and you answer into your microphone. | **2-3x per week** - Builds confidence for real conversations. Start typed to think through responses without pressure; switch to voice when you want the real thing. |
| **`/fluent-reading`** | **Reading comprehension** - Read short texts (stories, articles, dialogues) then answer comprehension questions. Expands vocabulary in context. | **2-3x per week** - Improves overall understanding. Best for intermediate+ learners. Reading is one of the fastest ways to absorb grammar patterns. |

#### Voice Commands 🔊

These use your speakers and microphone. All audio processing is local (OS text-to-speech + Whisper). Run `/fluent-voice-setup` once to see what's available on your machine.

| Command | What It Does | When & Why to Use It |
|---------|--------------|----------------------|
| **`/fluent-listening`** | **Listening comprehension** - The tutor *speaks* sentences and short dialogues; you type what you heard (dictation), fill a gap, or answer a question. Replay and slow-down controls. Needs only text-to-speech. | **2-3x per week** - The skill most apps skip. Trains sound→meaning directly, surfaces the sounds you can't yet hear. |
| **`/fluent-pronunciation`** | **Repeat-after-me** - Hear a word or sentence, say it into your mic, get a match score and concrete articulation tips for the sounds that drifted. Minimal pairs, sentences, shadowing. Needs TTS + mic + speech-to-text. | **Daily, 10 min** - Pronunciation benefits from day one. Short sessions, immediate feedback. |
| **`/fluent-voice-setup`** | **Audio check** - Detects your text-to-speech, microphone and speech-recognition backends, tells you exactly what to install for your OS, plays a test sentence. | **Once per machine** - Or whenever a voice skill says something is missing. Auto-invokes when you ask "does voice work?". |

#### Progress Command

| Command | What It Does | When & Why to Use It |
|---------|--------------|----------------------|
| **`/fluent-progress`** | **Statistics dashboard** - Shows your accuracy trends, streak days, mastery levels, achievements unlocked, and weak areas. Visual progress charts. | **Weekly check-in** - Read-only and safe to auto-invoke. Ask "how am I doing?" and Claude will open the dashboard automatically. |

### Helper skills (behind the scenes)

These skills don't change what the learner-facing commands do — they let Claude apply the same algorithms, feedback format, and database logic consistently across every session. You can still invoke them via `/` if curious.

| Skill | What It Does | When It Runs |
|-------|--------------|--------------|
| **`/fluent-sm2-calculator`** | SM-2 spaced-repetition algorithm reference: quality scale, interval formula, easiness-factor update, mastery-level transitions. | Auto-loaded whenever a review item is scored. |
| **`/fluent-feedback-formatter`** | Canonical per-answer feedback template — severity tagging (🔴 critical / 🟡 moderate / 🟢 minor), category labels, tone rules. | Auto-loaded every time Claude grades an answer. |
| **`/fluent-db-updater`** | How to call `update-db.py` with a single JSON payload that atomically updates all 6 databases at session end. | Auto-loaded when a session ends. |
| **`/fluent-session-analyzer`** | Parses `/results/fluent-{skill}-session-{ID}.md` files to extract error patterns, strengths, and focus areas for the next session. | Auto-loaded when planning the next session. |

### 📅 Recommended Daily Routine

**🌅 Morning Session (15 min)**
```bash
/fluent-review    # Must do first - Review what you learned before
/fluent-vocab     # Learn 5-10 new words
```
**Why?** Your brain is fresh. Reviewing first reinforces old knowledge, then new vocabulary sticks better.

**🌙 Evening Session (15 min)**
```bash
/fluent-writing   # Practice real-world writing
/fluent-learn     # Let AI choose what you need most
```

**🔊 Voice Days (2-3x per week, 10-15 min)**
```bash
/fluent-pronunciation     # Repeat after me — minimal pairs and sentences
/fluent-listening         # Dictation and comprehension from audio
/fluent-speaking voice    # A real spoken conversation
```

**Why?** Reading and writing don't train your ears or your mouth. Ten minutes of actual sound, a few times a week, is what makes the language usable in person.
**Why?** Writing solidifies what you learned today. `/fluent-learn` fills in any gaps.

**📊 Weekly Check-In (5 min)**
```bash
/fluent-progress  # See your stats and celebrate progress!
```
**Why?** Seeing improvement = motivation. You need to see you're getting better!

---

## 📁 System Architecture

### Data Layer (`/data` directory)

**Your learning data is tracked in 6 JSON databases** (created automatically by `/fluent-setup`):

| File | Purpose | Created When |
|------|---------|--------------|
| `learner-profile.json` | Your info, level, preferences, streak | `/fluent-setup` - One time |
| `progress-db.json` | Overall statistics and trends | `/fluent-setup` - Updated every session |
| `mistakes-db.json` | Error patterns with frequency and examples | `/fluent-setup` - Updated when you make mistakes |
| `mastery-db.json` | Skill mastery levels (0-5 stars) | `/fluent-setup` - Updated after practice |
| `spaced-repetition.json` | Review queue (SM-2 algorithm) | `/fluent-setup` - Updated after each answer |
| `session-log.json` | Complete session history | `/fluent-setup` - New entry each session |

**📋 Want to see the structure?** Check `/data-examples/` for template files showing the complete schema.

**🔒 Privacy:** All data stays on your machine. Automatically excluded from git via `.gitignore`.

### Intelligence Layer

The AI follows these guides:

- **`LEARNING_SYSTEM.md`** - Complete methodology (how to teach)
- **`CLAUDE.md`** - AI tutor's role and personality
- **`PRACTICE.md`** - Pattern analysis and tracking
- **`.claude/references/`** - Shared templates (SM-2 worked examples, feedback template, DB payload schema, session-file format) that every skill references

### Interface Layer

- **Skills** (`.claude/skills/`) — 15 skills total. 11 learner-facing (`/fluent-setup`, `/fluent-learn`, `/fluent-vocab`, `/fluent-writing`, `/fluent-speaking`, `/fluent-reading`, `/fluent-review`, `/fluent-listening`, `/fluent-pronunciation`, `/fluent-voice-setup`, `/fluent-progress`) run when you invoke them. 4 helper skills (`/fluent-sm2-calculator`, `/fluent-feedback-formatter`, `/fluent-db-updater`, `/fluent-session-analyzer`) auto-load whenever Claude needs them during a session — and are also directly `/`-invokable if you want to read the reference.
- **Plugin manifests** (`.claude-plugin/`) — `plugin.json` + `marketplace.json` make Fluent installable via `/plugin marketplace add m98/fluent`.
- **Automatic Hooks** (`.claude/hooks/`) — SessionStart welcome, SessionEnd backups, PostToolUse JSON validation + backups, PreCompact safety backup. Both `hooks.json` (plugin mode) and `.claude/settings.json` (clone mode) wire them up.
- **Session Results** (`/results/`) — Detailed practice logs per session, parsed by `fluent-session-analyzer` to plan future sessions.

---

## 🔊 Voice Features (Local Audio)

Fluent can **speak** and **listen** — entirely on your machine.

| Component | What it does | Backends (first found wins) |
|-----------|--------------|-----------------------------|
| 🔊 Text-to-speech | Reads sentences, dialogues and model pronunciations aloud | **Kokoro** (neural, best quality) → **Piper** (neural, 40+ languages) → OS engine: macOS `say` · Linux `espeak-ng` · Windows SAPI · `pyttsx3` · your own via `FLUENT_TTS_CMD` |
| 🎙️ Microphone | Records your answer, stops when you go quiet | `sounddevice`+`numpy` (pip) · `ffmpeg` · `sox` · `arecord` |
| 📝 Speech-to-text | Transcribes what you said in the target language | `faster-whisper` (pip) · `openai-whisper` · whisper.cpp · your own via `FLUENT_STT_CMD` |
| 👂 Phoneme recognizer *(optional)* | Hears the **sounds** you actually made, for phone-level pronunciation scoring | wav2vec2 (`pip install transformers torch soundfile`) + espeak-ng / `espeakng-loader` for the target IPA |
| ⚡ Voice server | Keeps the models loaded so every sentence after the first is instant | automatic; `voice-server.py status` |

**Setup** (macOS / Linux / Windows):

```bash
pip install faster-whisper sounddevice numpy      # microphone + speech recognition
pip install kokoro soundfile                      # natural voices (en/es/fr/it/pt-BR/hi/ja/zh)
pip install piper-tts                             # natural voices for 40+ other languages (nl, de, ru, pl, sv, tr, ar, …)
pip install espeakng-loader transformers          # phone-level pronunciation scoring (optional, ~1.2 GB model)
# Linux also: sudo apt install espeak-ng ffmpeg
```

Then in Claude Code: `/fluent-voice-setup` → it reports what works and plays a test sentence.

**Which voice you'll hear.** Per sentence, Fluent uses Kokoro if it has a voice for your target language, otherwise Piper, otherwise the operating system's voice. Kokoro is the most natural but covers nine languages and pulls in PyTorch; Piper is light (ONNX, 20-80 MB per voice) and covers most of Europe plus Arabic, Persian, Turkish, Mandarin and Vietnamese. Models download from Hugging Face on first use (`voice-doctor.py --download-voice` pre-fetches them). Without either, you still get the OS engine — fine for dictation, flat for shadowing.

**What each voice skill needs**

| | TTS | Mic | STT |
|---|:---:|:---:|:---:|
| `/fluent-listening` | ✅ | | |
| `/fluent-pronunciation` | ✅ | ✅ | ✅ |
| `/fluent-speaking voice` | ✅ | ✅ | ✅ |

**How pronunciation scoring works.** You hear the model, you repeat it, and `voice-listen.py --expect` scores you two ways:

- **Phone level** (when the optional recognizer is installed): espeak-ng turns the target sentence into IPA (*el perro* → /el pero/), a wav2vec2 phoneme model with **no language model** writes down the sounds you actually produced (/el peɾo/), and the two are aligned phone by phone and attributed to words. The result names the exact confusion — `/r/ → /ɾ/ in perro`, `/aː/ → /ɑ/ in maan` — plus a per-word accuracy, so the tutor can coach articulation instead of guessing.
- **Word level** (always): the Whisper transcript compared word by word. It's the fallback, and it is lenient on purpose: Whisper is a language model and silently corrects *pero* to *perro* when *perro* fits the sentence, which is exactly why it can't be the primary pronunciation signal.

Scores are still a proxy — recognizers make mistakes — so on low confidence the skill asks you to repeat rather than marking you wrong.

**Listening variety.** `voice-say.py --variety` plays each item with a random voice for your language at 0.9-1.1× speed, and `--noise 0.1`…`0.3` mixes in café/street background noise, so your ear doesn't tune to a single synthetic speaker in a silent room. `/fluent-listening` switches these on as you level up or when you type `harder`.

**Speed.** The first neural sentence loads models (3-10 s). After that a small local server keeps Kokoro, Whisper and the phoneme model in memory, and sentences are cached on disk, so the rest of the session plays without pauses. It starts itself on first use and exits after 30 idle minutes.

**Useful environment variables**

| Variable | Purpose |
|----------|---------|
| `FLUENT_WHISPER_MODEL` | `tiny` / `base` / `small` (default) / `medium` / `large-v3` — bigger is more accurate, slower, more RAM |
| `FLUENT_TTS_ENGINE` | `auto` (default) / `kokoro` / `piper` / `system` — force an engine |
| `FLUENT_KOKORO_VOICE` | Kokoro voice id (e.g. `em_alex`, `bf_emma`, `jf_alpha`) |
| `FLUENT_PIPER_VOICE` | Piper voice id (e.g. `nl_BE-nathalie-medium`) or path to a local `.onnx` |
| `FLUENT_PIPER_AUTO_DOWNLOAD` | `0` to never download; place models in `<data_dir>/.voice/models/` yourself |
| `FLUENT_TTS_VOICE` | OS-engine voice name (e.g. `Xander` on macOS for Dutch) |
| `FLUENT_PHONEME_MODEL` | wav2vec2 phoneme model (default `facebook/wav2vec2-xlsr-53-espeak-cv-ft`) |
| `FLUENT_PHONEME_CMD` | Your own phoneme recognizer: prints space-separated IPA for `{file}` |
| `FLUENT_VOICE_SERVER` | `0` to disable the model server; `FLUENT_VOICE_SERVER_IDLE` seconds before it exits (1800) |
| `FLUENT_TTS_CACHE` / `FLUENT_TTS_CACHE_MB` | `0` to disable the sentence cache; size cap in MB (200) |
| `FLUENT_MIC_DEVICE` | Pick a microphone when you have several |
| `FLUENT_TTS_CMD` / `FLUENT_STT_CMD` | Plug in any engine: `{text}`/`{lang}` and `{file}`/`{lang}` placeholders |
| `FLUENT_WHISPER_CPP_MODEL` | Path to a ggml model to use whisper.cpp from PATH |

**Privacy.** Recordings go to `<data_dir>/.voice/` and are deleted right after transcription unless you pass `--keep`. Nothing is uploaded anywhere; the only network access is the one-time model download from Hugging Face (opt out with `FLUENT_PIPER_AUTO_DOWNLOAD=0`).

**Scripts** (all in `.claude/hooks/`, usable on their own):

```bash
python3 .claude/hooks/voice-say.py --lang Dutch "Goedemiddag!"            # speak
python3 .claude/hooks/voice-listen.py --lang Dutch --expect "Goedemiddag"  # record, transcribe, score
python3 .claude/hooks/voice-doctor.py --test                               # diagnose + test sentence
python3 .claude/hooks/voice-say.py --lang Spanish --variety --noise 0.1 "…"  # listening drill: random voice, speed, café noise
python3 .claude/hooks/voice-server.py status                               # which models are loaded
```

---

## 🎯 Learning Principles

### Spaced Repetition (SM-2 Algorithm)

**Example progression for a difficult word:**

```
Day 1:  Make a mistake → Review tomorrow (interval = 1 day)
Day 2:  Answer correctly → Review in 6 days
Day 8:  Correct again → Review in 2 weeks
Day 22: Still remember → Monthly review (mastered!)
```

The system tracks for each item:
- **Easiness Factor** - How easy it is for YOU specifically
- **Interval Days** - When to review next
- **Repetitions** - Practice count
- **Quality Score** - Your performance (0-5)

### Mastery Levels

Every skill and pattern gets a star rating:

- ⭐☆☆☆☆ (1) - Just started
- ⭐⭐☆☆☆ (2) - Learning
- ⭐⭐⭐☆☆ (3) - Good understanding
- ⭐⭐⭐⭐☆ (4) - Strong skill
- ⭐⭐⭐⭐⭐ (5) - Mastered!

### Adaptive Difficulty

The system automatically adjusts:

- **Success rate 40-50%** → Too hard, makes easier
- **Success rate 60-70%** → Perfect challenge! ✨
- **Success rate 80-90%** → Too easy, makes harder

**Goal:** Keep you in the "sweet spot" where learning happens.

---

## 🔬 Technical Details

### Technology Stack

- **Platform:** Claude Code (Anthropic), installable as a plugin or by clone
- **AI Model:** Claude (any Claude Code-supported model)
- **Data Format:** JSON (human-readable)
- **Skills:** Markdown `SKILL.md` files with YAML frontmatter (15 total — 11 learner-facing + 4 helper)
- **Voice:** `.claude/hooks/fluent_voice.py` — local TTS (Kokoro / Piper / `say` / `espeak-ng` / SAPI / `pyttsx3`), mic capture (`sounddevice` / `ffmpeg` / `sox` / `arecord`), STT (`faster-whisper` / `openai-whisper` / whisper.cpp), sentence cache, listening variety. `fluent_phonemes.py` — phone-level pronunciation scoring (espeak-ng G2P + wav2vec2 phoneme recognizer, alignment, per-word attribution). `fluent_server.py` — local model server. Any backend can be swapped via `FLUENT_TTS_CMD` / `FLUENT_STT_CMD` / `FLUENT_PHONEME_CMD`.
- **Hooks:** Python + Bash, triggered on SessionStart / SessionEnd / PostToolUse / PreCompact
- **Algorithm:** SM-2 (SuperMemo 2)
- **Version Control:** Git

### Data Privacy & Security

- ✅ **All data stays local** on your machine
- ✅ **No external API calls** (except Claude Code itself)
- ✅ **Automatic .gitignore** prevents committing personal data
- ✅ **Automatic backups** to `.backups/` directory
- ✅ **No tracking, no analytics, no telemetry**

### Hooks System (Automated Data Management)

Fluent uses intelligent Claude Code hooks to ensure your data is always safe and validated:

**🔄 PostToolUse Hook** (after every Write/Edit)
- ✅ Creates timestamped backup: `data/file.json.backup-20231117-143022`
- ✅ Validates JSON structure automatically
- ✅ Alerts you immediately if data is malformed

**📦 SessionEnd Hook** (when you finish practicing)
- ✅ Creates daily snapshot in `.backups/YYYYMMDD/`
- ✅ Displays session summary with current streak
- ✅ Shows total practice sessions completed

**🌅 SessionStart Hook** (when you begin)
- ✅ Welcome message with your name and stats
- ✅ Shows current language, level, and streak
- ✅ Alerts you if reviews are due today

**🔒 PreCompact Hook** (before compaction)
- ✅ Safety backup to prevent data loss

**You'll never lose your progress.** All backups are automatic and excluded from git.

See [`.claude/hooks/README.md`](.claude/hooks/README.md) for technical details.

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Priority Areas

We're especially interested in:

1. 🌐 **Language-specific optimizations** - Grammar rules, common errors for specific languages
2. 🎵 **Audio features** - More STT backends (Vosk, Parakeet), prosody/stress scoring, Kokoro/Piper voices for more languages, listening with real recordings
3. 📊 **Visual enhancements** - Better progress charts, statistics
4. 📱 **Mobile support** - Companion app or mobile interface
5. ⚡ **Performance** - Optimize data loading, improve speed
6. ♿ **Accessibility** - Make system more accessible
7. 🧪 **Testing** - Add comprehensive test coverage

### How to Contribute

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Test thoroughly
5. Commit with clear messages
6. Push and open a Pull Request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.


---

## 🙏 Acknowledgments

- **Claude** by Anthropic - For the amazing AI capabilities
- **SuperMemo** - For the SM-2 algorithm
- **Anki** - For inspiring the flashcard approach
- **Language learning research** - Krashen, Bjork, Ebbinghaus, and many others
- **Open-source community** - For making this possible

---

## 📞 Support & Community

- 📖 **Documentation:** [Full docs in this repo](docs/)
- 🐛 **Bug Reports & Questions:** [GitHub Issues](https://github.com/m98/fluent/issues)
- 📧 **Email:** For sensitive issues

---

## 🌟 Star This Project!

If this system helps you learn a language, please **star the repository** ⭐

It helps others discover this project and motivates us to keep improving it!

---

## 📈 Project Stats

- **Skills:** 15 (11 learner-facing + 4 helper)
- **Hooks:** 5 automated (SessionStart, SessionEnd, PostToolUse, PreCompact, DB helpers)
- **Databases:** 6 JSON tracking files
- **Install paths:** 2 (Claude Code plugin + git clone — both supported)
- **Languages Supported:** All (system is fully language-agnostic)
- **Learning Methods:** 6 evidence-based principles
- **Contributors:** [See contributors](https://github.com/m98/fluent/graphs/contributors)

---

## 🎓 Success Stories

*Want to share your language learning success? Open a PR to add your story here!*

---

## 🛠️ Troubleshooting

**`python3: command not found` when hooks run.**
Install Python 3.8+ and make sure `python3` is on your PATH. On macOS: `brew install python3`. On Debian/Ubuntu: `sudo apt install python3`. On Windows: install via [python.org](https://www.python.org/downloads/) or use WSL.

**Hooks silently do nothing on Windows.**
The PreCompact hook is a Bash script. Run Claude Code from WSL or Git Bash. The Python hooks (SessionStart, SessionEnd, PostToolUse) work on native Windows Python — only PreCompact is Bash-only.

**Learner data is showing up in the wrong place.**
Check the data-dir resolution order (see above). Set `FLUENT_DATA_DIR` explicitly in your shell to force a specific location.

**JSON validation fails after a manual edit.**
The PostToolUse hook exits with status 2 if it finds malformed JSON. The last 10 backups live at `<data_dir>/<filename>.json.backup-<timestamp>`. Restore with: `cp <data_dir>/learner-profile.json.backup-XXXXXX <data_dir>/learner-profile.json`.

**Skills don't appear in the `/` menu after plugin install.**
Restart Claude Code. If still missing, verify install:

```bash
claude plugin list                              # should show fluent@m98 enabled
claude plugin validate fluent@m98
```

Or from inside a session: `/plugin list`. If the plugin is disabled, enable it: `claude plugin enable fluent@m98`.

---

## 🔗 Useful Links

- [Claude Code Documentation](https://code.claude.com/docs)
- [Claude Code Plugins](https://code.claude.com/docs/en/plugins)
- [SM-2 Algorithm Explained](https://www.supermemo.com/en/archives1990-2015/english/ol/sm2)
- [CEFR Levels](https://www.coe.int/en/web/common-european-framework-reference-languages/level-descriptions)
- [Spaced Repetition Research](https://www.gwern.net/Spaced-repetition)
- [Active Recall Benefits](https://en.wikipedia.org/wiki/Testing_effect)

---

## ❓ FAQ

**Q: How is this different from Duolingo/Babbel/etc?**
A: It’s ultra-minimalistic, just a terminal and pure learning. No extra distributions, no ads, no gimmicks. Infinitely adaptable. You ask it to teach you something, and it does. And best of all, everything stays private on your machine.

**Q: Do I need to know how to code?**
A: No! Just install Claude Code and run `/fluent-setup`. That's it.

**Q: How long until I see progress?**
A: Most learners see measurable improvement within the first week. The system tracks everything so you can see exactly how you're improving.

**Q: Can I use this for exam preparation?**
A: Yes! The system adapts to your goals. Tell it you're preparing for DELE/DELF/TestDaF/etc. and it'll focus on exam-relevant content.

**Q: Is my data safe?**
A: Absolutely. Everything stays on your machine. No cloud storage, no external servers (except Claude Code itself).

**Q: Can I export my progress?**
A: Yes! All data is in human-readable JSON. You can export, analyze, or migrate it anytime.

**Q: Can I use Open AI's Codex CLI  or Gemini CLI instead of Claude Code?**
A: We have AGENTS.md for instructing other AI CLIs as well, but this kit is specifically optimized for 
Claude Code and its unique capabilities. Using other AI platforms may not yield the same results. 
But feel free to experiment and share your findings!


---

*Start your language learning journey today!* 🚀

```bash
git clone https://github.com/m98/fluent.git
cd fluent
claude
/fluent-setup
```
