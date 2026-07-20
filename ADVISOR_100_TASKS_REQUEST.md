# Prompt for Advisor Amazon-Q — produce the task breakdown as a Markdown file

Advisor Amazon-Q has **no ClickUp access**, so ask it to output a single, strictly-formatted Markdown file that Claude can import and distribute to the Kiro queues. Copy the block below to Advisor (swap `[RELEASE]` for the one you want first — recommend **New Architecture**).

---

> I need you to break **[RELEASE]** down into well-scoped, independently executable tasks and output them as **one Markdown file** — no ClickUp access needed, Claude will import them.
>
> Output a single Markdown **table**, one row per task, with EXACTLY these columns:
>
> `| # | Release | Track | Owner | Task name | Description (inputs → work → outputs) | Acceptance criteria | Priority | Depends on (#) | Est. effort | Target week |`
>
> Rules:
> - **Release** ∈ {Beta, Storied, Subscribed, New Architecture}. **Track** ∈ {Development, Marketing, Revenue}. **Owner** ∈ {Services, Mobile, Michael, Claude}.
> - Each task must be **contained**: doable end-to-end without waiting on a human decision mid-task, with a **clear, verifiable acceptance criterion**.
> - **Depends on (#):** reference prerequisite rows by their number — this is how Claude wires ClickUp dependencies. Leave blank if none.
> - Routing: backend / tour-generation → **Services**; app/UI → **Mobile**; decisions, store console, legal/pricing → **Michael**; code review → **Claude**. (Expect most Development tasks to be Services.)
> - Do **NOT** include anything that modifies the frozen Beta pipeline. Mark any Storied content task as "gated on POC".
> - **Start with ONE batch of ~20 tasks** so we validate the format before you generate the rest.
> - Output **only** the Markdown table (plus a one-line title). No prose around it.

---

When Advisor returns the file, save it (e.g. `ADVISOR_TASKS_[release].md`) and tell Claude: *"Import the tasks in ADVISOR_TASKS_[release].md."* Claude will create them in the right space/queue, set priorities + target dates, and wire the dependencies.
