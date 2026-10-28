---
name: fluent-speaking
description: Run an interactive conversation session — free-flowing dialogue, role-plays, and opinion questions prioritizing communication over perfect grammar. Typed by default; `/fluent-speaking voice` makes it spoken — the tutor's lines are played with local text-to-speech and the learner answers into the microphone (transcribed locally with Whisper). Triggered when the learner types /fluent-speaking or picks it from the /fluent-learn menu. Asks questions one at a time in the target language, evaluates clarity and naturalness first and grammar second, and updates all databases at the end.
allowed-tools: Read, Write, Bash
---

# Speaking Practice (Typed or Voice)

## Overview

Conversational practice. Unlike `/fluent-writing`, prioritize **communication and naturalness** — grammar errors that don't block meaning are downplayed. Goal: build the learner's confidence to produce target-language output without over-analyzing.

Two modes:

- **Typed** (default) — the learner types their replies. Works everywhere.
- **Voice** (`/fluent-speaking voice`, or `preferences.voice: true` in the profile) — every tutor line is **spoken aloud** with the local TTS backend and the learner **answers into the microphone**; the reply is transcribed locally and evaluated like a typed one, plus a light pronunciation note when the transcript shows a sound drifted. This is the closest Fluent gets to a real conversation.

## When to Use

Trigger this skill when the learner types `/fluent-speaking` (optionally followed by `voice` or `typed`), picks it from the `/fluent-learn` menu, or explicitly asks to start this practice. Never start it from an ambiguous message — a 15-20 min interactive session that writes 6 databases must be what the learner asked for.

Skip this skill below A1 mastery 2 — the learner needs a basic word bank and verb conjugations first (run `/fluent-vocab` a few times).

## Instructions

### 1. Load context

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/read-db.py"
```

Need: `learner-profile` (level, target language, `preferences.voice`), `mastery-db.skills_mastery.speaking`.

### 1b. Decide the mode

Mode = `voice` if the learner typed `/fluent-speaking voice`, or the profile has `preferences.voice: true` and they didn't type `typed`. Otherwise `typed`.

In voice mode, check the audio stack first:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-doctor.py" --json
```

- All three checks ok → voice mode.
- Only `tts` ok → offer **half-voice**: Claude speaks, learner types. Ask which they prefer.
- `tts` missing → say what's missing in one line, offer `/fluent-voice-setup`, and ask whether to continue typed. Don't silently downgrade.

**Voice-mode turn mechanics** (used in steps 4 and 6 below):

Speak every target-language line you produce, right after printing it:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-say.py" --quiet --lang "{target_language}" "{line}"
```

Then record the learner's reply instead of waiting for typed input:

```bash
python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_PROJECT_DIR:-.}}/.claude/hooks/voice-listen.py" --lang "{target_language}" --max-seconds 30 --prompt "{names, places and key vocabulary of the current topic, comma-separated}"
```

`--prompt` biases Whisper toward the words it is likely to hear (the learner's name, the city in the role-play, the vocabulary you just introduced) and cuts transcription errors a lot in conversation. It is right here and wrong in `/fluent-pronunciation`. Use `transcript` as "their answer". Run `voice-server.py start` once at the opening so each turn doesn't reload the models. Show it back verbatim in the feedback (`**What I heard:**`) so a mis-transcription is visible and the learner can say `again`. Controls in voice mode: `again` (re-record), `type` (answer this one by keyboard), `replay`, `typed` (switch mode for the rest of the session). The learner can always type instead of speaking — if typed text arrives, use it.

Voice-mode error handling: a recording error → run the doctor, hand off to `/fluent-voice-setup`; empty transcript or `recording.seconds < 0.4` → "Didn't catch that — say `again`"; `confidence < 0.4` → ask them to repeat once before evaluating.

### 2. Opening

```markdown
# 🗣️ {target_language} Speaking Practice

Hallo {name}!

Today we're practicing **speaking** {through typed conversation | out loud — I'll talk, you answer into your microphone}. I'll ask you questions or give scenarios, you respond naturally in {target_language} — just like a real conversation.

**Focus:** natural expression, fluency{, pronunciation (voice mode)}
**Level:** {CEFR}
**Duration:** 15-20 min
{Voice mode: **Controls:** `again` · `type` · `replay` · `typed`}

**Tips:**
- Think in {target_language}, not {native_language}
- Don't chase perfect grammar — focus on getting your message across
- Use complete sentences
- Be natural and conversational

**Ready? Let's chat!** 💬
```

### 3. Pick topic based on mastery

A2 topics:
1. Personal introductions
2. Daily routine
3. Hobbies and interests
4. Shopping
5. Making appointments
6. Asking for directions
7. Ordering food
8. Talking about weather
9. Weekend plans
10. Work / study

B1+: opinions, comparisons, hypotheticals, complaints, narratives.

### 4. One question at a time

```markdown
## Question {N}: {Topic}

{Question in target language}

**{Type your answer in {target_language}: | 🎙️ Answer out loud:}**
```

In voice mode, speak the question (`voice-say.py`) right after printing it, then run `voice-listen.py` and treat the transcript as the answer.

Build the conversation naturally — after 3-4 Qs on one topic, transition: `Interessant! Let's talk about something else...`.

### 5. Evaluate

Check in this order:

1. **Communication** (most important, 0-5 points): was the message clear? Did it answer the question?
2. **Grammar** (0-3 points): verb conjugation, word order, articles. Note but don't belabor.
3. **Vocabulary** (0-2 points): appropriate word choice, no English mixing.

