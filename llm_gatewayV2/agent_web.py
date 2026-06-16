from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Literal, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field

from schemas import ChatRequest


SYSTEM_PROMPT = (
    "You are a helpful assistant in a ChatGPT-style web app. "
    "Use the available MCP tools when they help answer the user's question. "
    "For addition and subtraction, call the tools instead of doing the math mentally. "
    "For current temperature or weather in a city, call the get_temperature tool. "
    "If no tool is needed, answer directly and concisely."
)


class AgentMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AgentChatRequest(BaseModel):
    message: str
    history: list[AgentMessage] = Field(default_factory=list)
    provider: Optional[str] = None
    max_turns: int = 8


class AgentChatResponse(BaseModel):
    answer: str
    provider: str | None = None
    model: str | None = None
    turns: int
    trace: list[dict[str, Any]]


def _mcp_tool_to_v2(tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.inputSchema or {"type": "object", "properties": {}},
    }


async def _dispatch_tool_calls(session: ClientSession, tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    async def run_one(tool_call: dict[str, Any]) -> dict[str, Any]:
        result = await session.call_tool(tool_call["name"], tool_call.get("arguments") or {})
        text = result.content[0].text if result.content else ""
        return {
            "role": "tool",
            "tool_call_id": tool_call["id"],
            "tool_name": tool_call["name"],
            "content": text,
        }

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(run_one(tool_call)) for tool_call in tool_calls]
    return [task.result() for task in tasks]


def _messages_from_request(request: AgentChatRequest) -> list[dict[str, str]]:
    messages = [
        {"role": item.role, "content": item.content}
        for item in request.history[-16:]
        if item.content.strip()
    ]
    messages.append({"role": "user", "content": request.message.strip()})
    return messages


async def run_agent_chat(
    request: AgentChatRequest,
    gateway_chat: Callable[[ChatRequest], Awaitable[dict[str, Any]]],
) -> AgentChatResponse:
    """Run one web-chat answer.

    Every LLM turn goes through the gateway chat callable. The first turn can
    use gateway failover; after a provider succeeds, later turns in the same
    tool conversation are pinned to that provider to avoid mixing provider-
    specific tool-call metadata.
    """

    message = request.message.strip()
    if not message:
        raise ValueError("message cannot be empty")

    mcp_server = Path(__file__).resolve().parents[1] / "mcp_server.py"
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(mcp_server)],
    )

    trace: list[dict[str, Any]] = []
    messages = _messages_from_request(request)
    active_provider = request.provider or None
    last_provider = None
    last_model = None

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools = [_mcp_tool_to_v2(tool) for tool in mcp_tools]
            trace.append({
                "kind": "mcp_tools",
                "tools": [{"name": tool.name, "description": tool.description or ""} for tool in mcp_tools],
            })

            for turn in range(1, request.max_turns + 1):
                reply = await gateway_chat(ChatRequest(
                    messages=messages,
                    system=SYSTEM_PROMPT,
                    cache_system=True,
                    tools=tools,
                    tool_choice="auto",
                    reasoning="off",
                    provider=active_provider,
                    temperature=0,
                    max_tokens=1024,
                ))

                last_provider = reply.get("provider")
                last_model = reply.get("model")
                if active_provider is None:
                    active_provider = last_provider

                tool_calls = reply.get("tool_calls") or []
                trace.append({
                    "kind": "llm_call",
                    "turn": turn,
                    "provider": last_provider,
                    "model": last_model,
                    "latency_ms": reply.get("latency_ms"),
                    "input_tokens": reply.get("input_tokens"),
                    "output_tokens": reply.get("output_tokens"),
                    "stop_reason": reply.get("stop_reason"),
                    "text": reply.get("text") or "",
                    "tool_calls": tool_calls,
                })

                if not tool_calls:
                    return AgentChatResponse(
                        answer=(reply.get("text") or "").strip(),
                        provider=last_provider,
                        model=last_model,
                        turns=turn,
                        trace=trace,
                    )

                messages.append({
                    "role": "assistant",
                    "content": reply.get("text") or "",
                    "tool_calls": tool_calls,
                })

                tool_results = await _dispatch_tool_calls(session, tool_calls)
                for tool_call, tool_result in zip(tool_calls, tool_results):
                    trace.append({
                        "kind": "tool_call",
                        "turn": turn,
                        "name": tool_call.get("name"),
                        "arguments": tool_call.get("arguments") or {},
                        "result": tool_result.get("content", ""),
                    })
                messages.extend(tool_results)

    raise RuntimeError(f"agent exceeded max_turns={request.max_turns}")
