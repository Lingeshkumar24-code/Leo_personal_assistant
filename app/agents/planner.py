"""
Planner (§17 Task Manager / pipeline: INTENT -> PLANNER -> TOOL SELECTION).

Given a user instruction and the set of available tools, ask the AI provider
which tool(s) to call and with what arguments, using real tool_call() /
structured_output() against the configured provider — never a hardcoded
if/else guess of what the user "probably" meant.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.providers.base import AIProvider, Message, ProviderError
from app.tools.registry import ToolRegistry


@dataclass
class PlannedStep:
    tool_name: str
    arguments: dict
    rationale: str = ""


@dataclass
class Plan:
    steps: list[PlannedStep]
    direct_response: str = ""  # set when no tool call is needed, just an answer


SYSTEM_PROMPT = """You are LEO's planning module, the reasoning core of a desktop AI \
assistant. Given a user's instruction and a list of available tools, decide which \
tool(s) to call, in order, to satisfy the request.

RULES:
1. ALWAYS use tools for actions (opening apps, browsing, files, documents, system commands, etc.)
2. ONLY respond with plain text (no tool calls) for: questions, small talk, explanations, or things outside your capabilities
3. When user refers to screen content ("this", "the error", "my screen"), call screen.look FIRST
4. Chain multiple tools when needed (e.g., open app -> wait -> type)
5. Be specific with tool arguments

Examples:
User: "open notepad"
-> Call computer.open_application with {"app_name": "notepad"}

User: "create a word document with hello world"
-> Call documents.create_report with {"title": "Document", "content": "hello world", "output_path": "document.docx"}

User: "search for python tutorials on youtube"
-> Call browser.open with {"url": "https://www.youtube.com/results?search_query=python+tutorials"}

User: "what time is it"
-> Respond directly: "I don't have access to real-time clock. Check your system clock."

User: "take a screenshot"
-> Call screen.look with {}

If a tool is needed, YOU MUST CALL IT. Never describe what you would do - do it via tool call.
"""


class Planner:
    def __init__(self, provider: AIProvider, registry: ToolRegistry):
        self.provider = provider
        self.registry = registry

    def plan(self, user_instruction: str, conversation: list[dict[str, str]] | None = None) -> Plan:
        messages = [Message(role="system", content=SYSTEM_PROMPT)]
        for turn in (conversation or [])[-6:]:
            messages.append(Message(role=turn["role"], content=turn["content"]))
        messages.append(Message(role="user", content=user_instruction))

        tool_specs = self.registry.as_tool_specs()
        try:
            result = self.provider.tool_call(messages, tools=tool_specs)
        except ProviderError as e:
            # Provider unreachable/misconfigured: surface it, don't fabricate a plan.
            return Plan(steps=[], direct_response=f"I couldn't reach the AI provider: {e}")

        if not result.tool_calls:
            return Plan(steps=[], direct_response=result.text or "I'm not sure how to help with that yet.")

        steps = [PlannedStep(tool_name=tc.name, arguments=tc.arguments) for tc in result.tool_calls]
        return Plan(steps=steps, direct_response=result.text)
