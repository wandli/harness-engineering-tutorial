一份从零开始的 Harness 工程（Harness Engineering）中文教程，讲 AI Agent 里"模型之外的一切"怎么设计：循环、工具、项目说明文件、权限与沙箱、上下文管理、停止与验证、评测。资料截至 2026 年 10 月，关键结论都附出处。

### 文件

| 文件 | 内容 |
|---|---|
| `教程.md` | 教程正文，11 课加学习路线和原文清单 |
| `教程_离线版.html` | 同内容的网页版，下载后双击即可在浏览器打开 |
| `教程.html` | 网页版源文件（Claude Artifact 格式，缺少 doctype，直接打开请用离线版） |
| `mini_harness.py` | 约 200 行的最小 coding agent harness，每段代码对应教程的一课 |
| `mini_eval.py` | 最小评测脚本：每次 trial 用干净目录，输出 pass@1、pass^k 和成本 |
| `tasks/fix_add/` | 示例评测任务：起始仓库、任务描述、在仓库外部运行的 grader |
| `调研笔记/` | 写教程时的五份调研笔记，每条结论带日期和链接 |

### 快速开始

需要 Python 3.10 以上和一个 Anthropic API key。

```bash
pip install anthropic pytest
export ANTHROPIC_API_KEY=...
cp -r tasks/fix_add/repo /tmp/fix_add
python mini_harness.py "$(cat tasks/fix_add/prompt.txt)" --workdir /tmp/fix_add --require-tests
```

跑评测（默认每个任务 3 次，评测模式不会弹权限确认，只在一次性目录或容器里用）：

```bash
HARNESS_MODEL=claude-haiku-5-5 python mini_eval.py --trials 3
```

### 说明

- 工具层、权限门和 grader 已离线验证；与 Claude API 的端到端运行需要你自己配置 key 后执行。
- `run_command` 的只读白名单是按前缀的粗筛，拼接命令可以绕过，正式使用请放进容器或操作系统级沙箱。
- 教程中少数二手来源（播客里的数字、第三方排行榜快照）已在正文注明。