Voice mode only — add a **pronunciation note** (not scored) when the transcript contains a word that is clearly a near-miss of what they meant (e.g. *pero* for *perro*, *man* for *maan*): one line naming the sound. Skip it when the transcript is plausible as-is; recognizer errors are not the learner's fault. Hesitation markers and self-corrections in the transcript are fluency data, not errors.

Feedback template (variant of `fluent-feedback-formatter`):

```markdown
{✅ or 🟡} {one-line encouragement}

**What {you said | I heard}:**
"{their_answer}"
{Voice mode, if applicable: **Pronunciation note:** *{heard}* for **{meant}** — {sound tip}}

**Communication:** {Clear / Mostly clear / Unclear} ✅

**Grammar notes:** (secondary — don't over-focus)
- {major error → correction, only if communication-blocking}

**Natural alternative:**
You could also say: "{more_natural_phrasing}"

**Score: {X}/10**
- Communication: {Y}/5
- Grammar: {Z}/3
- Vocabulary: {W}/2

{encouragement}

---
```

### 6. Role-play (advanced)

For B1+ or when the learner is warmed up:

```markdown
## 🎭 Role-Play

**Scenario:** {description in native language}
**Your role:** {what the learner plays}
**I'll be:** {what Claude plays}

Ready? I'll start...

---

{first line in target language}

**Your turn:**
```

In voice mode, role-plays are the highlight — speak each of your lines, record each of theirs, and keep the exchanges short (one or two sentences per turn) so the rhythm stays conversational.

### 7. Session summary

```markdown
## 🎉 Speaking Session Complete!

**Duration:** {X} min
**Questions Answered:** {N}
**Topics Covered:** {list}

### Communication Scores
**Overall:** {percent}%
- Clear messages: {count}
- Natural expression: {rating}/5
- Confidence: Growing! 💪

### Vocabulary Used Well
- {words}

### For Next Time
- Try using: {new phrase}
- Practice: {weak area}

**{target-language well done}!** 🌟
```

### 8. Update all databases

Use the `fluent-db-updater` skill:

- `command_used: "/fluent-speaking"` (or `"/fluent-speaking voice"`), `skills_practiced: ["speaking"]` — add `"pronunciation"` in voice mode when at least one pronunciation note was given
- `skill_scores.speaking: {exercises: N, correct: count_of_clear_answers, time_minutes}`
- Voice mode: `skill_scores.pronunciation: {exercises: turns, correct: turns_without_a_note, time_minutes: 0}`
- `errors[]` — only communication-blocking ones (don't flood mistakes-db with minor speaking slips); voice-mode pronunciation notes go in with category `pronunciation`
- `focus_next_session[]` — one topic + one pattern

Save exchange to `/results/fluent-speaking-session-{NNN}.md` (note the mode in the header; in voice mode store the transcripts, not audio — recordings are deleted after transcription).

## Examples

### Example 1 — personal intro (Dutch A2)

> ## Question 1: Introductions
>
> Vertel me over jezelf. Waar kom je vandaan?
> (Tell me about yourself. Where are you from?)

Learner: "Ik ben Mohammad. Ik kom van Iran maar ik woon nu in Nederland."

> ✅ Clear and natural!
>
> **What you said:** "Ik ben Mohammad. Ik kom van Iran maar ik woon nu in Nederland."
>
> **Communication:** Clear ✅
>
> **Grammar notes:**
> - 🟢 "van Iran" → **"uit Iran"** (prepositions — origin uses `uit`, not `van`). Small slip; message still crystal clear.
>
> **Natural alternative:**
> "Ik kom uit Iran, maar ik woon al een paar jaar in Nederland."
>
> **Score: 9/10**
> - Communication: 5/5
> - Grammar: 2/3
> - Vocabulary: 2/2
>
> Great start — you packed two ideas into one sentence, which is exactly what fluency looks like.

### Example 2 — role-play opener (café scenario)

> ## 🎭 Role-Play
>
> **Scenario:** You're at a café in Amsterdam. You want coffee and a vegetarian option for lunch.
> **Your role:** Customer
> **I'll be:** The server
>
> ---
>
> *"Goedemiddag! Wat wilt u drinken?"*
>
> **Your turn:**

## Critical Rules

- **Communication first.** A clear message with a missed article scores better than a grammatically perfect but confusing answer.
- **One question at a time.** Wait for reply before next.
- **Stay in the target language** for questions and transitions. Drop to native only for explanations.
- **Praise natural expression.** If the learner uses "Nou..." or "Eh..." correctly, call it out — those are fluency markers.
- **Don't over-correct.** A speaking session with 20 red marks kills confidence.
- **Voice mode: show the transcript, trust the learner over the recognizer.** If they say the transcript is wrong, take their word and re-record or let them type.
- **Voice mode: speak every target-language line you print.** Half-spoken sessions feel broken.
- **Start only on request.** Slash command, `/fluent-learn` menu pick, or an explicit ask — never from an ambiguous message.

## Language Reference

### Dutch A2 conversational fillers

- "Nou..." (well / so)
- "Eh..." (uh / um)
- "Eigenlijk..." (actually)
- "Dus..." (so / therefore)
- "Ja, dat klopt" (yes, that's right)
- "Ik snap het niet" (I don't understand)

Add equivalents for other target languages as needed.
