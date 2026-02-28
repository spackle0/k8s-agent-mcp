# agent.py
#
# This is the LLM agent that ties together the language model (via Ollama) and
# the MCP tool server. The flow is:
#   1. Fetch the list of available tools from the MCP server at startup.
#   2. Send the user's message to the LLM along with the tool definitions.
#   3. If the LLM decides to call a tool, execute it against the MCP server.
#   4. Feed the tool result back into the conversation and get a final answer.

from ollama import ChatResponse, chat

import asyncio

from fastmcp import Client

from typing import Any

# Base URL for the FastMCP server's streamable-HTTP endpoint.
MCP_SERVER_URL = "http://localhost:8000/mcp"

# Example of a manually defined tool dict in Ollama's expected format.
# Tools fetched from the MCP server are converted to this same shape by
# tool_to_dict() below. This one is kept here as a reference/fallback.
subtract_two_numbers_tool = {
    "type": "function",
    "function": {
        "name": "subtract_two_numbers",
        "description": "Subtract two numbers",
        "parameters": {
            "type": "object",
            "required": ["a", "b"],
            "properties": {
                "a": {"type": "integer", "description": "The first number"},
                "b": {"type": "integer", "description": "The second number"},
            },
        },
    },
}


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
                "required": tool.inputSchema["required"],
                "properties": tool.inputSchema["properties"],
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
        # Summarise each parameter as "name: type (required)" or "name: type".
        params = ", ".join(
            f"{k}: {v.get('type', '?')}"
            + (" (required)" if k in tool.inputSchema.get("required", []) else "")
            for k, v in tool.inputSchema.get("properties", {}).items()
        )
        lines.append(f"  {name}({params})")
        if tool.description:
            # Only show the first line to keep the log tidy.
            summary = tool.description.strip().split("\n")[0]
            lines.append(f"    └─ {summary}")

    header = f"Available tools ({len(tools)}):"
    return "\n".join([header, *lines])


async def call_tool(tool_name: str, tool_arguments: dict[str, Any]) -> Any:
    """Execute a single tool call on the MCP server and return the result.

    Opens a short-lived connection to the MCP server for each call. The
    FastMCP Client handles the streamable-HTTP transport and protocol
    handshake automatically.
    """
    async with Client(MCP_SERVER_URL) as client:
        return await client.call_tool(tool_name, tool_arguments)


async def get_tools() -> dict:
    """Fetch all tools registered on the MCP server.

    Returns a dict keyed by tool name so the rest of the agent can look up
    a tool's metadata by name in O(1) time.
    """
    async with Client(MCP_SERVER_URL) as client:
        tools = await client.list_tools()
        return {t.name: t for t in tools}


async def main():
    # --- Step 1: Discover tools ---
    # Pull the current tool list from the MCP server and print it so the
    # operator can confirm what capabilities are available.
    available_tools = await get_tools()
    print(format_tools_for_log(available_tools))

    # --- Step 2: First LLM call (tool selection) ---
    # Send the user message together with the tool definitions. The model
    # decides whether to answer directly or to invoke one or more tools.
    messages = [{"role": "user", "content": "What are the current weather alerts for alaska?"}]
    print("Prompt:", messages[0]["content"])

    response: ChatResponse = chat(
        "llama3.1:8b",
        messages=messages,
        tools=[tool_to_dict(t) for t in available_tools.values()],
    )

    # --- Step 3: Execute any requested tool calls ---
    # The model may request multiple tools in a single turn. We run each one
    # and capture the last output (used in the follow-up message below).
    if response.message.tool_calls:
        for tool in response.message.tool_calls:
            if tool.function.name not in available_tools:
                raise RuntimeError(f"No function available - {tool.function.name}")
            print("Calling function:", tool.function.name)
            print("Arguments:", tool.function.arguments)
            output = await call_tool(tool.function.name, tool.function.arguments)
            print("Function output:", output)

    # --- Step 4: Second LLM call (final answer) ---
    # Append the assistant's tool-call message and the tool result to the
    # conversation history, then ask the model to produce a natural-language
    # answer that incorporates the tool output.
    if response.message.tool_calls:
        messages.append(response.message)
        messages.append(
            {"role": "tool", "content": str(output), "tool_name": tool.function.name}
        )

        final_response = chat("llama3.1:8b", messages=messages)
        print("Final response:", final_response.message.content)

    else:
        print("No tool calls returned from model")


if __name__ == "__main__":
    asyncio.run(main())
