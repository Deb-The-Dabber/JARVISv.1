import json
import re
import threading
import time
import uuid
from pathlib import Path
from dataclasses import dataclass, field
from event_bus import publish

# ── Goal sanitization: strip bypass/PII before passing to sub-agents ──
_BYPASS_PATTERNS = re.compile(
    r"(?i)(bypass|skip|ignore|disable|circumvent|override|suppress)"
    r"\s*(permission|prompt|confirm|approval|check|gate|block|safety|restrict)"
    r"|"
    r"(don'?t|do not|never)\s*(wait|ask|prompt|confirm|check|halt)"
    r"|"
    r"(just|simply|automatically)\s*(go|do|proceed|execute|run)\s*(without|ahead|freely)"
    r"|"
    r"\bjust go ahead\b"
)
_PII_PATTERNS = re.compile(
    r"\b\d{13,19}\b"  # credit card / long numbers
    r"|\b\d{3}-\d{2}-\d{4}\b"  # SSN
    r"|\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"  # email
)


def _sanitize_goal(goal: str) -> str:
    goal = _BYPASS_PATTERNS.sub("[redacted]", goal)
    goal = _PII_PATTERNS.sub("[redacted]", goal)
    return goal


AGENT_TRIGGERS = [
    "discord",
    "send a message",
    "send the chat",
    "open the chat",
    "read the most recent",
    "fix",
    "debug",
    "refactor",
    "rewrite",
    "build",
    "create and",
    "write a script",
    "write code",
    "implement",
    "edit the file",
    "update the file",
    "read and",
    "scan and",
    "find and fix",
    "look through",
    "go through",
    "check all",
    "analyse",
    "analyze",
    "step by step",
    "automatically",
    "keep trying",
    "until it works",
    "iterate",
]

PLANNER_TRIGGERS = [
    "complex",
    "multi-step",
    "research",
    "investigate",
    "compare",
    "find and",
    "gather",
    "collect",
    "organize",
    "prepare a report",
    "comprehensive",
    "thorough",
    "plan",
]

MAX_STEPS = 30

# ── Think → Act → Evaluate: Plan dataclasses ──


@dataclass
class PlanStep:
    step_id: str = ""
    goal: str = ""
    tool_hint: str = ""
    args: dict = field(default_factory=dict)
    status: str = "pending"
    result: str = ""
    evaluation: str = ""


@dataclass
class Plan:
    plan_id: str = ""
    original_goal: str = ""
    steps: list[PlanStep] = field(default_factory=list)
    current_step: int = 0
    status: str = "running"
    final_answer: str = ""


_plan_store: dict[str, Plan] = {}
_plan_lock = threading.Lock()


def _register_plan(p: Plan):
    with _plan_lock:
        _plan_store[p.plan_id] = p


def get_plan(plan_id: str) -> Plan | None:
    with _plan_lock:
        return _plan_store.get(plan_id)


def list_plans() -> list[dict]:
    with _plan_lock:
        return [
            {
                "plan_id": p.plan_id,
                "goal": p.original_goal[:100],
                "status": p.status,
                "steps": len(p.steps),
                "current_step": p.current_step,
            }
            for p in _plan_store.values()
        ]


def needs_planner(text: str) -> bool:
    """Check if the user's request is complex enough to warrant a planner agent."""
    t = (text or "").lower()
    return any(trigger in t for trigger in PLANNER_TRIGGERS)


