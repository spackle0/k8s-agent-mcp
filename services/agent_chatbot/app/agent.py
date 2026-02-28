from ollama import ChatResponse, chat

import asyncio

import pprint

from mcp import ClientSession, Tool
from mcp.client.streamable_http import streamable_http_client

from typing import Any

# Tools can still be manually defined and passed into chat
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

def tool_to_dict(tool: Tool) -> dict:
  return {
    "type": "function",
    "function": {
      "name": tool.name,
      "description": tool.description,
      "parameters": {
        "type": "object",
        "required": tool.inputSchema["required"],
        "properties": tool.inputSchema['properties']
      }
    }
  }

def format_tools_for_log(tools: dict) -> str:
    lines = []
    for name, tool in tools.items():
        params = ", ".join(
                f"{k}: {v.get('type', '?')}" + (" (required)" if k in tool.inputSchema.get("required", []) else "")
                for k, v in tool.inputSchema.get("properties", {}).items()
        )
        lines.append(f"  {name}({params})")
        if tool.description:
            summary = tool.description.strip().split("\n")[0]
            lines.append(f"    └─ {summary}")

    header = f"Available tools ({len(tools)}):"
    return "\n".join([header, *lines])

async def call_tool(tool_name: str, tool_arguments: dict[str, Any]) -> Any:
    # Call our MCP Server with a tool
    async with streamable_http_client("http://localhost:8000/mcp") as (
        read_stream,
        write_stream,
        _,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, tool_arguments)
            breakpoint()
            return result.content


async def get_tools() -> dict[str, Tool]:
    async with streamable_http_client("http://localhost:8000/mcp") as (
        read_stream,
        write_stream,
        _,
    ):
        # Create a session using the client streams
        async with ClientSession(read_stream, write_stream) as session:
            # Initialize the connection
            await session.initialize()
            # List available tools
            tools = (await session.list_tools()).tools
            return {t.name: t for t in tools}


async def main():
  available_tools = await get_tools()
  print(format_tools_for_log(available_tools))
  messages = [{"role": "user", "content": "What are the current weather alerts for alaska?"}]
  print("Prompt:", messages[0]["content"])

  response: ChatResponse = chat(
          "llama3.1:8b",
          messages=messages,
          tools=[tool_to_dict(t) for t in available_tools.values()],
  )

  if response.message.tool_calls:
      # There may be multiple tool calls in the response
      for tool in response.message.tool_calls:
          # Ensure the function is available, and then call it
          if tool.function.name not in available_tools:
            raise RuntimeError(f"No function available - {tool.function.name}")
          print("Calling function:", tool.function.name)
          print("Arguments:", tool.function.arguments)
          output = await call_tool(tool.function.name, tool.function.arguments)
          print("Function output:", output)

  # Only needed to chat with the model using the tool call results
  if response.message.tool_calls:
      # Add the function response to messages for the model to use
      messages.append(response.message)
      messages.append(
          {"role": "tool", "content": str(output), "tool_name": tool.function.name}
      )

      # Get final response from model with function outputs
      final_response = chat("llama3.1:8b", messages=messages)
      print("Final response:", final_response.message.content)

  else:
      print("No tool calls returned from model")


if __name__ == "__main__":
    asyncio.run(main())
