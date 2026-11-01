"""mini_harness.py: 一个 200 行左右、可运行的最小 coding-agent harness(教学用)。

依赖:   pip install anthropic
环境:   export ANTHROPIC_API_KEY=...
用法:   python mini_harness.py "test_calc.py 里有测试失败, 修好 calc.py" --workdir ./tasks/fix_add/repo

每一段代码对应教程里的一课:
  第 1 课 循环        -> run()
  第 2 课 工具        -> read_file / list_files / edit_file / run_command
  第 3 课 规矩        -> build_system()
  第 4 课 权限        -> gate()
  第 5 课 上下文      -> truncate(), 只追加历史, 缓存字段入日志
  第 6 课 停止与验证  -> MAX_STEPS / MAX_COST_USD / --require-tests
"""
import argparse
import difflib
import json
import os
import pathlib
import signal
import subprocess
import time

import anthropic

MODEL = os.environ.get("HARNESS_MODEL", "claude-opus-5-5")
WORKDIR = pathlib.Path(os.environ.get("HARNESS_WORKDIR", ".")).resolve()

MAX_STEPS = 40            # 第 6 课: 步数上限(官方参考实现用 20)
MAX_COST_USD = 2.0        # 第 6 课: 费用上限(mini-swe-agent 默认 3 美元)
MAX_OUTPUT_CHARS = 10_000  # 第 5 课: 单个工具结果上限, 头尾各留一半
CMD_TIMEOUT = 60          # 第 2 课: 命令默认超时(秒)

# 第 4 课: 不需要确认的只读命令前缀
SAFE_PREFIXES = ("ls", "cat ", "head ", "tail ", "wc ", "find ", "grep ", "rg ",
                 "git status", "git diff", "git log", "pytest", "python -m pytest")

# 美元 / 百万 token: (输入, 输出)。缓存读取按输入价的 10% 估算, 实际 5.5 代模型更低。
PRICE = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-1": (10.0, 50.0),
}


# ---------------------------------------------------------------- 第 2 课: 工具
def _resolve(path: str) -> pathlib.Path:
    """路径不允许逃出工作目录。"""
    p = (WORKDIR / path).resolve()
    if p != WORKDIR and WORKDIR not in p.parents:
        raise ValueError(f"path escapes the workspace: {path}")
    return p


def truncate(text: str) -> str:
    """第 5 课: 在进入 messages 之前截断, 保留头尾(mini-swe-agent 的做法)。"""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    half = MAX_OUTPUT_CHARS // 2
    elided = len(text) - MAX_OUTPUT_CHARS
    return f"{text[:half]}\n... [{elided} chars elided] ...\n{text[-half:]}"


def read_file(path: str, offset: int = 1, limit: int = 200) -> str:
    lines = _resolve(path).read_text(errors="replace").splitlines()
    chunk = lines[offset - 1: offset - 1 + limit]
    body = "\n".join(f"{offset + i:6d}\t{line}" for i, line in enumerate(chunk))
    if offset - 1 + limit < len(lines):
        body += f"\n... ({len(lines)} lines total; call again with offset={offset + limit})"
    return body or "(empty file)"


def list_files(pattern: str = "**/*", max_results: int = 200) -> str:
    out = []
    for p in sorted(WORKDIR.glob(pattern)):
        rel = p.relative_to(WORKDIR)
        if any(part.startswith(".") or part in ("node_modules", "__pycache__") for part in rel.parts):
            continue
        out.append(str(rel) + ("/" if p.is_dir() else ""))
        if len(out) >= max_results:
            out.append(f"... (truncated at {max_results} entries; narrow the pattern)")
            break
    return "\n".join(out) or "(no matches)"


