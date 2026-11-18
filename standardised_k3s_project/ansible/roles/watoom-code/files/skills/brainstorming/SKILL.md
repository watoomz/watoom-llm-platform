---
name: brainstorming
description: Use before building something new or changing behaviour when the request leaves something important open. Find out what the operator actually wants and why, agree an approach, write a short design, and get it approved before building. Skip it when the request is already complete and clear.
---

# Brainstorming

Your picture of what the operator wants is usually thinner than it feels. This skill finds out what they want, and why, before anything is built. When you know the why, you make the many unmentioned decisions the way they would.

## First: what do you actually know?

- **Everything that matters is in the request** (an exact change, a full spec, a detailed pipeline prompt): this skill is not needed. Do the work and say what you did.
- **Something non-trivial is missing**, or the request is open-ended: continue below.
- **Automated or pipeline prompts** that already carry a reviewed spec and scope: do not interrupt them with questions. Follow the spec; list any ambiguity as a note in your progress file.

## Look before you ask

Read what the request refers to and the code or material around it first, until you can say how the relevant parts work today and what the change would touch. Never ask what the project already answers or reopen what is decided.

## First message

About 200 words: restate the request in your own words (what, for whom, why as far as stated), add what you found that bears on it (how it works today, what it would touch), and flag anything that may change what they ask for, such as a constraint, a conflict or a cheaper path. End with one line inviting corrections.

Then one question, only if the answer would change what gets built:
- If you do not know **why** they want it, ask that, open-ended, with no example answers.
- Otherwise ask the single most decisive open point; when choices can be named, sketch each with its trade-off and say which you would pick.
- If nothing is open, give the short design and ask for approval.

If they did not ask for a discussion, add one line: "Or if you'd rather I just get going, say so."

## The conversation

- Ask only when the answer changes the result. Otherwise state your call and reason as a proposal they can correct, and move on.
- One question at a time, specific to their project, building on their last answer. Plain language, their vocabulary.
- Process choices (where files go, what to read next) are yours: do them and say so.
- Play back what you understand in short chunks (about 200 words), separate what they said from what you filled in, and ask what is wrong or missing.
- **Lay out the approaches** in a message of its own once you understand the goal: two or three real alternatives, what each trades off, your recommendation. They choose (or hand the choice to you).
- Where seeing helps, sketch layouts or flows in text.
- A quick throwaway spike is allowed if they agree; it stays labelled throwaway, and keeping it is a new request through this gate.

## Size and write the design

Small change: a short design (intent, the chosen approach and why, what changes). A project: the fuller one, covering intent and why, goals, non-goals and anti-goals, constraints, approaches considered and the pick, the decisions they made, and what is left to the builder.
Save it with your task notes (for example `.opencode/work/<task>/design.md`) unless they say otherwise. Re-read it as a builder who has not seen this conversation: list anything you could not build from it and fix or ask.

## Gate

Do not build (no product code, scaffolding or installs) until the operator approves the design. Reading and exploring are fine. After approval, use `writing-plans`.

## Stop signs

Offering a menu before asking them to describe it; filling defaults silently; writing the design before laying out approaches; treating "sounds good" as approval of a design they have not seen; building on a spike without a new go-ahead.

Ported and condensed from obra/superpowers (MIT), see `superpowers-LICENSE`. The browser "visual companion" and the subagent builder-check were not ported.
