"""mini_eval.py: 一个最小的 harness 评测脚本(第 7 课)。

目录约定:
  tasks/<name>/prompt.txt   给 agent 的任务描述
  tasks/<name>/repo/        起始仓库(每次 trial 拷贝到临时目录, 保证干净环境)
  tasks/<name>/check.py     grader: 从仓库外部检查结果, 退出码 0 = 通过

用法:   HARNESS_MODEL=claude-haiku-5-5 python mini_eval.py --trials 3
输出:   results.jsonl(每次 trial 一行, 含完整轨迹路径、usage、成本) + 终端汇总表
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

import mini_harness as H

os.environ["HARNESS_YOLO"] = "1"   # 评测不能交互; 所以只在一次性目录/容器里跑


def run_trial(task_dir: pathlib.Path, trial: int) -> dict:
    sandbox = pathlib.Path(tempfile.mkdtemp(prefix=f"{task_dir.name}-{trial}-"))
    shutil.copytree(task_dir / "repo", sandbox / "repo")
    H.WORKDIR = (sandbox / "repo").resolve()            # 每次 trial 一个全新工作目录
    prompt = (task_dir / "prompt.txt").read_text()
    t0 = time.time()
    try:
        res = H.run(prompt, log_path=str(sandbox / "trajectory.jsonl"))
        error = None
    except Exception as e:                              # harness 自身崩溃也要记录, 不能让整轮评测中断
        res, error = {"stop": "exception", "steps": 0, "cost_usd": 0.0}, repr(e)
    check = subprocess.run([sys.executable, str(task_dir / "check.py"), str(sandbox / "repo")],
                           capture_output=True, text=True, timeout=120)
    return {
        "task": task_dir.name, "trial": trial, "pass": check.returncode == 0,
        "stop": res["stop"], "steps": res["steps"], "cost_usd": res["cost_usd"],
        "seconds": round(time.time() - t0, 1), "error": error,
        "check_output": (check.stdout + check.stderr)[-500:],
        "trajectory": str(sandbox / "trajectory.jsonl"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default="tasks")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--out", default="results.jsonl")
    args = ap.parse_args()

    task_dirs = sorted(p for p in pathlib.Path(args.tasks).iterdir() if (p / "prompt.txt").exists())
    rows = []
    with open(args.out, "a") as f:
        for task_dir in task_dirs:
            for t in range(args.trials):
                rec = run_trial(task_dir, t)
                rows.append(rec)
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{rec['task']:<24} trial {t}  pass={rec['pass']}  stop={rec['stop']}  "
                      f"steps={rec['steps']}  ${rec['cost_usd']:.3f}  {rec['seconds']}s")

    print("\n{:<24} {:>7} {:>7} {:>9} {:>7}".format("task", "pass@1", "pass^k", "avg_cost", "steps"))
    for task_dir in task_dirs:
        rs = [r for r in rows if r["task"] == task_dir.name]
        pass_at_1 = sum(r["pass"] for r in rs) / len(rs)          # 单次成功率的估计
        pass_pow_k = float(all(r["pass"] for r in rs))             # k 次全成功才算稳定
        print("{:<24} {:>7.0%} {:>7.0%} {:>9.3f} {:>7.1f}".format(
            task_dir.name, pass_at_1, pass_pow_k,
            sum(r["cost_usd"] for r in rs) / len(rs), sum(r["steps"] for r in rs) / len(rs)))


if __name__ == "__main__":
    main()
