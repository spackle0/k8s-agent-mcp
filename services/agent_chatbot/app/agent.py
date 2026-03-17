# agent.py
#
# Interactive Kubernetes troubleshooting chatbot. Connects to the MCP server
# once at startup, then runs a conversation loop where the user can ask
# free-form questions. The LLM reasons over the available tools and may call
# them multiple times per turn before producing a final answer.
#
# Flow per turn:
#   1. Read user input.
#   2. Agentic loop: call LLM → execute any tool calls → repeat until the
#      LLM stops requesting tools and produces a final answer.
#   3. Print the answer and wait for the next input.
#
# Type 'quit' or 'exit' (or Ctrl+C) to end the session.

from ollama import ChatResponse, chat

import asyncio
import os

from fastmcp import Client
from fastmcp.exceptions import ToolError

from typing import Any

# Base URL for the FastMCP server's streamable-HTTP endpoint.
# Override with MCP_SERVER_URL env var when running in Docker.
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp")

SYSTEM_PROMPT = (
    "You are a Kubernetes troubleshooting assistant. "
    "Use the provided tools to answer questions about the cluster. "
    "Report tool results directly and concisely. "
    "Do not suggest kubectl commands or external tools."
)

MODEL = "llama3.1:8b"


def tool_to_dict(tool: Any) -> dict:
    """Convert an MCP Tool object into the dict format Ollama expects.

    Ollama's chat() call requires tools in OpenAI-style function-calling
    format. MCP tools carry the same information but in a different shape
    (tool.name, tool.description, tool.inputSchema), so this adapts them.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "required": tool.inputSchema.get("required", []),
                "properties": tool.inputSchema.get("properties", {}),
            },
        },
    }


def format_tools_for_log(tools: dict) -> str:
    """Build a human-readable summary of available tools for console output.

    Each tool is printed with its name, parameter names/types, and the first
    line of its description so you can quickly see what the server exposes.
    """
    lines = []
    for name, tool in tools.items():
        # Summarize each parameter as "name: type (required)" or "name: type".
        params = ", ".join(
            f"{k}: {v.get('type', '?')}" + (" (required)" if k in tool.inputSchema.get("required", []) else "")
            for k, v in tool.inputSchema.get("properties", {}).items()
        )
        lines.append(f"  {name}({params})")
        if tool.description:
            # Only show the first line to keep the log tidy.
            summary = tool.description.strip().split("\n")[0]
            lines.append(f"    └─ {summary}")

    header = f"Available tools ({len(tools)}):"
    return "\n".join([header, *lines])


async def call_tool(client: Client, tool_name: str, tool_arguments: dict[str, Any]) -> str:
    """Execute a single tool call on the MCP server and return the text result.

    Reuses the persistent client passed in rather than opening a new
    connection. Extracts the plain text from the first content item so the
    LLM receives a clean string rather than a raw result object.
    """
    try:
        result = await client.call_tool(tool_name, tool_arguments)
        return result.content[0].text if result.content else ""
    except ToolError as e:
        return f"Tool error: {e}"


async def get_tools(client: Client) -> dict:
    """Fetch all tools registered on the MCP server.

    Returns a dict keyed by tool name so the rest of the agent can look up
    a tool's metadata by name in O(1) time.
    """
    tools = await client.list_tools()
    return {t.name: t for t in tools}


async def run_turn(
    client: Client,
    available_tools: dict,
    ollama_tools: list,
    messages: list,
    user_input: str,
) -> str:
    """Run one full conversation turn and return the assistant's final answer.

    Appends the user message to the history, then enters the agentic loop:
    the LLM is called repeatedly until it stops requesting tools. Each tool
    result is appended to the message history so the LLM has full context
    for its next decision. Returns the final answer text.
    """
    messages.append({"role": "user", "content": user_input})

    # Agentic loop: keep calling the LLM until it produces a final answer
    # with no further tool calls. The LLM may chain multiple tool calls
    # across several iterations before it has enough information to respond.
    while True:
        response: ChatResponse = chat(MODEL, messages=messages, tools=ollama_tools)

        if not response.message.tool_calls:
            # No tool calls — the LLM is done reasoning. Append the final
            # answer to history so future turns have context, then return it.
            messages.append(response.message)
            return response.message.content

        # The LLM requested one or more tools. Execute each one and append
        # the results to the message history before looping back.
        messages.append(response.message)
        for tool_call in response.message.tool_calls:
            name = tool_call.function.name
            args = tool_call.function.arguments

            if name not in available_tools:
                raise RuntimeError(f"LLM requested unknown tool: {name}")

            print(f"  [calling {name}({args})]")
            output = await call_tool(client, name, args)
            messages.append({"role": "tool", "content": output, "tool_name": name})


async def main():
    async with Client(MCP_SERVER_URL) as client:
        # --- Startup: discover tools and build the Ollama tool list once ---
        available_tools = await get_tools(client)
        print(format_tools_for_log(available_tools))
        print("\nKubernetes assistant ready. Type 'exit' or 'quit' to quit.\n")

        # Ollama-format tool list is constant for the session.
        ollama_tools = [tool_to_dict(t) for t in available_tools.values()]

        # Conversation history persists across turns so the LLM has full
        # context. The system prompt is fixed at index 0.
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # --- Conversation loop ---
        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye.")
                break

            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit"):
                print("Goodbye.")
                break

            try:
                answer = await run_turn(client, available_tools, ollama_tools, messages, user_input)
                print(f"Assistant: {answer}\n")
            except Exception as e:
                print(f"Error: {e}\n")


if __name__ == "__main__":
    asyncio.run(main())
