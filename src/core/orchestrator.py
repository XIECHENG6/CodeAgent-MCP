import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    plan: list[dict]
    results: list[dict]
    execution_log: list[dict]
    total_tokens: int = 0


class Orchestrator:
    def __init__(self, planner, coder, reviewer, config: dict):
        self.planner = planner
        self.coder = coder
        self.reviewer = reviewer
        self.max_review_rounds = config.get("max_review_rounds", 3)
        self.review_threshold = config.get("review_threshold", 7.0)
        self.execution_log: list[dict] = []

    async def run(self, user_requirement: str) -> ExecutionResult:
        self.execution_log = []

        plan_output = await self.planner.run(user_requirement)
        tasks = self._parse_plan(plan_output)
        self._log("plan", {"raw_output": plan_output, "parsed_tasks": tasks})

        logger.info(f"[Orchestrator] Plan: {len(tasks)} tasks")

        results = []
        for i, task in enumerate(tasks):
            logger.info(f"[Orchestrator] Executing task {i+1}/{len(tasks)}: {task['description'][:60]}")
            task_result = await self._execute_task(task)
            results.append(task_result)

        total_tokens = (
            self.planner.total_tokens_used
            + self.coder.total_tokens_used
            + self.reviewer.total_tokens_used
        )

        return ExecutionResult(
            plan=tasks,
            results=results,
            execution_log=self.execution_log,
            total_tokens=total_tokens,
        )

    async def _execute_task(self, task: dict) -> dict:
        code_output = None
        review = None

        for attempt in range(self.max_review_rounds):
            if attempt == 0:
                coder_input = self.coder.format_input(task)
            else:
                coder_input = (
                    f"你之前的代码审查未通过 (得分: {review['score']}/10)。\n"
                    f"问题: {json.dumps(review['issues'], ensure_ascii=False)}\n"
                    f"建议: {json.dumps(review['suggestions'], ensure_ascii=False)}\n\n"
                    f"原始任务: {task['description']}\n"
                    f"请修改代码。"
                )

            code_output = await self.coder.run(coder_input)
            self._log("coder", {"task_id": task.get("task_id"), "attempt": attempt, "output_preview": code_output[:500]})

            reviewer_input = self.reviewer.format_input({
                "task": task,
                "code": code_output,
            })
            review_raw = await self.reviewer.run(reviewer_input)
            review = self._parse_review(review_raw)
            self._log("reviewer", {"task_id": task.get("task_id"), "attempt": attempt, "review": review})

            logger.info(f"  [Review] Attempt {attempt+1}: score={review['score']}, passed={review['passed']}")

            if review["passed"]:
                return {
                    "task": task,
                    "code": code_output,
                    "review": review,
                    "attempts": attempt + 1,
                    "status": "completed",
                }

        return {
            "task": task,
            "code": code_output,
            "review": review,
            "attempts": self.max_review_rounds,
            "status": "max_attempts_reached",
        }

    def _parse_plan(self, plan_text: str) -> list[dict]:
        parsed = self._extract_json(plan_text)
        if parsed and "tasks" in parsed:
            return parsed["tasks"]

        tasks = []
        lines = plan_text.strip().split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if re.match(r'^[\d]+[.)\-]', line):
                desc = re.sub(r'^[\d]+[.)\-]\s*', '', line)
                tasks.append({"task_id": f"T{i+1}", "description": desc, "dependencies": []})

        if not tasks:
            tasks = [{"task_id": "T1", "description": plan_text, "dependencies": []}]

        return tasks

    def _parse_review(self, review_text: str) -> dict:
        parsed = self._extract_json(review_text)
        if parsed and "score" in parsed:
            parsed.setdefault("passed", parsed["score"] >= self.review_threshold)
            parsed.setdefault("issues", [])
            parsed.setdefault("suggestions", [])
            parsed.setdefault("summary", "")
            return parsed

        score_match = re.search(r'(\d+\.?\d*)\s*/\s*10', review_text)
        score = float(score_match.group(1)) if score_match else 5.0

        return {
            "score": score,
            "passed": score >= self.review_threshold,
            "issues": [],
            "suggestions": [],
            "summary": review_text[:200],
        }

    def _extract_json(self, text: str) -> dict | None:
        if "```json" in text:
            match = re.search(r'```json\s*(.*?)```', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        if "```" in text:
            match = re.search(r'```\s*(.*?)```', text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1).strip())
                except json.JSONDecodeError:
                    pass
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _log(self, stage: str, data: dict):
        self.execution_log.append({"stage": stage, **data})
