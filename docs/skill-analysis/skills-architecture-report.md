# GenericAgent Skill Architecture Analysis

## Executive Summary

GenericAgent **does not programmatically discover, load, or invoke skills** from the `skills/` directory. There is no skill registry, no dynamic loader, and no dedicated skill invocation API in the core codebase. The seven skill directories are essentially **standalone documentation-and-script bundles** that the agent (or the LLM driving it) uses in an ad-hoc, manual way.

---

## 1. Where Skill Loading Code Is *Not* Found

I searched the main codebase for any reference to `skills/`, `SKILL.md`, skill loading, registries, or invocation:

| File | Skill-related code? |
|---|---|
| `agent_loop.py` | None |
| `agentmain.py` | None |
| `llmcore.py` | None |
| `ga.py` | None |
| `plugins/*.py` | None |
| `assets/sys_prompt.txt` | None |
| `frontends/tui_v3.py` | Only UI strings: `/morphling` tip and help text (lines 99, 156, 202) |

**Conclusion:** The runtime has no built-in awareness of the `skills/` folder.

---

## 2. What the Skill Lifecycle Actually Is

Because there is no loader, the lifecycle is **manual / prompt-driven**:

1. **Discovery** — done by the agent on demand, usually via `ls skills/` through the `code_run`/`bash` tool, or by reading `memory/global_mem_insight.txt` where the user has manually recorded skill facts.
2. **Selection** — driven by the LLM. Each `SKILL.md` has YAML frontmatter with `name` and `description`. The LLM uses these descriptions (when the file is read) to decide whether a skill matches the user request.
3. **Loading** — the agent reads `SKILL.md` explicitly using file-read tools, exactly like reading any other document.
4. **Invocation** — the agent executes the skill's scripts directly via `code_run` or `bash`, e.g.:
   ```bash
   python3 skills/conversation_html_exporter/exporter.py ...
   skills/meeting-audio-local-workflow/run_meeting_workflow.sh ...
   ```

This matches the project's stated philosophy in `README.md` line 38:

> Design philosophy — **don't preload skills, evolve them.**

In other words, skills are **evolved, stored, and recalled as files**, not registered objects.

---

## 3. Concrete File Paths and Line Numbers

| Path | Observation |
|---|---|
| `agent_loop.py:18-29` | Tool dispatch via `do_{tool_name}` — no skill hooks |
| `agentmain.py:12-13` | Only plugin hook loader: `plugins.hooks.discover_and_load()` |
| `ga.py:16-97` | `code_run()` executor — skills run through this generic runner |
| `plugins/hooks.py` | No skill references |
| `frontends/tui_v3.py:99,156,202` | `/morphling` help text only |
| `memory/skill_search/skill_search/__pycache__/engine.cpython-312.pyc` | Compiled remote skill-search API client; no local skill loader |
| `README.md:38` | "don't preload skills, evolve them" |
| `docs/GETTING_STARTED.md:281-290` | Describes skill evolution and reuse, but no code mechanism |
| `skills/*/SKILL.md` | Each skill's entry point (manual-read markdown) |

---

## 4. Status of the 7 Skills

| Skill | Git status | Assessment |
|---|---|---|
| `AI-Search-Hub` | Tracked as submodule, modified (`m`) | Active; full Playwright scripts, own `.venv`, `ROUTING.md` |
| `conversation_html_exporter` | Tracked | Active; has `exporter.py`, examples, and outputs |
| `js-reverse` | Tracked | Active; MCP-based workflow with `agents/openai.yaml` and references |
| `Web-Clipper-Conversation-Archive` | Tracked (only `SKILL.md`) | Lightweight; active when user asks to archive conversations |
| `DeepSearch` | **Untracked** (`??`) | Active but uncommitted; has `DeepSearch_SOP.md`, `scripts/`, `.env` |
| `arcane-api-management` | **Untracked** (`??`) | Draft; only `SKILL.md` + `arcane_api.py` |
| `meeting-audio-local-workflow` | **Untracked** (`??`) | Draft/early; `SKILL.md` + shell script + MLX summarizer |

**Active (4):** `AI-Search-Hub`, `conversation_html_exporter`, `js-reverse`, `DeepSearch`  
**Lightweight / intent-only (1):** `Web-Clipper-Conversation-Archive`  
**Dormant drafts (2):** `arcane-api-management`, `meeting-audio-local-workflow`

---

## 5. Why "Codex Sees So Many Skills"

There is no runtime deduplication or pruning. Because GenericAgent's model is **"evolve skills into the folder"**, every completed workflow the user chose to persist becomes a new `skills/<name>/SKILL.md`. The agent does not:

- enumerate them at startup,
- score redundancy,
- disable unused ones, or
- garbage-collect drafts.

The only "registry" is the filesystem itself. The large number is therefore a side effect of the design: the folder is a **personal capability notebook**, not a managed plugin system.

---

## Recommendation

If the goal is to reduce perceived bloat, consider adding a lightweight skill manager in `agentmain.py` or a new `skills/__index__.py` that:

1. enumerates `skills/*/` at startup,
2. parses each `SKILL.md` frontmatter,
3. injects a condensed skill catalog into the system prompt,
4. marks draft/untracked skills separately.

Until then, the architecture remains **manual, filesystem-based, and LLM-prompt-driven**.