def _create_plan(goal: str, ask_llm_fn) -> Plan | None:
    """Use the LLM to decompose a goal into steps."""
    prompt = (
        "You are Jarvis's planner. Given a user goal, break it into a sequence of 2-6 discrete steps. "
        "Each step should use exactly one tool. Respond ONLY with a JSON array of steps.\n\n"
        f"Goal: {goal}\n\n"
        "Format:\n"
        "[\n"
        '  {"step_id": "1", "goal": "what to accomplish", "tool_hint": "suggested_tool_name",\n'
        '   "args": {"query": "search term", "app_name": "Safari"}},\n'
        "  ...\n"
        "]\n"
        "Rules:\n"
        "- Each step must be achievable with a single tool call\n"
        "- tool_hint must match a known tool name (browser_navigate, web_search, open_app, etc.)\n"
        "- Each step MUST include an 'args' object with ALL required parameters for that tool\n"
        '- Example: web_search needs args={"query": "..."}, open_app needs args={"app_name": "..."}\n'
        "- Return NOTHING but the JSON array\n"
    )
    try:
        raw = ask_llm_fn(prompt)
        raw_clean = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
        steps_data = json.loads(raw_clean)
        if not isinstance(steps_data, list):
            raise ValueError("Expected array")
        plan = Plan(
            plan_id=uuid.uuid4().hex[:8],
            original_goal=goal,
            steps=[PlanStep(**s) for s in steps_data],
        )
        _register_plan(plan)
        return plan
    except Exception:
        return None


def _evaluate_step(step: PlanStep, ask_llm_fn) -> str:
    """LLM-as-judge: evaluate whether a step succeeded."""
    prompt = (
        "You are Jarvis's step evaluator. Determine if this step succeeded.\n\n"
        f"Step goal: {step.goal}\n"
        f"Tool: {step.tool_hint}\n"
        f"Result: {step.result[:500]}\n\n"
        "Respond with a single word: SUCCESS or FAILURE. Then a brief reason."
    )
    try:
        raw = ask_llm_fn(prompt)
        if raw.strip().upper().startswith("SUCCESS"):
            return "success"
        return "failure"
    except Exception:
        return "failure" if "error" in step.result.lower() else "success"


def _generate_final_answer(plan: Plan, ask_llm_fn) -> str:
    """Synthesize a final answer from all completed steps."""
    steps_text = "\n".join(f"Step {s.step_id}: {s.goal} → {s.evaluation}\n  Result: {s.result[:200]}" for s in plan.steps if s.result)
    prompt = f"Summarize what was accomplished based on these step results.\nOriginal goal: {plan.original_goal}\n\n{steps_text}\n\nProvide a concise summary of what was done and key findings."
    try:
        return ask_llm_fn(prompt) or "Completed."
    except Exception:
        return "Completed."


def run_planner_loop(goal: str, execute_tool_fn, ask_llm_fn, speak_fn=None) -> str:
    # Record start time for duration metrics
    start_time = time.time()
    """Think → Act → Evaluate loop with separate planner agent."""

    if speak_fn:
        try:
            speak_fn("Let me think through the best approach for this.")
        except Exception:
            pass

    # THINK: Create a plan
    plan = _create_plan(goal, ask_llm_fn)
    if not plan:
        return "I couldn't create a plan for this task. Try being more specific or use the direct agent instead."

    if speak_fn:
        try:
            speak_fn(f"Okay, I have a {len(plan.steps)}-step plan. Let me start working through it.")
        except Exception:
            pass

    # ACT → EVALUATE loop
    for step_idx, step in enumerate(plan.steps):
        plan.current_step = step_idx
        step.status = "running"

        # Check if we have a known tool for this hint
        tool_name = step.tool_hint
        args = step.args if step.args else {}

        try:
            result = execute_tool_fn(tool_name, args)
            step.result = str(result)
        except Exception as e:
            step.result = f"Tool error: {e}"

        # EVALUATE: Check if step succeeded
        step.evaluation = _evaluate_step(step, ask_llm_fn)
        step.status = "completed" if step.evaluation == "success" else "failed"

        # Re-plan if step failed (max 2 retries per step)
        if step.status == "failed":
            retry_prompt = (
                f"Step '{step.goal}' failed. Result: {step.result[:300]}\n"
                "Suggest an alternative approach or tool to accomplish this goal. "
                f'Respond with: {{"tool": "tool_name", "args": {{"param": "value"}}, "reason": "why"}}\n'
                "Include ALL required arguments for the tool in the args field."
            )
            try:
                raw = ask_llm_fn(retry_prompt)
                raw_clean = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
                retry = json.loads(raw_clean)
                alt_tool = retry.get("tool", "")
                alt_args = retry.get("args", {})
                if alt_tool:
                    try:
                        result = execute_tool_fn(alt_tool, alt_args)
                        step.result = str(result)
                        step.evaluation = _evaluate_step(step, ask_llm_fn)
                        if step.evaluation == "success":
                            step.status = "completed"
                    except Exception as e2:
                        step.result += f" | Retry failed: {e2}"
            except Exception:
                pass

        # Announce progress for multi-step plans
        if speak_fn and len(plan.steps) > 1:
            status_msg = f"Step {step_idx + 1} of {len(plan.steps)}: {step.evaluation}"
            try:
                speak_fn(status_msg)
            except Exception:
                pass

    # Synthesize final answer
    plan.status = "completed"
    plan.final_answer = _generate_final_answer(plan, ask_llm_fn)
    # Emit planner completed event
    publish("subagent_completed", {
        "agent_id": "planner",  # identifier for planner
        "goal": goal,
        "final_answer": plan.final_answer,
        "steps": [
            {"tool": s.tool_hint, "status": "success" if s.evaluation == "success" else "failed"}
            for s in plan.steps
        ],
        "duration": time.time() - start_time,
        "timestamp": time.time(),
    })
    return plan.final_answer


