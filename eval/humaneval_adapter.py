"""
HumanEval Benchmark Adapter for CodeAgent-MCP.

Evaluates the system on OpenAI's HumanEval benchmark (164 function completion tasks).
Uses the multi-agent pipeline (Planner+Coder+Reviewer) in no-mcp mode.

Usage:
    python eval/humaneval_adapter.py                    # run all 164 tasks
    python eval/humaneval_adapter.py --limit 20         # run first 20
    python eval/humaneval_adapter.py --provider default  # specify provider
"""

import asyncio
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.config import load_settings, load_agents_config
from src.core.llm_client import LLMClient


def load_humaneval(path: str = None) -> list[dict]:
    if path is None:
        path = str(Path(__file__).parent / "humaneval_problems.jsonl")
    problems = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                problems.append(json.loads(line))
    return problems


def strip_markdown(text: str) -> str:
    text = text.strip()
    blocks = re.findall(r'```(?:python)?\s*(.*?)```', text, re.DOTALL)
    if blocks:
        return blocks[0].strip()
    return text


def normalize_indent(code: str) -> str:
    code = code.replace('\t', '    ')
    lines = code.split('\n')
    non_empty = [l for l in lines if l.strip()]
    if not non_empty:
        return code
    min_indent = min(len(l) - len(l.lstrip()) for l in non_empty)
    dedented = []
    for l in lines:
        if l.strip():
            dedented.append('    ' + l[min_indent:])
        else:
            dedented.append('')
    return '\n'.join(dedented)


def extract_body_after_sig(code: str, entry_point: str) -> str | None:
    sig_pattern = rf'def\s+{re.escape(entry_point)}\s*\('
    match = re.search(sig_pattern, code)
    if not match:
        return None

    rest = code[match.start():]
    depth = 0
    colon_pos = None
    for i, ch in enumerate(rest):
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
        elif ch == ':' and depth == 0 and i > 0:
            colon_pos = i
            break

    if colon_pos is None:
        return None

    body = rest[colon_pos + 1:]
    lines = body.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)

    doc_stripped = lines
    if doc_stripped and '"""' in doc_stripped[0]:
        in_doc = True
        for j, l in enumerate(doc_stripped):
            if j == 0:
                after_open = l.split('"""', 1)[1]
                if '"""' in after_open:
                    doc_stripped = doc_stripped[j+1:]
                    in_doc = False
                    break
            elif '"""' in l:
                doc_stripped = doc_stripped[j+1:]
                in_doc = False
                break
        if in_doc:
            doc_stripped = []

    if not doc_stripped:
        return None

    return '\n'.join(doc_stripped)


def build_candidates(completion: str, prompt: str, entry_point: str) -> list[str]:
    raw = strip_markdown(completion)
    candidates = []

    sig_pattern = rf'def\s+{re.escape(entry_point)}\s*\('
    has_sig = bool(re.search(sig_pattern, raw))

    if has_sig:
        candidates.append(raw)

        body = extract_body_after_sig(raw, entry_point)
        if body and body.strip():
            candidates.append(prompt + "\n" + normalize_indent(body))
            candidates.append(prompt + "\n" + body)

    normalized = normalize_indent(raw)
    candidates.append(prompt + "\n" + normalized)
    candidates.append(prompt + normalized)
    candidates.append(prompt + "\n" + raw)

    return candidates


def _exec_with_timeout(code: str, timeout: float) -> dict:
    import multiprocessing

    def run_code(code, result_queue):
        try:
            exec_globals = {}
            exec(code, exec_globals)
            result_queue.put(("passed", None))
        except Exception as e:
            result_queue.put(("failed", f"{type(e).__name__}: {str(e)}"))

    result_queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=run_code, args=(code, result_queue))
    p.start()
    p.join(timeout=timeout)

    if p.is_alive():
        p.kill()
        p.join()
        return {"passed": False, "error": "timeout"}

    if not result_queue.empty():
        status, error = result_queue.get()
        return {"passed": status == "passed", "error": error}

    return {"passed": False, "error": "no result"}


def check_correctness(problem: dict, completion: str, timeout: float = 10.0) -> dict:
    test_code = problem["test"] + f"\ncheck({problem['entry_point']})\n"
    raw = strip_markdown(completion)

    standalone = raw + "\n" + test_code
    result = _exec_with_timeout(standalone, timeout)
    if result["passed"]:
        return result
    standalone_err = result.get("error", "")
    if "SyntaxError" not in standalone_err and "IndentationError" not in standalone_err:
        return result

    candidates = build_candidates(completion, problem["prompt"], problem["entry_point"])

    last_error = standalone_err
    for candidate in candidates:
        full_code = candidate + "\n" + test_code
        result = _exec_with_timeout(full_code, timeout)
        if result["passed"]:
            return result
        err = result.get("error", "")
        if "SyntaxError" not in err and "IndentationError" not in err:
            return result
        last_error = err

    return {"passed": False, "error": last_error}

    result_queue = multiprocessing.Queue()
    p = multiprocessing.Process(target=run_code, args=(full_code, result_queue))
    p.start()
    p.join(timeout=timeout)

    if p.is_alive():
        p.kill()
        p.join()
        return {"passed": False, "error": "timeout"}

    if not result_queue.empty():
        status, error = result_queue.get()
        return {"passed": status == "passed", "error": error}

    return {"passed": False, "error": "no result"}