def edit_file(path: str, old_string: str, new_string: str) -> str:
    p = _resolve(path)
    if not p.exists():
        if old_string:
            raise FileNotFoundError(f"{path} does not exist. Pass old_string='' to create it.")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(new_string)
        return f"created {path} ({len(new_string)} chars)"
    text = p.read_text()
    n = text.count(old_string)
    if n == 0:
        raise ValueError("old_string not found. Read the file again and copy the exact text, "
                         "including indentation and blank lines.")
    if n > 1:
        raise ValueError(f"old_string matches {n} places. Include more surrounding lines so it is unique.")
    new = text.replace(old_string, new_string, 1)
    p.write_text(new)
    diff = difflib.unified_diff(text.splitlines(), new.splitlines(),
                                fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=2)
    return "\n".join(diff) or "(no change)"


def run_command(command: str, timeout: int = CMD_TIMEOUT) -> str:
    gate(command)
    env = {**os.environ, "PAGER": "cat", "GIT_PAGER": "cat", "PIP_PROGRESS_BAR": "off", "TQDM_DISABLE": "1"}
    proc = subprocess.Popen(command, shell=True, cwd=WORKDIR, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=min(int(timeout), 600))
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)   # 杀整个进程组, 不留孤儿
        out, _ = proc.communicate()
        out = (out or "") + f"\n[killed after {timeout}s timeout]"
    return truncate(f"exit code: {proc.returncode}\n{out}")


# ---------------------------------------------------------------- 第 4 课: 权限门
def gate(command: str) -> None:
    """只读命令直接放行; 其他命令问人。HARNESS_YOLO=1 关闭确认(只在一次性容器里用)。"""
    if os.environ.get("HARNESS_YOLO"):
        return
    if command.strip().startswith(SAFE_PREFIXES):
        return
    answer = input(f"\n[permission] run `{command}` ? [y/N] ").strip().lower()
    if answer != "y":
        raise PermissionError("The user declined to run this command. "
                              "Try a different approach or explain what you need and why.")


TOOLS = [
    {"name": "read_file",
     "description": "Read a text file in the workspace and return numbered lines. "
                    "Large files are paged: pass offset/limit to continue (default 200 lines).",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Path relative to the workspace root"},
         "offset": {"type": "integer", "description": "1-based first line to return", "default": 1},
         "limit": {"type": "integer", "description": "Max lines to return", "default": 200}},
         "required": ["path"]}},
    {"name": "list_files",
     "description": "List files in the workspace matching a glob pattern (default '**/*'). "
                    "Hidden dirs, node_modules and __pycache__ are skipped; at most 200 entries.",
     "input_schema": {"type": "object", "properties": {
         "pattern": {"type": "string", "default": "**/*"}}, "required": []}},
    {"name": "edit_file",
     "description": "Replace exactly one occurrence of old_string with new_string in a file. "
                    "old_string must match exactly once; copy it from read_file output including "
                    "indentation. Pass old_string='' to create a new file. Returns a unified diff.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"}},
         "required": ["path", "old_string", "new_string"]}},
    {"name": "run_command",
     "description": "Run a shell command in the workspace. Returns the exit code and combined "
                    "stdout/stderr, truncated to 10k chars. Read-only commands run immediately; "
                    "anything else needs the user's approval. Default timeout 60s.",
     "input_schema": {"type": "object", "properties": {
         "command": {"type": "string"}, "timeout": {"type": "integer", "default": CMD_TIMEOUT}},
         "required": ["command"]}},
]
DISPATCH = {"read_file": read_file, "list_files": list_files, "edit_file": edit_file, "run_command": run_command}


# ---------------------------------------------------------------- 第 3 课: 规矩
def build_system() -> list:
    """系统提示 + 项目说明文件。只在任务开始时构建一次, 之后不再变动(保住前缀缓存)。"""
    text = (
        f"You are a careful coding agent working inside the workspace {WORKDIR}.\n"
        "Rules:\n"
        "- Read a file before you edit it. Keep edits minimal and in the existing style.\n"
        "- Never edit or delete tests to make them pass.\n"
        "- Run the test suite before claiming the task is done, and report the exact command and result.\n"
        "- If a tool returns an error, fix the cause instead of repeating the same call.\n"
        "- Finish with a short summary: what changed, how you verified it, anything left open."
    )
    for name in ("AGENTS.md", "CLAUDE.md"):
        f = WORKDIR / name
        if f.exists():
            text += f'\n\n<project_instructions source="{name}">\n{f.read_text()[:20_000]}\n</project_instructions>'
            break
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def cost_of(usage) -> float:
    p_in, p_out = PRICE.get(MODEL, (4.0, 20.0))
    cached_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cached_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    return (usage.input_tokens * p_in + cached_write * p_in * 1.25
            + cached_read * p_in * 0.10 + usage.output_tokens * p_out) / 1e6