# ── Success/Failure detection ──

# Agent success detection — scored terms
SUCCESS_TERMS = {
    "opened",
    "sent",
    "completed",
    "created",
    "started",
    "playing",
    "navigated",
    "remembered",
    "saved",
    "quit",
    "closed",
    "delivered",
    "found",
    "results",
    "added",
    "marked",
    "done",
    "success",
    "launched",
    "focused",
    "loaded",
    "navigating",
    "posted",
    "resumed",
    "skipped",
    "next",
    "timer set",
    "countdown",
    "goal added",
    "stored",
    "written",
    "edited",
    "updated",
    "modified",
    "exit code 0",
    "temperature",
    "humidity",
    "wind",
    "cpu",
    "ram",
    "disk",
    "percent",
    "killed",
}
FAILURE_TERMS = {
    "error",
    "failed",
    "could not",
    "timeout",
    "exception",
    "denied",
    "not found",
    "permission",
    "unavailable",
    "invalid",
    "missing",
    "traceback",
    "cannot",
    "unable",
    "refused",
    "aborted",
    "no such",
}


def _is_success_result(tool_name: str, result: str) -> bool:
    """Score-based success detection. Primary = positive terms; fallback = non-empty without failure."""
    r = result.lower()
    # Score positive and negative terms
    pos_score = sum(1 for t in SUCCESS_TERMS if t in r)
    neg_score = sum(1 for t in FAILURE_TERMS if t in r)
    if pos_score or neg_score:
        return pos_score > neg_score
    # Fallback: non-empty result is likely success
    return bool(r.strip())


_agent_store: dict[str, "Agent"] = {}
_store_lock = threading.Lock()
AGENTS_DB = Path.home() / ".jarvis" / "agents.json"