async def solve_problem_single(problem: dict, llm: LLMClient) -> str:
    messages = [
        {"role": "system", "content": (
            "You are an expert Python programmer. "
            "Complete the given function and output the COMPLETE function including its signature, docstring, and implementation. "
            "Use exactly 4 spaces for indentation. "
            "Do NOT wrap the code in markdown code blocks. "
            "Do NOT add any explanation, just the function code."
        )},
        {"role": "user", "content": f"Complete this function:\n\n{problem['prompt']}"},
    ]

    response = await llm.chat(messages, temperature=0.0)
    return response["content"]


async def solve_problem_multi(problem: dict, settings: dict, agents_config: dict, provider: str) -> tuple[str, int]:
    from src.core.orchestrator import Orchestrator
    from src.agents import PlannerAgent, CoderAgent, ReviewerAgent

    llm = LLMClient.from_settings(provider, settings)
    planner = PlannerAgent(agents_config["planner"], llm)
    coder = CoderAgent(agents_config["coder"], llm, mcp_manager=None)
    reviewer = ReviewerAgent(agents_config["reviewer"], llm)
    orchestrator = Orchestrator(
        planner=planner, coder=coder, reviewer=reviewer,
        config=settings["orchestrator"],
    )

    requirement = (
        f"Complete the following Python function. Output the complete function including signature.\n\n"
        f"{problem['prompt']}\n\n"
        f"The function should pass these test patterns: {problem['entry_point']}"
    )

    result = await orchestrator.run(requirement)
    code = ""
    for r in result.results:
        if r.get("code"):
            code += r["code"] + "\n"

    tokens = planner.total_tokens_used + coder.total_tokens_used + reviewer.total_tokens_used
    return code, tokens


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--provider", default="default")
    parser.add_argument("--mode", choices=["single", "multi"], default="single",
                        help="single=Coder only, multi=Planner+Coder+Reviewer")
    parser.add_argument("--output", default="eval/results")
    args = parser.parse_args()

    problems = load_humaneval()
    if args.limit:
        problems = problems[:args.limit]

    settings = load_settings()
    agents_config = load_agents_config()
    llm = LLMClient.from_settings(args.provider, settings)

    print(f"HumanEval Benchmark: {len(problems)} problems")
    print(f"Provider: {args.provider} | Mode: {args.mode}")
    print("-" * 60)

    results = []
    passed = 0
    total_tokens = 0
    start_all = time.time()

    for i, problem in enumerate(problems):
        task_id = problem["task_id"]
        try:
            start = time.time()

            if args.mode == "single":
                completion = await solve_problem_single(problem, llm)
                tokens_used = 0
            else:
                completion, tokens_used = await solve_problem_multi(
                    problem, settings, agents_config, args.provider
                )

            elapsed = time.time() - start
            total_tokens += tokens_used

            check = check_correctness(problem, completion)

            if check["passed"]:
                passed += 1
                status = "PASS"
            else:
                status = "FAIL"

            results.append({
                "task_id": task_id,
                "entry_point": problem["entry_point"],
                "passed": check["passed"],
                "error": check.get("error"),
                "tokens": tokens_used,
                "elapsed": round(elapsed, 1),
            })

            print(f"  [{i+1}/{len(problems)}] {task_id} ({problem['entry_point']}): {status} ({elapsed:.1f}s)")

        except Exception as e:
            results.append({
                "task_id": task_id,
                "entry_point": problem["entry_point"],
                "passed": False,
                "error": f"{type(e).__name__}: {str(e)}",
            })
            print(f"  [{i+1}/{len(problems)}] {task_id}: ERROR - {e}")

    elapsed_all = time.time() - start_all
    pass_rate = passed / len(problems) if problems else 0

    print("\n" + "=" * 60)
    print("HUMANEVAL RESULTS")
    print("=" * 60)
    print(f"pass@1: {passed}/{len(problems)} ({pass_rate:.1%})")
    print(f"Total time: {elapsed_all:.0f}s")
    if total_tokens:
        print(f"Total tokens: {total_tokens:,}")

    os.makedirs(args.output, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(args.output, f"humaneval_{args.provider}_{args.mode}_{timestamp}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "benchmark": "humaneval",
            "timestamp": timestamp,
            "config": {"provider": args.provider, "mode": args.mode},
            "summary": {
                "total": len(problems),
                "passed": passed,
                "pass_at_1": round(pass_rate, 4),
                "total_tokens": total_tokens,
                "elapsed_seconds": round(elapsed_all, 1),
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