# ---------------------------------------------------------------- 第 1 课: 循环
def run(task: str, log_path: str = "trajectory.jsonl", require_tests: bool = False) -> dict:
    client = anthropic.Anthropic()
    system = build_system()
    messages = [{"role": "user", "content": task}]
    cost, ran_tests, nudges = 0.0, False, 0
    log = open(log_path, "a")

    for step in range(1, MAX_STEPS + 1):
        r = client.messages.create(model=MODEL, max_tokens=8000, system=system,
                                   tools=TOOLS, messages=messages)
        cost += cost_of(r.usage)
        log.write(json.dumps({"ts": time.time(), "step": step, "stop_reason": r.stop_reason,
                              "usage": r.usage.model_dump(), "cost_so_far": round(cost, 4),
                              "content": [b.model_dump() for b in r.content]}, ensure_ascii=False) + "\n")
        log.flush()

        if r.stop_reason == "end_turn":
            # 第 6 课: 玩具版 Stop hook, 没跑测试就不许宣布完成(最多提醒两次)
            if require_tests and not ran_tests and nudges < 2:
                nudges += 1
                messages.append({"role": "assistant", "content": r.content})
                messages.append({"role": "user", "content": "[harness] You have not run the test suite yet. "
                                 "Run it with pytest, fix any failure, then give your final summary."})
                continue
            text = "".join(b.text for b in r.content if b.type == "text")
            return {"stop": "end_turn", "text": text, "steps": step, "cost_usd": round(cost, 4)}

        if r.stop_reason != "tool_use":
            # max_tokens(输出截断, 可加大 max_tokens 重试)、refusal、context 超限等
            return {"stop": r.stop_reason, "text": "", "steps": step, "cost_usd": round(cost, 4)}

        results = []
        for block in r.content:
            if block.type != "tool_use":
                continue
            try:
                if block.name == "run_command" and "pytest" in block.input.get("command", ""):
                    ran_tests = True
                output = DISPATCH[block.name](**block.input)      # input 已经是 dict
                results.append({"type": "tool_result", "tool_use_id": block.id, "content": output})
            except Exception as e:                                 # 错误回灌给模型, 不要吞掉
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": f"{type(e).__name__}: {e}", "is_error": True})
        messages.append({"role": "assistant", "content": r.content})   # 原样追加
        messages.append({"role": "user", "content": results})          # 所有结果放同一条消息, 且排在最前

        if cost > MAX_COST_USD:
            return {"stop": "cost_limit", "text": "", "steps": step, "cost_usd": round(cost, 4)}

    return {"stop": "step_limit", "text": "", "steps": MAX_STEPS, "cost_usd": round(cost, 4)}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("task")
    ap.add_argument("--workdir", default=".")
    ap.add_argument("--yolo", action="store_true", help="skip permission prompts (throwaway containers only)")
    ap.add_argument("--require-tests", action="store_true", help="refuse to finish until pytest has been run")
    ap.add_argument("--log", default="trajectory.jsonl")
    args = ap.parse_args()
    WORKDIR = pathlib.Path(args.workdir).resolve()
    if args.yolo:
        os.environ["HARNESS_YOLO"] = "1"
    result = run(args.task, log_path=args.log, require_tests=args.require_tests)
    print(json.dumps({k: v for k, v in result.items() if k != "text"}, ensure_ascii=False))
    print(result["text"])