def _save_agents():
    """Persist agent store to JSON file."""
    try:
        AGENTS_DB.parent.mkdir(parents=True, exist_ok=True)
        with _store_lock:
            data = {aid: a.to_dict() for aid, a in _agent_store.items()}
        with open(AGENTS_DB, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _load_agents():
    """Load agent store from JSON file on startup."""
    if not AGENTS_DB.exists():
        return
    try:
        with open(AGENTS_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        with _store_lock:
            for aid, adict in data.items():
                # Create a minimal Agent-like object with just the dict data
                # We store as dict since full Agent reconstruction needs tools/execute_fn
                _agent_store[aid] = adict
    except Exception:
        pass


# Load persisted agents on module import
_load_agents()


class Agent:
    def __init__(self, goal: str, tools: dict = None, max_iterations: int = MAX_STEPS):
        self.id = uuid.uuid4().hex[:8]
        self.goal = goal
        self.tools = tools or {}
        self.max_iterations = max_iterations
        self.steps = []
        self.last_result = ""
        self.already_called: set[tuple[str, str]] = set()
        self.fail_counts = {}
        self.status = "running"
        self.error = None
        self.final_answer = ""
        self.parent_id = None

    def checkpoint(self):
        try:
            from procedural_memory import save_procedure

            summary = "; ".join(f"{s['tool']}:{'ok' if s['success'] else 'fail'}" for s in self.steps[-5:])
            save_procedure(
                trigger=f"agent_{self.id}",
                steps=[s["tool"] for s in self.steps if s.get("tool")],
                description=f"Agent #{self.id}: {self.goal[:80]} ({summary})",
            )
        except Exception:
            pass

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal[:200],
            "status": self.status,
            "step_count": len(self.steps),
            "successful_steps": sum(1 for s in self.steps if s.get("success")),
            "tools_used": sorted(set(s["tool"] for s in self.steps if s.get("tool"))),
            "final_answer": self.final_answer[:200] if self.final_answer else "",
            "error": self.error,
            "parent_id": self.parent_id,
        }


def _register_agent(a: Agent):
    with _store_lock:
        _agent_store[a.id] = a
    _save_agents()


def get_agent(agent_id: str) -> Agent | dict | None:
    with _store_lock:
        return _agent_store.get(agent_id)


def list_agents() -> list[dict]:
    with _store_lock:
        result = []
        for a in _agent_store.values():
            if hasattr(a, 'to_dict'):
                result.append(a.to_dict())
            elif isinstance(a, dict):
                result.append(a)
        return result


def stop_agent(agent_id: str) -> bool:
    with _store_lock:
        if agent_id in _agent_store:
            agent = _agent_store[agent_id]
            if hasattr(agent, 'status'):
                agent.status = "stopped"
            elif isinstance(agent, dict):
                agent["status"] = "stopped"
            _save_agents()
            return True
        return False


def needs_agent_loop(text: str) -> bool:
    t = (text or "").lower()
    return any(trigger in t for trigger in AGENT_TRIGGERS)


def _parse_decision(raw: str) -> dict:
    if not raw:
        return {"thought": "", "tool": "", "args": {}, "done": True, "final_answer": "No response from model."}
    cleaned = re.sub(r"```(?:json)?", "", raw).replace("```", "").strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return {
        "thought": "Model returned non-JSON response.",
        "tool": "",
        "args": {},
        "done": True,
        "final_answer": raw.strip(),
    }


def _build_prompt(goal: str, steps: list, last_result: str, already_called: set = None) -> str:
    recent = steps[-5:]
    recent_text = "\n".join(f"{i + 1}. tool={step.get('tool')} success={step.get('success')} result={step.get('result', '')[:200]}" for i, step in enumerate(recent))
    already_text = ""
    if already_called:
        already_text = "\nAlready executed this turn — do NOT repeat:\n" + "\n".join(f"  - {t}({a})" for t, a in sorted(already_called))
    return (
        "You are Jarvis running an autonomous agent loop. "
        "Respond ONLY with a single JSON object — no explanation, no backticks.\n"
        f"Goal: {goal}\n\n"
        "Recent steps:\n"
        f"{recent_text if recent_text else '(none yet)'}\n\n"
        f"Last result: {last_result or '(none yet)'}\n"
        f"{already_text}\n\n"
        "Required JSON format:\n"
        '{{"thought": "brief reasoning", "tool": "exact_tool_name", '
        '"args": {{}}, "done": false, "final_answer": ""}}\n\n'
        "Rules:\n"
        "- done=true only when the goal is fully complete or cannot continue\n"
        "- If done=true, put the full response in final_answer and leave tool empty\n"
        "- Pick exactly one tool per step\n"
        "- args must be a valid JSON object\n"
        "- Never call the same tool with the same arguments twice\n"
        "- Return NOTHING except the JSON object"
    )


def _synthesize_from_steps(goal, steps) -> str:
    lines = [f"Agent summary for: {goal}"]
    successful = [step for step in steps if step.get("success")]
    if not successful:
        lines.append("- No successful tool steps completed.")
    for step in successful:
        tool = step.get("tool", "unknown")
        result = str(step.get("result", "")).strip()
        if len(result) > 180:
            result = result[:177] + "..."
        lines.append(f"- {tool}: {result or 'completed'}")
    if len(steps) >= MAX_STEPS:
        lines.append("- Stopped after reaching the maximum step limit.")
    return "\n".join(lines)


def get_agent_stats(steps) -> dict:
    tools = [step.get("tool") for step in steps if step.get("tool")]
    return {
        "total_steps": len(steps),
        "tools_used": sorted(set(tools)),
        "successful_steps": sum(1 for step in steps if step.get("success")),
    }


def _canonical_args_key(args: dict) -> str:
    return str(sorted((k, str(v)) for k, v in (args or {}).items()))


def run_agent_loop(goal: str, execute_tool_fn, ask_llm_fn, speak_fn=None, max_iterations: int = 30) -> str:
    # Record start time for duration metrics
    start_time = time.time()
    agent = Agent(goal=goal, max_iterations=max_iterations)
    _register_agent(agent)

    if speak_fn:
        try:
            speak_fn("On it, let me work through this step by step.")
        except Exception:
            pass

    for step_num in range(1, agent.max_iterations + 1):
        if agent.status == "stopped":
            agent.final_answer = _synthesize_from_steps(goal, agent.steps)
            return agent.final_answer

        prompt = _build_prompt(goal, agent.steps, agent.last_result, agent.already_called)
        raw_decision = ask_llm_fn(prompt)
        decision = _parse_decision(raw_decision)

        if decision.get("done"):
            agent.final_answer = (decision.get("final_answer") or "").strip()
            agent.final_answer = agent.final_answer or _synthesize_from_steps(goal, agent.steps)
            agent.status = "completed"
            agent.checkpoint()
            return agent.final_answer

        tool_name = (decision.get("tool") or "").strip()
        args = decision.get("args") or {}
        if not isinstance(args, dict):
            args = {}

        if not tool_name:
            agent.steps.append(
                {
                    "tool": "",
                    "args": args,
                    "success": False,
                    "result": "No tool selected.",
                    "thought": decision.get("thought", ""),
                }
            )
            agent.last_result = "No tool selected."
            continue

        arg_key = _canonical_args_key(args)
        if (tool_name, arg_key) in agent.already_called:
            agent.last_result = f"Skipped {tool_name}: already called with these args."
            agent.steps.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "success": False,
                    "result": agent.last_result,
                    "thought": decision.get("thought", ""),
                }
            )
            continue

        if agent.fail_counts.get(tool_name, 0) >= 2:
            agent.last_result = f"Skipped {tool_name}: failed too many times."
            agent.steps.append(
                {
                    "tool": tool_name,
                    "args": args,
                    "success": False,
                    "result": agent.last_result,
                    "thought": decision.get("thought", ""),
                }
            )
            continue

        # Rapid-repeat prevention — skip if same tool used ≥2 times in last 3 steps
        HIGH_FREQ_TOOLS = {"browser_navigate", "open_app", "quit_app", "web_search", "spotify_play", "spotify_skip"}
        if tool_name in HIGH_FREQ_TOOLS and len(agent.steps) >= 2:
            last_tools = [s.get("tool") for s in agent.steps[-3:] if s.get("tool")]
            if last_tools.count(tool_name) >= 2:
                agent.last_result = f"Skipped {tool_name}: used {last_tools.count(tool_name)}x in last 3 steps."
                agent.steps.append(
                    {
                        "tool": tool_name,
                        "args": args,
                        "success": False,
                        "result": agent.last_result,
                        "thought": decision.get("thought", ""),
                    }
                )
                continue

        print(f"[AGENT] Step {step_num}: {tool_name}({args})")

        try:
            result = execute_tool_fn(tool_name, args)
            result_str = str(result)
            success = _is_success_result(tool_name, result_str)
            if not success:
                agent.fail_counts[tool_name] = agent.fail_counts.get(tool_name, 0) + 1
            agent.last_result = result_str
        except Exception as e:
            success = False
            agent.fail_counts[tool_name] = agent.fail_counts.get(tool_name, 0) + 1
            agent.last_result = f"Tool execution error: {e}"

        agent.already_called.add((tool_name, arg_key))
        agent.steps.append(
            {
                "tool": tool_name,
                "args": args,
                "success": success,
                "result": agent.last_result,
                "thought": decision.get("thought", ""),
            }
        )

        if step_num % 5 == 0:
            # Emit progress event for sub‑agent
            publish("subagent_progress", {
                "agent_id": agent.id,
                "step": step_num,
                "tool": tool_name,
                "status": "running",
            })
            agent.checkpoint()

    agent.status = "completed"
    agent.final_answer = _synthesize_from_steps(goal, agent.steps)
    agent.checkpoint()
    # Emit sub‑agent completed event with summary
    publish("subagent_completed", {
        "agent_id": agent.id,
        "goal": goal,
        "final_answer": agent.final_answer,
        "steps": [
            {"tool": s.get("tool"), "status": "success" if s.get("success") else "failed"}
            for s in agent.steps
        ],
        "duration": time.time() - start_time,
        "timestamp": time.time(),
    })
    return agent.final_answer


