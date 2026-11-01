Research notes for the "do it yourself" part of a beginner harness-engineering tutorial: building a tiny Python coding-agent harness step by step. Current as of 2026-10-25. Items marked **[skill-local]** come from Anthropic's bundled `claude-api` reference skill on this machine (cached 2026-10-06), not from a fetched URL; items marked **[unverified]** come from search snippets only.

### Q1. Current Anthropic Python SDK shape for tool use (manual loop, tool runner, model ids)

**Takeaway**
The shape is unchanged in essentials: `client.messages.create(model=..., max_tokens=..., tools=[{name, description, input_schema}], messages=[...])`; the response has `stop_reason == "tool_use"` and `tool_use` blocks (`id`, `name`, `input`); you append the assistant content verbatim, then a `user` message whose content is a list of `tool_result` blocks (`tool_use_id`, `content`, optional `is_error`), and loop. The SDK's beta tool runner (`@beta_tool` + `client.beta.messages.tool_runner(...).until_done()`, `max_iterations=`) removes the loop. Current model ids are exactly `claude-opus-5-5` (recommended default), `claude-fable-5-1`, `claude-sonnet-5-5`, `claude-haiku-5-5`, all 1M context / 128K output, no date suffixes.

**Cited Findings**

Model ids and prices (official docs):
- Docs say "start with Claude Opus 5.5 for most workloads" and use Claude Fable 5.1 "for demanding reasoning and long-horizon agentic work". Claude API ids: `claude-fable-5-1`, `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-haiku-5-5`. Prices per MTok in/out: Fable 5.1 $10/$50; Opus 5.5 $4/$20; Sonnet 5.5 $2/$10; Haiku 5.5 from $0.10/$0.50. All: 1M-token context window, 128K max output, knowledge cutoff Jun 2026. Default effort: Fable 5.1 `high`, Opus 5.5 `medium`, Sonnet 5.5 `high`, Haiku 5.5 `medium`. Thinking: "Adaptive (always on)" for Fable 5.1 and Opus 5.5; "Adaptive" for Sonnet 5.5 / Haiku 5.5. — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- "Every Claude model ID is a pinned snapshot, including the dateless IDs used from the 4.6 generation on." Cache reads cost 10% of base input price (2.5% on Fable 5.1, 5% on Opus 5.5 and Sonnet 5.5); Batch API is 50% off. Legacy still-available models include `claude-sonnet-5`, `claude-opus-5`, `claude-opus-4-8`, `claude-haiku-4-5`. — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- The Models API returns `max_input_tokens`, `max_tokens`, and a `capabilities` object (e.g. `thinking.types.disabled.supported`) per model; use `client.models.list()` / `client.models.retrieve(id)`. — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- **[skill-local]** Harness-relevant model gotchas: on Opus 5.5 `thinking: {type: "disabled"}` and `budget_tokens` return 400 (use `output_config: {effort: ...}`); on Fable 5.1 / Opus 5.5 / Sonnet 5.5 forced `tool_choice` `{type: "any"}` / `{type: "tool"}` return 400 (use `auto` + prompt instruction, or `strict: true`); assistant prefill returns 400 on all 4.6+ models; always parse `tool_use.input` with `json.loads`-style access rather than string-matching serialized JSON. — bundled `claude-api` skill, SKILL.md (cached 2026-10-06); public page for the same material: [Migration guide](https://platform.claude.com/docs/en/about-claude/models/migration-guide)

Wire format (official docs):
- Tool definition fields are `name`, `description`, `input_schema` (JSON Schema). Minimal client-tool round trip in Python: `response = client.messages.create(model="claude-opus-5-5", max_tokens=1024, tools=tools, tool_choice={"type": "auto", "disable_parallel_tool_use": True}, messages=messages)`; `tool_use = next(b for b in response.content if b.type == "tool_use")`; then `messages += [{"role": "assistant", "content": response.content}, {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tool_use.id, "content": weather}]}]`. — [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- Client tools: "Claude responds with `stop_reason: "tool_use"` and one or more `tool_use` blocks. Your code runs the operation and sends back a `tool_result`." Adding `strict: true` to a custom tool guarantees calls match the schema exactly. — [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- Tool-use system prompt overhead: 286 tokens for Opus 5.5 / Sonnet 5.5 / Haiku 5.5 with `tool_choice` auto/none. — [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- `tool_use` block fields: `id`, `name`, `input`. `tool_result` fields: `tool_use_id`, `content` (string, or list of `text`/`image`/`document`/`search_result` blocks), `is_error` (optional bool). "Tool result blocks must immediately follow their corresponding tool use blocks"; "the `tool_result` blocks must come FIRST in the content array. Any text must come AFTER all tool results" (text before causes a 400). Error string to look for: "tool_use ids were found without tool_result blocks immediately after". — [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- Error signalling: return the error message in `content` with `"is_error": true`; "Write instructive error messages ... include what went wrong and what Claude should try next". For invalid/missing parameters, "Claude will retry 2–3 times with corrections before apologizing to the user." Tool results are untrusted content; keep them inside `tool_result` blocks rather than `system` or user `text` (indirect prompt injection). — [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- Anthropic's own 5-ring tutorial: Ring 1 single call; Ring 2 `while response.stop_reason == "tool_use":` loop; Ring 3 multiple tools + parallel calls (all `tool_result`s in one user message, `tool_choice` omitted so parallel is allowed); Ring 4 `try/except` around the tool, appending `{"type": "tool_result", "tool_use_id": block.id, "content": str(exc), "is_error": True}`; Ring 5 the tool runner (`@beta_tool` functions, `client.beta.messages.tool_runner(...).until_done()`), "roughly half the lines, no manual loop". Note: Rings 2–4 use a bare `while` with no iteration cap and `max_tokens=1024`. — [Tutorial: Build a tool-using agent](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent)

Stop reasons and loop guards (official docs):
- `stop_reason` values: `end_turn`, `max_tokens`, `stop_sequence`, `tool_use`, `pause_turn` (server-tool loop hit its iteration limit, default 10 — append assistant content and call again), `refusal` (HTTP 200; read `stop_details`), `model_context_window_exceeded`. If `max_tokens` is hit mid tool call, "the final block may be a truncated `tool_use`. Detect it and retry with a higher limit" (`response.content[-1].type == "tool_use"`). After tool results Claude sometimes returns empty `end_turn`; don't add text immediately after `tool_result`s and don't resend unchanged. — [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)
- Reference loop with caps from the same page: `MAX_STEPS = 20`, `MAX_CONTINUATIONS = 5`, `for _ in range(MAX_STEPS): ... match response.stop_reason: case "end_turn": return response; case "tool_use": ... messages.append({"role": "assistant", "content": response.content}); messages.append({"role": "user", "content": results}); case "pause_turn": ...; case "max_tokens" | "model_context_window_exceeded": raise ...; case "refusal": raise ...` and finally `raise RuntimeError(f"Agent exceeded {MAX_STEPS} steps without finishing")`. — [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)

Tool runner (official docs + SDK repo):
- `@beta_tool` builds the JSON schema from the function signature and docstring (`additionalProperties: false`, typed required params); async variant `@beta_async_tool`. `client.beta.messages.tool_runner(...)` returns a `BetaToolRunner` iterator yielding one `BetaMessage` per API call; on `tool_use` it runs tools and sends results back; on `pause_turn` or `compaction` it resends the turn; on any other stop reason it yields and stops. `runner.until_done()` resumes and returns the final message; `runner.close()` ends it; `thread=False` sends full history each request (required if `system`/`tools` change during a run). `ToolError` (`from anthropic.lib.tools import ToolError`) returns intentional error content without logging; a plain exception's `repr()` goes to the model as a text error. `stream=True` + `run_tools_eagerly=True` runs each tool as soon as its call finishes; `runner.defer_tool_call(block)` holds a call for approval. `compact_before_next_turn()` needs `betas=["compact-2026-09-04"]`; `add_tools()`/`remove_tools()` need `betas=["inline-tools-2026-09-15"]`. — [anthropic-sdk-python tools.md](https://github.com/anthropics/anthropic-sdk-python/blob/main/tools.md)
- "The runner loops until Claude returns a message without a tool use, or until it reaches `max_iterations` ... if you set it"; `max_iterations` exists in all seven SDKs. Per-turn control: inside `for message in runner:` call `runner.generate_tool_call_response()` to inspect/compute the tool result; `runner.append_messages()` means you own history; `runner.set_messages_params(lambda params: {**params, "max_tokens": 2048})` changes request params. "When a tool throws an exception, the tool runner catches it and returns the error to Claude as a tool result with `is_error: true`" carrying "its type and message, not the full stack trace." You can set `block["cache_control"] = {"type": "ephemeral"}` on a tool result before it is sent. The docs recommend the manual loop "when you need human-in-the-loop approval, custom logging, or conditional execution." — [Tool runner (SDK)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner)
- **[skill-local]** The Python runner (as of `anthropic` 0.116.0) does not auto-resume `pause_turn` from server tools; mirror history and restart the runner. Python SDK requires Python 3.10+. — bundled `claude-api` skill, `python/claude-api/tool-use.md`; [SDK README](https://github.com/anthropics/anthropic-sdk-python)
- Bundled SDK README basic call uses `model="claude-opus-5-5"`; the SDK emits one OpenTelemetry span per API call when a tracer provider is registered (`open_telemetry` client option). — [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python)
- **[skill-local]** Client defaults: `timeout` 10 minutes, `max_retries` 2 (retries 408/409/429/5xx and connection errors); per-request override `client.with_options(timeout=5.0).messages.create(...)`. — bundled `claude-api` skill, SKILL.md

Anthropic-defined file tools (official docs):
- Text editor tool is declared schema-less as `{"type": "text_editor_20250728", "name": "str_replace_based_edit_tool"}` with optional `max_characters` (truncation when viewing large files; only on `text_editor_20250728` and later). Commands: `view`, `create`, `str_replace`, `insert`. For `str_replace`: `old_str` "must match exactly, including whitespace and indentation", `new_str` replaces it. — [Text editor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool)
- **[skill-local]** Bash tool is `{"type": "bash_20250124", "name": "bash"}`; a custom tool with your own schema named "bash" is a different tool. — bundled `claude-api` skill; public page: [Bash tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/bash-tool)

Minimal manual loop (assembled from the official snippets above; Python):
```python
import anthropic, json
client = anthropic.Anthropic()
MAX_STEPS = 30

def run(task, tools, dispatch, system):
    messages = [{"role": "user", "content": task}]
    for _ in range(MAX_STEPS):
        r = client.messages.create(model="claude-opus-5-5", max_tokens=16000,
                                   system=system, tools=tools, messages=messages)
        if r.stop_reason == "end_turn":
            return r
        if r.stop_reason == "max_tokens" and r.content and r.content[-1].type == "tool_use":
            continue  # truncated call: retry with higher max_tokens (per docs)
        if r.stop_reason != "tool_use":
            raise RuntimeError(f"stop_reason={r.stop_reason} details={r.stop_details}")
        results = []
        for b in r.content:
            if b.type != "tool_use":
                continue
            try:
                out = dispatch(b.name, b.input)            # b.input is already a dict
                results.append({"type": "tool_result", "tool_use_id": b.id, "content": out})
            except Exception as e:
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": f"{type(e).__name__}: {e}", "is_error": True})
        messages.append({"role": "assistant", "content": r.content})  # append verbatim
        messages.append({"role": "user", "content": results})          # results FIRST, all in one msg
    raise RuntimeError("step limit reached")
```
Sources for each line: [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls), [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons). `max_tokens=16000` follows the **[skill-local]** non-streaming default guidance; the docs' tutorial uses 1024.

**Inferences**
- For a beginner tutorial, teach the manual loop first (it is ~25 lines and exposes every protocol rule), then show the tool runner as the "collapse" step, mirroring Anthropic's own Ring 1–5 progression.
- Because Opus 5.5 / Sonnet 5.5 / Fable 5.1 reject forced `tool_choice`, a tutorial should not rely on `tool_choice: {"type": "any"}` tricks; use `auto` and prompt wording.

**Gaps**
- The exact current `anthropic` PyPI version number was not visible on the fetched pages (the skill mentions 0.116.0 for a `pause_turn` caveat; a 1.x line exists per the skill's `sdk-upgrade.md` but I did not confirm the latest release).

### Q2. Thorsten Ball's "How to Build an Agent" (Amp, Apr 2025): steps, key insight, ports

**Takeaway**
Ball's essay builds a Go code-editing agent in ~300 lines with three tools (`read_file`, `list_files`, `edit_file`) and argues that "It's an LLM, a loop, and enough tokens." Its structure (chat loop → tool type → one tool at a time → tool-result feedback loop) is the canonical outline for a beginner harness; the only Python ports found are blog write-ups, not maintained repos.

**Cited Findings**
- Published April 15, 2025 on ampcode.com; Go, using `github.com/anthropics/anthropic-sdk-go` and `github.com/invopop/jsonschema` to generate tool input schemas via reflection; model constant `anthropic.ModelClaude3_7SonnetLatest`. Size estimates in the text: "less than 400 lines" (intro), ~90 lines after the chat loop, ~190 after read/list tools, "300 lines of code and three tools" at the end. — [How to Build an Agent](https://ampcode.com/how-to-build-an-agent)
- Steps: (1) project setup; (2) `Agent` struct with client + stdin reader; (3) `Run()` chat loop keeping a `conversation` slice and resending the whole history each turn (`MaxTokens` 1024) — "the API is stateless"; (4) demo that the model can "signal" a tool call in plain text; (5) `ToolDefinition{Name, Description, InputSchema, Function}`; (6) register tools and pass them in the request; (7) `read_file` tool with a `GenerateSchema[T]` helper; (8) handle `tool_use` blocks: run `executeTool`, collect results, send them back as a user message without prompting the user (`readUserInput` flag); tool errors are returned with the error flag set; (9) `list_files` via `filepath.Walk`, directories suffixed with `/`, returned as a JSON array; (10) `edit_file` with `path`, `old_str`, `new_str`, creating the file (and parent dirs) when it does not exist and `old_str` is empty. The loop never inspects `stop_reason`; it scans content blocks and re-calls the model whenever any tool results were produced. — [How to Build an Agent](https://ampcode.com/how-to-build-an-agent)
- Edit-tool discrepancy worth teaching: the description says `old_str` "must only have one match" but the implementation uses `strings.Replace(..., -1)` (replace all) and returns an error only when `old_str` is not found. — [How to Build an Agent](https://ampcode.com/how-to-build-an-agent)
- Key quotes: "It's an LLM, a loop, and enough tokens."; "Anything goes as long as Claude can make sense of it."; the rest is "Elbow grease." — [How to Build an Agent](https://ampcode.com/how-to-build-an-agent)
- Ports / re-implementations **[unverified, search snippets only]**: a Python port described in Matt Herzog's "learning in public" post — [matt-herzog.beehiiv.com](https://matt-herzog.beehiiv.com/p/learning-in-public-building-my-first-ai-coding-agent); a Chinese-language Go reproduction (Apr 18, 2025) — [tonybai.com](https://tonybai.com/2025/04/18/reproduce-thorsten-balls-code-agent/); a JavaScript rebuild in a Web Directions talk by Kevin Yank — [webdirections.org](https://www.webdirections.org/dev-summit/speakers/kevin-yank.php); a secondary summary calling it a "400-line blueprint" — [howaiworks.ai](https://howaiworks.ai/thorsten-ball-how-to-build-an-agent/).
- Thomas Ptacek's companion essay (Python, `ping` tool via subprocess) makes the same point: the loop appends user input to a context list, calls the model with tools, runs requested tools, appends results, repeats; "giving the agent `bash` would produce a coding agent"; "context engineering is a straightforwardly legible programming problem"; sub-agents are "a new context array with its own model call". — [You Should Write An Agent](https://fly.io/blog/everyone-write-an-agent/); Simon Willison endorsed it on 7 Nov 2025 as the new "hello world" of AI engineering — [simonwillison.net/b/9139](https://simonwillison.net/b/9139)

**Inferences**
- A faithful Python port of Ball's outline is ~150–200 lines with the current SDK (the Go version spends many lines on schema generation that `@beta_tool` or hand-written `input_schema` dicts avoid).
- Ball's "signal a tool call in plain text" demo (step 4) is a good pedagogical bridge before introducing the structured `tool_use` protocol.

**Gaps**
- No maintained, widely-starred GitHub Python port of the Ball post was found; the Herzog post was not fetched, so its code quality and SDK version are unknown.

### Q3. mini-swe-agent's minimal design and what a beginner can copy

**Takeaway**
mini-swe-agent v2 is ~100 lines of agent class around one bash tool, every command run in a fresh `subprocess` (no persistent shell), a flat linear `messages` list that *is* the trajectory, explicit `step_limit` / `cost_limit` / `wall_time_limit_seconds` / `max_consecutive_format_errors` guards, head+tail truncation of long outputs at 10,000 characters, and a sentinel command (`echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT`) to end the run. All of these are directly copyable.

**Cited Findings**
- README: "about 100 lines of Python for the agent class", bash as the only tool, "doesn't even need to use the tool-calling interface of the LMs", actions via `subprocess.run` so "sandboxing is just a matter of swapping in `docker exec`", linear history so "the trajectory and the LM's input are the same"; scores "above 74% on SWE-bench Verified"; this is v2 (v1 on a `v1` branch). Install: `pip install mini-swe-agent` then `mini`; environments: local, docker/podman, singularity/apptainer, bubblewrap, contree. Python names: `DefaultAgent`, `LitellmModel`, `LocalEnvironment`, `agent.run(...)`. — [SWE-agent/mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent); PyPI 2.4.1 — [pypi.org](https://pypi.org/project/mini-swe-agent/2.4.1/)
- `agents/default.py` `AgentConfig`: `system_template`, `instance_template` (Jinja2), `step_limit` (default 0 = none), `cost_limit` (default 3.0 USD), `wall_time_limit_seconds` (0 = none), `max_consecutive_format_errors` (3), `output_path` (trajectory JSON saved after every loop iteration). Exceptions drive control flow: `FormatError` (bills cost, appends messages, exits with `exit_status` "RepeatedFormatError" after the limit), `InterruptAgentFlow`, `LimitsExceeded`, `TimeExceeded`; any other exception records an exit message with the exception class name then re-raises. Loop ends when the last message has role `"exit"`; result `extra` includes `exit_status` and `submission`. `self.messages` is flat and never pruned or summarized. — [default.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/agents/default.py)
- `environments/local.py`: `subprocess.Popen(shell=True, text=True, ...)` with stderr merged into stdout, UTF-8 with replacement, `cwd` and env from config merged over `os.environ`, new session on POSIX; default timeout 30 s; on timeout kills the whole process group "so no children are orphaned", collects partial output; any exception yields `returncode: -1` plus `exception_info` and `extra` with exception type/text. No truncation at this layer. First output line `COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` with return code 0 raises `Submitted`. — [local.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/environments/local.py)
- `config/mini.yaml`: instance template prescribes a six-step workflow (analyze, reproduction script, edit, verify, edge cases, submit), says "Every action is executed in a new subshell", and requires finishing with `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` alone. `format_error_template` tells the model to respond "exactly one bash tool call" when it was cut off or produced no tool call. `action_observation_template` returns JSON with `returncode`, `output`, `exception_info`; outputs over 10,000 chars are shown as `output_head` (5,000), `output_tail` (5,000), `elided_chars`, and "Output too long." Defaults `step_limit: 0`, `cost_limit: 3.`, `mode: confirm`; env sets `PAGER`/`MANPAGER=cat`, `PIP_PROGRESS_BAR=off`, `TQDM_DISABLE=1`. — [mini.yaml](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/config/mini.yaml)
- `models/litellm_model.py` (v2) actually sends `tools=[BASH_TOOL]` and parses `response.choices[0].message.tool_calls` via `parse_toolcall_actions(...)`, raising `FormatError` on failure; cost is `litellm.cost_calculator.completion_cost(response, model=...)` accumulated into `GLOBAL_MODEL_STATS`; each stored message carries `extra = {actions, response, cost, timestamp}`. — [litellm_model.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/models/litellm_model.py). This contradicts the README's "doesn't even need to use the tool-calling interface" — the v2 default model path *does* use native tool calling (the README claim may describe v1 or an alternative text-parsing model class).
- Batch runner: `mini-extra swebench --model ... --subset verified --split test --workers 4`; flags `-o/--output`, `--subset`, `--split`, `--slice 0:5`, `-w/--workers`, `--filter`, `--shuffle`, `--redo-existing`, `--environment-class`. Each instance saves `<instance_id>.traj.json` ("only saved upon completion"); `preds.json` maps instance id to `{model_name_or_path, instance_id, model_patch}`; evaluation via `sb-cli submit swe-bench_verified test --predictions_path preds.json --run_id <id>` or local `python -m swebench.harness.run_evaluation`. Each instance uses its own Docker image, default `docker.io/swebench/sweb.eval.x86_64.<instance_id>:latest`; `environment.pull_timeout` default 120 s. — [mini-swe-agent SWE-bench docs](https://mini-swe-agent.com/latest/usage/swebench/)

**Inferences**
- A beginner can copy five things verbatim in spirit: (a) stateless per-command subprocess with timeout + process-group kill, (b) `returncode`/`output` JSON observation with head/tail truncation at a fixed character budget, (c) step/cost/wall-time/format-error limits as config, (d) a sentinel "I'm done" command, (e) `messages` list == trajectory, dumped to JSON after every step.
- Its "exceptions as control flow" design (`Submitted`, `LimitsExceeded`, `FormatError`) is simple enough for a tutorial and avoids nested if/else in the loop.

**Gaps**
- I did not fetch `models/utils/actions_toolcall.py`, so the exact `BASH_TOOL` schema text and the parser are not quoted.
- Per-instance Docker runs for SWE-bench are x86-only per the docs; I did not verify Apple-silicon behaviour.

### Q4. Well-regarded tutorials / courses (URL, date, what it teaches, language)

**Takeaway**
The best current beginner path is: Anthropic's own 5-ring "Build a tool-using agent" docs tutorial (Python/TS/…), then Ball's essay for the coding-agent shape, then mini-swe-agent for a real minimal harness, with Anthropic's three engineering posts (context engineering, long-running harnesses, agent evals) as the conceptual spine. Course platforms (Anthropic Academy, DeepLearning.AI, LangChain, Hugging Face) exist but none teaches a from-scratch *coding* harness in Python.

**Cited Findings**

Official Anthropic material:
- [Tutorial: Build a tool-using agent](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent) — undated (examples dated March 2026), Python/TypeScript/C#/Go/Java/PHP/Ruby. Rings 1–5: single call → loop → parallel tools → `is_error` → tool runner. No loop cap, no truncation, no caching shown.
- [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons) — Python; the only official page with a capped agent loop (`MAX_STEPS`, `MAX_CONTINUATIONS`) and the `max_tokens`-mid-tool-call retry.
- [Tool runner (SDK)](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner) and [anthropic-sdk-python/tools.md](https://github.com/anthropics/anthropic-sdk-python/blob/main/tools.md) — Python; `@beta_tool`, `max_iterations`, per-turn hooks, `ToolError`, deferral for approval.
- [Anthropic Academy (skilljar)](https://anthropic.skilljar.com/) — courses listed: "Building with the Claude API" (`/claude-with-the-anthropic-api`, covers tool use), "Claude Code in Action" (`/claude-code-in-action`: long unattended sessions, steering, verification), "Introduction to Model Context Protocol" (Python MCP servers/clients), "MCP: Advanced Topics", "Introduction to agent skills", "Introduction to subagents", "Claude Platform 101". No durations shown; **no dedicated Claude Agent SDK course and no standalone tool-use course on skilljar** as of this fetch.
- DeepLearning.AI "Agent Skills with Anthropic" (Elie Schoppik): beginner, 2 h 19 min, 10 lessons; final lesson builds a research agent with the Claude Agent SDK ("the same internal harness that Claude Code does"). — [deeplearning.ai](https://www.deeplearning.ai/short-courses/agent-skills-with-anthropic/) **[search snippet]**
- [anthropic-cookbook/patterns/agents](https://github.com/anthropics/anthropic-cookbook/tree/main/patterns/agents) — Python notebooks: `basic_workflows.ipynb` (prompt chaining, routing, parallelization), `orchestrator_workers.ipynb`, `evaluator_optimizer.ipynb`, `async_multi_agent_orchestration.ipynb`, `latency_multi_agent.ipynb`, `util.py`; README says it is the reference implementation for "Building Effective Agents" (Schluntz & Zhang). It covers workflow patterns, not a coding-agent loop.
- [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — Sep 29, 2025. Context engineering = curating "the full set of tokens the model sees"; "context rot" / finite "attention budget"; system prompts at the "right altitude" with minimal information; minimal, unambiguous tool sets; just-in-time retrieval via file paths/grep/glob (Claude Code loads CLAUDE.md up front, retrieves the rest); long-horizon techniques: compaction (Claude Code keeps the summary plus the five most recently accessed files; clearing old tool results is a light form), structured note-taking (NOTES.md / to-do), sub-agents returning 1,000–2,000-token summaries.
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — Nov 26, 2025 (Justin Young). Problems: each session starts with no memory; agents do too much at once and leave half-finished work; "Claude declares victory on the entire project too early". Harness: initializer agent (first session) + coding agent (every later session), differing only in prompt; `claude-progress.txt`; a JSON feature list (200+ features, all initially failing; JSON chosen because the model is less likely to overwrite it than Markdown; "It is unacceptable to remove or edit tests" — agents may only flip `passes`); `init.sh` to start the dev server; descriptive git commits for rollback; end-to-end testing (Puppeteer MCP) before marking a feature done; startup routine: read git log + progress file + feature list, pick the highest-priority unfinished feature, start server, run a basic e2e check.
- [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) — Jan 9, 2026 (details in Q6).

Independent, from-scratch coding-agent tutorials:
- [How to Build an Agent](https://ampcode.com/how-to-build-an-agent) — Apr 15, 2025, Go, ~300 lines (Q2).
- [mini-swe-agent](https://github.com/SWE-agent/mini-swe-agent) — Python, ~100-line agent class (Q3).
- [You Should Write An Agent](https://fly.io/blog/everyone-write-an-agent/) — Thomas Ptacek, Python, late 2025 (references GPT-5 / Sonnet 4.5; linked by Willison 7 Nov 2025); loop + `ping` tool; context-as-array framing; sub-agents.
- [How coding agents work](https://simonwillison.net/guides/agentic-engineering-patterns/how-coding-agents-work/) — Simon Willison's guide chapter (references Codex prompt "as-of March 2026"): a coding agent is "software that wraps an LLM" with hidden system prompts and tools; statelessness means the harness resends the whole conversation; loop = system prompt → model replies with text or tool call → harness extracts call (often via regex) and runs it → result goes back; "a simple version takes only a few dozen lines"; most agents define a dozen or more tools, the most powerful being code execution; coding agents "avoid editing earlier conversation content so the cache stays effective".
- [llm-coding-agent 0.1a0](https://simonwillison.net/2026/Jul/2/llm-coding-agent/) — Jul 2, 2026, Python on the `llm` library; six tools: `read_file(path, offset=0, limit=2000)` returning `cat -n`-style numbered lines; `write_file(path, content)` (prefer `edit_file` for existing files); `edit_file(path, old_string, new_string, replace_all=False)` — `old_string` must be unique unless `replace_all`, returns a diff; `execute_command(command, timeout=120)` capped at 600 s, kills the whole process tree on timeout, returns stdout/stderr plus "Exit code"; `list_files(pattern='**/*', path='.')` newest first, skips hidden dirs / `node_modules` / `__pycache__` / `.gitignore` matches, max 200 paths; `search_files(pattern, ..., max_results=100)` returning `path:line:line`. Permissions: `llm code --yolo` (no prompts), `--allow "pytest*" --allow "git diff*"` pre-approval patterns, Python API `CodingAgent(..., approve=True)`. Built by having Claude Code write `spec.md` then red/green TDD.
- [Build a Coding Agent from Scratch (sidbharath.com)](https://sidbharath.com/blog/build-a-coding-agent-python-tutorial/) — Aug 14, 2025 (updated Aug 25, 2026), Anthropic Python SDK, model id `claude-sonnet-5` (a valid legacy id per the models page), Python 3.10+. Phase 1 `read_file`/`write_file`/`list_files` (~300 lines), Phase 2 `run_python` (AST check + subprocess) and `run_bash` (60 s timeout, 10,000-char output cap), Phase 3 `search_files` (max 50 results, 200-char lines), `edit_file` (exact, must appear once), paginated `read_file` (500 lines/call); streaming loop checks `final_message.stop_reason == "tool_use"`; no iteration cap, no permission prompts, compaction only as pseudocode; some snippets skip the workspace-path check and omit imports.
- **[search snippets, not fetched]**: heyuan110.com (Mar 7, 2026, OpenAI SDK + `rich`/`prompt_toolkit`, ~250 lines) — [link](https://www.heyuan110.com/posts/ai/2026-03-07-build-ai-agent-python/); decodingai.com 8-lesson open course building "Decode" with Pydantic AI, claims harness-only changes moved an agent from ~30th to top-5 on LangChain's Terminal-Bench experiment — [link](https://www.decodingai.com/p/building-a-coding-agent-from-scratch-system-design); youcanbuildthings.com ~150-line single-file agent — [link](https://youcanbuildthings.com/articles/build-ai-coding-agent-from-scratch-python); freeCodeCamp video course by Lane Wagner (boot.dev) — [link](https://www.freecodecamp.org/news/build-an-ai-coding-agent-in-python/); Orkes "what's really under the hood" — [link](https://orkes.io/blog/building-a-coding-agent-from-scratch-whats-really-under-the-hood).

Other ecosystems:
- [OpenAI Cookbook: Orchestrating Agents](https://developers.openai.com/cookbook/examples/orchestrating_agents) — Python, chat-completions; marked "archived and may reference outdated models or APIs"; `run_full_turn` loop, `function_to_schema` (signature/docstring → schema), `execute_tool_call`, routines (instructions + tools) and handoffs (`transfer_to_XXX` returning an `Agent`); basis of the Swarm proof of concept.
- [langchain-ai/agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch) — Python 3.11+, LangGraph; email assistant; notebooks: LangGraph 101, `agent.ipynb`, `evaluation.ipynb` (pytest + LangSmith `evaluate`, LLM-as-judge, tool-call checks), `hitl.ipynb` (Agent Inbox review of tool calls), `memory.ipynb` (LangGraph Store); materials date from ~Apr 2025.
- [Hugging Face Agents Course](https://huggingface.co/learn/agents-course/unit0/introduction) — Unit 1 agent fundamentals (tools, thoughts/actions/observations, chat templates, Python functions as tools), Unit 2 smolagents / LangGraph / LlamaIndex, Unit 3 use cases, Unit 4 benchmark assignment; bonus units on function-calling fine-tuning and observability/evaluation; ~1 week per chapter at 3–4 h/week; no dates on the page.

**Inferences**
- For a Python-first beginner tutorial on *harness engineering*, the official Anthropic tutorial + stop-reasons page + mini-swe-agent together already cover loop, tools, errors, limits, truncation, and trajectories; the gaps a tutorial must fill itself are permission gating, CLAUDE.md loading, compaction, and a mini eval — which is exactly the list in this assignment.
- Willison's `llm-coding-agent` tool signatures (offset/limit reads, unique-match edits returning a diff, capped command timeouts, capped listings) are a good, dated (Jul 2026) reference tool surface to mirror.

**Gaps**
- I could not confirm an Anthropic Academy course specifically on the Claude Agent SDK; third-party roundups mention one but the skilljar catalog fetched today does not list it.
- LangChain Academy's hosted "agents from scratch" course page was not fetched (only the GitHub repo).

### Q5. Concrete beginner pitfalls (with the fix each source uses)

**Takeaway**
Every pitfall in the brief has an official or widely-copied mitigation: cap tool output (head/tail), cap steps/cost/time, gate or sandbox shell commands, make edits exact-match-unique and return informative errors with `is_error`, keep history append-only for caching (and for the newer preserved-thinking check), return all parallel results in one user message, and enforce per-command timeouts with process-group kills.

**Cited Findings**

Tool result too large / context rot:
- "Context rot": recall degrades as the window grows; tools "should return token-efficient results". — [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- mini-swe-agent truncates observations over 10,000 chars to `output_head`/`output_tail` of 5,000 each plus `elided_chars`. — [mini.yaml](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/config/mini.yaml)
- Willison's tools page reads (`offset`/`limit=2000` lines), cap listings at 200 paths and searches at `max_results=100`. — [llm-coding-agent](https://simonwillison.net/2026/Jul/2/llm-coding-agent/); sidbharath caps bash output at 10,000 chars and search at 50 results / 200-char lines. — [sidbharath.com](https://sidbharath.com/blog/build-a-coding-agent-python-tutorial/)
- Anthropic's text editor tool exposes `max_characters` to truncate `view` output. — [Text editor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool)
- Heavier options once a tutorial outgrows truncation: context editing `context_management={"edits": [{"type": "clear_tool_uses_20250919"}]}` (beta `context-management-2025-06-27`) and server-side compaction (beta `compact-2026-01-12`; must append `response.content` including compaction blocks). **[skill-local]** — bundled `claude-api` skill; public pages: [Compaction](https://platform.claude.com/docs/en/build-with-claude/compaction)

Agent loops forever:
- Official loop guard: `MAX_STEPS = 20`, `MAX_CONTINUATIONS = 5`, raise when exceeded. — [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)
- Tool runner `max_iterations`. — [Tool runner](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner)
- mini-swe-agent: `step_limit`, `cost_limit` (3.0 USD default), `wall_time_limit_seconds`, `max_consecutive_format_errors` (3). — [default.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/agents/default.py)
- Premature "done": agents "declared the job done" after seeing partial progress; fix with a feature list the agent may only flip to `passes`, plus e2e verification. — [Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

Destructive shell commands (allowlist / confirm / sandbox):
- CLAUDE.md-style instructions are "context, not enforced configuration. To block an action regardless of what Claude decides, use a PreToolUse hook instead." — [Claude Code memory docs](https://code.claude.com/docs/en/memory)
- Pattern allowlists and a yolo flag: `llm code --allow "pytest*" --allow "git diff*"`, `--yolo`, `approve=True`. — [llm-coding-agent](https://simonwillison.net/2026/Jul/2/llm-coding-agent/)
- mini-swe-agent default `mode: confirm`; swap `subprocess.run` for `docker exec` to sandbox. — [mini.yaml](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/config/mini.yaml); [README](https://github.com/SWE-agent/mini-swe-agent)
- OS-level sandbox reference (what Claude Code does): macOS Seatbelt, Linux/WSL2 bubblewrap + `socat`, package `@anthropic-ai/sandbox-runtime`; writes allowed only in cwd, per-user temp, and added dirs; protected paths (`.claude/settings*`, `.mcp.json`, `.bashrc`, `.git/hooks`) stay write-denied; reads broad by default; network only via a local proxy checked against `allowedDomains` (starts empty). Settings: `sandbox.enabled`, `failIfUnavailable`, `allowUnsandboxedCommands`, `filesystem.allowWrite/denyRead/...`, `network.allowedDomains/deniedDomains`, `excludedCommands`, `credentials.files/envVars`. Not covered: Read/Edit/Write tools, hooks, local MCP servers; TLS not inspected (domain-fronting risk); Unix sockets like `/var/run/docker.sock`. — [Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing)
- **[skill-local]** Design heuristic: start with bash for breadth, promote an action to a dedicated tool when you need to gate, render, audit, or parallelize it (a `send_email` tool is gateable; `bash -c "curl -X POST"` is not); a dedicated `edit` tool can reject writes if the file changed since it was last read. — bundled `claude-api` skill, `shared/agent-design.md`

Edit tool that silently fails:
- `str_replace` `old_str` "must match exactly, including whitespace and indentation". — [Text editor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/text-editor-tool)
- Ball's `edit_file` description says one match but code replaces all; errors only when not found. — [How to Build an Agent](https://ampcode.com/how-to-build-an-agent)
- Willison: `old_string` must be unique unless `replace_all`, and the tool "returns a diff of the change so it can be verified". — [llm-coding-agent](https://simonwillison.net/2026/Jul/2/llm-coding-agent/); sidbharath: must appear exactly once or return an error asking for more specificity. — [sidbharath.com](https://sidbharath.com/blog/build-a-coding-agent-python-tutorial/)

Keeping errors in context so the model recovers:
- Return `is_error: true` with instructive text; Claude "will retry 2–3 times with corrections". — [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls)
- Tool runner sends exception type + message (not the stack trace) as an `is_error` result. — [Tool runner](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-runner)
- mini-swe-agent feeds a `format_error_template` back as the next observation instead of crashing, and exits only after 3 consecutive format errors; environment exceptions become `returncode: -1` + `exception_info`. — [mini.yaml](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/config/mini.yaml); [local.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/environments/local.py)

Prompt caching and append-only history:
- Cache is a prefix match in the order `tools` → `system` → `messages`; "Cache hits require 100% identical prefix content"; editing tool definitions invalidates all three levels; up to 4 explicit breakpoints; a breakpoint on content that changes each request never hits (system looks back 20 blocks); minimum cacheable prompt 512 tokens on Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 5.5 (1,024 on Sonnet 5 / Opus 4.8, 4,096 on Opus 4.6 / Haiku 4.5); TTL 5 min (refreshes on use) or `"ttl": "1h"`; 5-min write 1.25×, 1-h write 2×, read 0.1× (0.05× Opus 5.5 / Sonnet 5.5, 0.025× Fable 5.1). Simplest pattern: top-level `cache_control={"type": "ephemeral"}` (automatic caching moves the breakpoint to the last cacheable block each turn). Check `usage.cache_read_input_tokens` / `cache_creation_input_tokens`; both 0 means no caching. Keep thinking config and `output_config.effort` constant across calls. — [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- "Coding agents avoid editing earlier conversation content so the cache stays effective." — [How coding agents work](https://simonwillison.net/guides/agentic-engineering-patterns/how-coding-agents-work/)
- **[skill-local]** Beyond caching, newer models enforce "preserved thinking": for accounts created on/after 2026-08-31 the API checks that `system`, `tools`, and every earlier message are byte-identical to when a thinking block was produced; editing history then returns a 400 (older accounts can opt in with `thinking.block_binding.prefix_mismatch_behavior`, beta `thinking-binding-controls-2026-08-01`). Append-only replacements: append a `{"role": "system", ...}` message to `messages` instead of editing the top-level `system`; declare all tools up front; use server-side compaction. — bundled `claude-api` skill, `shared/model-migration.md`; public page: [Migration guide](https://platform.claude.com/docs/en/about-claude/models/migration-guide)
- Mid-conversation `{"role": "system"}` messages (no beta) are the cache-safe way to inject operator instructions on Opus 5.5 / Sonnet 5.5 / Fable 5.1 / Haiku 5.5 (not Sonnet 5). **[skill-local]** — bundled `claude-api` skill, SKILL.md

Parallel tool calls:
- One assistant message may hold several `tool_use` blocks; return **all** `tool_result`s in a **single** user message, `tool_result`s first. — [Handle tool calls](https://platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls); Ring 3 code. — [Tutorial](https://platform.claude.com/docs/en/agents-and-tools/tool-use/build-a-tool-using-agent)
- To force at most one call per turn while learning: `tool_choice={"type": "auto", "disable_parallel_tool_use": True}`. — [Tool use overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- **[skill-local]** Splitting results across messages "silently trains Claude to stop making parallel calls"; for a failed tool return `is_error: true`, don't drop it. — bundled `claude-api` skill, SKILL.md

Timeouts:
- mini-swe-agent: 30 s default per command, kill the process group on expiry, keep partial output. — [local.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/environments/local.py)
- Willison: `execute_command(timeout=120)` capped at 600 s, kills the whole process tree. — [llm-coding-agent](https://simonwillison.net/2026/Jul/2/llm-coding-agent/)
- API side: `max_tokens` hit mid tool call → truncated `tool_use`, retry with a larger budget; empty `end_turn` after tool results should not be resent unchanged. — [Handling stop reasons](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons)
- Disable pagers/progress bars in the subprocess env (`PAGER=cat`, `PIP_PROGRESS_BAR=off`, `TQDM_DISABLE=1`) so commands don't hang or spam output. — [mini.yaml](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/config/mini.yaml)

System prompt and project instruction file (CLAUDE.md / AGENTS.md):
- CLAUDE.md scopes: `~/.claude/CLAUDE.md` (user), `./CLAUDE.md` or `./.claude/CLAUDE.md` (project), `./CLAUDE.local.md` (gitignored personal). Files in cwd and every parent directory load at launch, concatenated root→cwd (closest read last); subdirectory files load on demand when a file there is touched. Best practice: "target under 200 lines per CLAUDE.md file"; keep to facts needed every session (build commands, conventions, "always do X"); contradictory instructions may be picked arbitrarily. `@path/to/import` syntax, relative to the importing file, max depth four hops; code spans are not imported. `.claude/rules/*.md` for topic files, optionally path-scoped. If a repo has `AGENTS.md` and no CLAUDE.md, Claude Code reads AGENTS.md; if both, CLAUDE.md only. Auto memory loads "first 200 lines or 25KB". — [Claude Code: How Claude remembers your project](https://code.claude.com/docs/en/memory)
- AGENTS.md: open Markdown format, "a README for agents", stewarded under the Linux Foundation's Agentic AI Foundation, used by 60k+ projects; supported by Codex, Jules, Aider, goose, Zed, Warp, VS Code, Devin, Windsurf, Junie, Amp, Cursor, Gemini CLI, Copilot coding agent, etc.; recommended sections: overview, build/test commands, code style, testing, security, PR conventions; nearest file in the directory tree wins; explicit chat prompts override everything. — [agents.md](https://agents.md/)
- System prompt guidance: minimal set of information at the "right altitude", structured with XML tags or Markdown headers; start minimal and add rules from observed failures; Claude Code loads CLAUDE.md up front and retrieves other files just-in-time. — [Effective context engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- Note/progress files as harness state: `claude-progress.txt`, JSON feature list, `init.sh`, git commits; agent prompt forbids editing tests. — [Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

**Inferences**
- A tutorial's "read file" tool should return numbered lines with offset/limit, and "run command" should return `{returncode, output}` with head/tail truncation, timeout, and process-group kill — this combination appears independently in mini-swe-agent, Willison's agent, and sidbharath's tutorial.
- Permission gating belongs in the harness (a `confirm()` before `run_command`/`write`/`edit`, plus an allowlist of safe prefixes), never in the prompt; the Claude Code docs say so explicitly for hooks vs. CLAUDE.md.
- Append-only history should be taught as a hard rule from step 1 (it serves caching today and the preserved-thinking check on new accounts); truncate at tool-execution time, before results enter `messages`, rather than editing old messages later.

**Gaps**
- No official page states a recommended character/token budget for a single tool result; the 10,000-character figure is a mini-swe-agent / tutorial convention, not Anthropic guidance.
- I did not fetch the Bash tool reference page, so its stated security considerations are not quoted.

### Q6. Writing a 5-task mini eval and logging trajectories / tokens / cost

**Takeaway**
Anthropic's eval post supplies the vocabulary (task, trial, grader, transcript, outcome), the rules (fresh environment per trial, several trials per task, grade the outcome not the path, start with 20–50 tasks drawn from real failures, read transcripts), and the metrics (pass@1 / pass@k / pass^k); mini-swe-agent supplies the mechanics (per-instance sandbox, `*.traj.json`, `preds.json`, `--workers`, `--slice`). Cost accounting comes from `response.usage` fields and the public price table.

**Cited Findings**
- Definitions: task = "a single test with defined inputs and success criteria"; trial = one attempt; grader = logic that scores part of performance (a task may have several); transcript = the full record including tool calls (also "trace or trajectory"); outcome = final environment state, e.g. whether a reservation actually exists, not whether the agent claimed it. — [Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Grader types: code-based/deterministic (string match, binary tests, static analysis, tool-call verification — fast, cheap, reproducible, can be brittle), model-based (rubrics, pairwise, multi-judge — flexible, non-deterministic, must be calibrated), human (gold standard). "Often better to grade what the agent produced, not the path it took." — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Metrics: pass@k = at least one success in k attempts (50% pass@1 = half of tasks succeed on first try); pass^k = all k trials succeed (75% per-trial over 3 trials ≈ 0.75³ ≈ 42%). Use pass@k when one success suffices, pass^k when consistency matters. — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Isolation and size: start each trial from a clean environment (one case where an agent read git history from earlier trials); run several trials per task; "20-50 simple tasks drawn from real failures" is a strong start; read transcripts so failures "look fair". — [Demystifying evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)
- Trajectory format in practice: mini-swe-agent writes the linear `messages` list (each message with `extra = {actions, response, cost, timestamp}`) to `output_path` after every step and to `<instance_id>.traj.json` per instance in batch mode; `preds.json` keyed by instance id; `--workers N`, `--slice 0:5`, `--redo-existing`; one Docker image per instance; results evaluated by an external harness (`sb-cli submit ...` or `swebench.harness.run_evaluation`). — [SWE-bench docs](https://mini-swe-agent.com/latest/usage/swebench/); [default.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/agents/default.py); [litellm_model.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/models/litellm_model.py)
- Cost accounting fields: `usage.input_tokens` (uncached), `usage.cache_creation_input_tokens`, `usage.cache_read_input_tokens`, `usage.output_tokens`; total input = sum of the three input fields. — [Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). Prices per MTok: Opus 5.5 $4/$20, Sonnet 5.5 $2/$10, Haiku 5.5 from $0.10/$0.50, Fable 5.1 $10/$50; cache reads 10% (5% Opus 5.5/Sonnet 5.5, 2.5% Fable 5.1). — [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)
- mini-swe-agent computes per-call cost with `litellm.cost_calculator.completion_cost` and stops at `cost_limit`. — [litellm_model.py](https://raw.githubusercontent.com/SWE-agent/mini-swe-agent/main/src/minisweagent/models/litellm_model.py)
- The Python SDK emits an OpenTelemetry span per API call when a tracer provider is configured. — [anthropic-sdk-python](https://github.com/anthropics/anthropic-sdk-python)
- LangChain's course evaluates with pytest + LangSmith `evaluate`, LLM-as-judge for free text, deterministic checks on tool calls/triage. — [agents-from-scratch](https://github.com/langchain-ai/agents-from-scratch)
- Verification inside the loop (the "self-check" step): the long-running harness post requires an e2e test before a feature is marked passing and a baseline check at session start. — [Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)

Sketch of a 5-task mini eval consistent with the above (own synthesis, not a quoted source):
```python
# tasks/<name>/{repo/, prompt.txt, test_check.py}; checker = pytest exit code (deterministic grader)
import json, shutil, subprocess, tempfile, time, pathlib
def run_task(task_dir, n_trials=3):
    passes = 0
    for t in range(n_trials):
        sandbox = pathlib.Path(tempfile.mkdtemp())                  # fresh env per trial
        shutil.copytree(task_dir / "repo", sandbox / "repo")
        traj = run_agent(prompt=(task_dir / "prompt.txt").read_text(), cwd=sandbox / "repo")
        ok = subprocess.run(["pytest", "-q", str(task_dir / "test_check.py")],
                            cwd=sandbox / "repo", capture_output=True).returncode == 0
        with open("runs.jsonl", "a") as f:                           # one JSON line per trial
            f.write(json.dumps({"task": task_dir.name, "trial": t, "pass": ok,
                                "steps": traj.steps, "usage": traj.usage, "cost_usd": traj.cost,
                                "messages": traj.messages}) + "\n")
        passes += ok
    return passes / n_trials   # pass@1 estimate for this task; report mean over tasks
```
Cost per trial = Σ over calls of `input_tokens*p_in + cache_creation_input_tokens*1.25*p_in + cache_read_input_tokens*p_read + output_tokens*p_out` using the price table above ([Prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching), [Models overview](https://platform.claude.com/docs/en/about-claude/models/overview)).

**Inferences**
- With 5 tasks × 3 trials, report per-task pass rate and overall mean pass@1; also show pass^3 to make flakiness visible, since the eval post warns pass@k can hide instability.
- Because mini-swe-agent's `messages` list is the trajectory, the cheapest logging design is to dump that list plus `usage` per step to JSONL; no separate tracing stack is needed for a tutorial.

**Gaps**
- No source gives a worked example of a *5-task* local eval with pytest checkers; the sketch above is a synthesis.
- I did not find an official Anthropic recommendation for how many trials per task to run in small evals (the post says "several").

### Q7. Miscellaneous: sandboxing options for a tutorial, and sources not reached

**Takeaway**
Three sandbox tiers are documented: (1) process-level (subprocess + timeout + cwd + allowlist/confirm), (2) container (`docker exec` swap, per-task image), (3) OS sandbox (Seatbelt / bubblewrap as in Claude Code). A tutorial can present them in that order.

**Cited Findings**
- Tier 1 and 2: mini-swe-agent local env vs. `docker exec`; per-instance Docker images for SWE-bench. — [README](https://github.com/SWE-agent/mini-swe-agent); [SWE-bench docs](https://mini-swe-agent.com/latest/usage/swebench/)
- Tier 3: Claude Code sandbox details (Seatbelt / bubblewrap + socat, `@anthropic-ai/sandbox-runtime`, settings keys, coverage gaps). — [Claude Code sandboxing](https://code.claude.com/docs/en/sandboxing); Anthropic's product blog describes the same OS primitives **[search snippet]** — [claude.com blog](https://claude.com/it/blog/beyond-permission-prompts-making-claude-code-more-secure-and-autonomous)

**Inferences**
- For beginners on macOS/Linux, tier 1 plus "run the whole tutorial inside a throwaway Docker container" is the realistic recommendation; wiring bubblewrap/Seatbelt by hand is out of scope but can be pointed to via `@anthropic-ai/sandbox-runtime`.

**Gaps**
- I did not fetch the `@anthropic-ai/sandbox-runtime` repository or the Anthropic engineering post on sandboxing, so its CLI usage for arbitrary (non-Claude-Code) harnesses is unverified.
- OpenAI Codex CLI's sandbox approach was not researched (out of scope for an Anthropic-SDK tutorial).
