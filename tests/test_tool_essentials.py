from agent.tool_essentials import ToolRegistry


class TestToolEssentials:
    def test_register_tool(self):
        registry = ToolRegistry()

        @registry.register(description="Adds two numbers", tags=["math", "arithmetic"])
        def add(a: int, b: int) -> int:
            """
            Adds two numbers together
            Args:
                a (int): The first number
                b (int): The second number
            Returns:
                int: The sum of the two numbers
            """

            return a + b

        @registry.register(description="Says hello", tags=["text"])
        def hello(name: str) -> str:
            """
            Says hello to the given name
            Args:
                name (str): The name to say hello to
            Returns:
                str: A greeting message
            """
            return f"Hello {name}"

        assert registry.tools["add"]["description"] == "Adds two numbers"