def spawn_agent(goal: str, tools: dict = None) -> str:
    goal = _sanitize_goal(goal)
    sub = Agent(goal=goal, tools=tools)
    _register_agent(sub)
    # Emit sub‑agent started event
    publish("subagent_started", {"agent_id": sub.id, "goal": goal, "timestamp": time.time()})
    return sub.id


# ── Tool registration ──


def _agent_spawn_tool(goal: str) -> str:
    aid = spawn_agent(goal)
    return f"Spawned sub-agent [{aid}] for: {goal[:100]}"


def _list_agents_tool() -> str:
    agents = list_agents()
    if not agents:
        return "No sub-agents currently running."
    lines = [f"{len(agents)} sub-agent(s):"]
    for a in agents:
        lines.append(f"  [{a['id']}] {a['goal'][:80]} — {a['status']} ({a['successful_steps']}/{a['step_count']} steps ok)")
    return "\n".join(lines)


def _get_agent_status_tool(agent_id: str) -> str:
    agent = get_agent(agent_id)
    if not agent:
        return f"No agent found with id '{agent_id}'."
    d = agent.to_dict()
    lines = [
        f"Agent [{d['id']}]",
        f"  Goal: {d['goal']}",
        f"  Status: {d['status']}",
        f"  Steps: {d['successful_steps']}/{d['step_count']} successful",
        f"  Tools used: {', '.join(d['tools_used']) if d['tools_used'] else 'none'}",
    ]
    if d.get("error"):
        lines.append(f"  Error: {d['error']}")
    if d.get("final_answer"):
        lines.append(f"  Final: {d['final_answer']}")
    if d.get("parent_id"):
        lines.append(f"  Parent: {d['parent_id']}")
    return "\n".join(lines)


AGENT_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "agent_spawn",
            "description": "Launch a sub-agent for a multi-step goal. The agent runs autonomously and returns a summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "goal": {"type": "string", "description": "The goal or task for the sub-agent to complete"},
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_agents",
            "description": "List all sub-agents with IDs, goals, and status. Use this before calling get_agent_status.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_agent_status",
            "description": "Get detailed status of a sub-agent by ID. Returns goal, steps, tools, errors, final answer.",
            "parameters": {
                "type": "object",
                "properties": {
                    "agent_id": {"type": "string", "description": "The 8-character hex agent ID (e.g. 'a1b2c3d4')"},
                },
                "required": ["agent_id"],
            },
        },
    },
]

AGENT_TOOLS = {
    "agent_spawn": _agent_spawn_tool,
    "list_agents": _list_agents_tool,
    "get_agent_status": _get_agent_status_tool,
}
