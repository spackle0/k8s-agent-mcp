"You'll need an .env file with: ANTHROPIC_API_KEY = 'sk-ant-...'"

from anthropic import Anthropic
import os
import subprocess

from dotenv import load_dotenv

load_dotenv()


class Agent:
    def __init__(self, client, get_user_message, tools: list):
        self.client = client
        self.get_user_message = get_user_message
        self.tools = tools
        self.system_prompt = """
            You are a simple agent with one tool. 
            If the user asks you to do something, try to do it with the bash tool.
        """

    def _run_inference(self, messages):
        message = self.client.messages.create(
            max_tokens=10000,
            messages=messages,
            model="claude-sonnet-4-6",
            tools=self.tools,
            system=self.system_prompt,
        )

        return message

    def run(self):
        print("Chat with the agent. Type 'quit', 'exit', or 'bye' to quit.")
        conversation = []

        while True:
            try:
                user_message = self.get_user_message()

            except EOFError, KeyboardInterrupt:
                print("\nGoodbye!")
                break

            if user_message.strip().lower() in ("quit", "exit", "bye"):
                print("\nGoodbye!")
                break

            conversation.append({"role": "user", "content": user_message})

            while True:
                response = self._run_inference(conversation)
                conversation.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type == "text":
                        print("\n--------\n🤖 Agent:")
                        print(block.text)

                    elif block.type == "tool_use":
                        print("Tool use: ", block.name, " with input: ", block.input)

                        tool_result_content = ""
                        if block.name == "run_bash":
                            try:
                                tool_result_content = run_bash(**block.input)
                            except Exception as e:
                                tool_result_content = str(e)

                        print("Tool output: ", tool_result_content)

                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": tool_result_content,
                            }
                        )
                if tool_results:
                    conversation.append({"role": "user", "content": tool_results})
                else:
                    break


BASH_TOOL = {
    "name": "run_bash",
    "description": "Run something in bash. If the command is dangerous, you should confirm with the user.",
    "input_schema": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The script to run",
            },
            "timeout": {
                "type": "integer",
                "description": "Seconds of timeout. Default is 30 seconds.",
            },
        },
        "required": ["command"],
    },
}


def run_bash(command: str, timeout: int = 30) -> str:
    """Run a bash command.

    Args:
        command: Bash command to execute.
        timeout: Max seconds before timeout.

    Returns:
        Command output or error message.
    """
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        output = result.stdout + result.stderr
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"


def main():
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

    def get_user_message():
        print("\n--------\n🧑 You: ", end="", flush=True)
        user_message = input()
        return user_message

    tools = [BASH_TOOL]

    agent = Agent(client, get_user_message, tools)
    agent.run()


if __name__ == "__main__":
    main()
