import inspect
from typing import Callable, Dict, List, Any, get_type_hints, get_origin, get_args


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._tools_by_tag: Dict[str, List[str]] = {}

    @property
    def tools(self) -> Dict[str, Dict[str, Any]]:
        return self._tools

    @property
    def tools_by_tag(self) -> Dict[str, List[str]]:
        return self._tools_by_tag

    def to_openai_tools(self) -> List[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": data.get("description", "")[:1024],
                    "parameters": data.get("parameters", {}),
                },
            }
            for tool_name, data in self._tools.items()
        ]

    def _get_tool_metadata(
        self,
        func: Callable,
        tool_name: str = None,
        description: str = None,
        parameters_override: dict = None,
        terminal: bool = False,
        tags: List[str] = None,
    ) -> Dict[str, Any]:
        tool_name = tool_name or func.__name__
        description = description or (func.__doc__.strip() if func.__doc__ else "No description provided.")

        if parameters_override is None:
            signature = inspect.signature(func)
            type_hints = get_type_hints(func)
            args_schema = {
                "type": "object",
                "properties": {},
                "required": []
            }

            for param_name, param in signature.parameters.items():
                if param_name in ["self","action_context", "action_agent"]:
                    continue

                def get_json_schema(param_type):
                    origin = get_origin(param_type)
                    args = get_args(param_type)

                    if origin is list or origin is List:
                        item_type = args[0] if args else str
                        return {
                            "type": "array",
                            "items": get_json_schema(item_type)
                        }
                    elif origin is dict or origin is Dict:
                        key_type, val_type = args if args else (str, str)
                        return {
                            "type": "object",
                            "additionalProperties": get_json_schema(val_type)
                        }
                    elif param_type in [str, int, float, bool]:
                        return {"type": {
                            str: "string",
                            int: "integer",
                            float: "number",
                            bool: "boolean"
                        }[param_type]}
                    else:
                        return {"type": "string"}

                param_type = type_hints.get(param_name, str)
                param_schema = get_json_schema(param_type)
                args_schema["properties"][param_name] = param_schema

                if param.default == inspect.Parameter.empty:
                    args_schema["required"].append(param_name)
        else:
            args_schema = parameters_override

        return {
            "tool_name": tool_name,
            "description": description,
            "parameters": args_schema,
            "function": func,
            "terminal": terminal,
            "tags": tags or []
        }

    def register(
        self,
        tool_name: str = None,
        description: str = None,
        parameters_override: dict = None,
        terminal: bool = False,
        tags: List[str] = None
    ):
        def decorator(func: Callable):
            metadata = self._get_tool_metadata(
                func,
                tool_name=tool_name,
                description=description,
                parameters_override=parameters_override,
                terminal=terminal,
                tags=tags
            )

            self._tools[metadata["tool_name"]] = {
                "description": metadata["description"],
                "parameters": metadata["parameters"],
                "function": metadata["function"],
                "terminal": metadata["terminal"],
                "tags": metadata["tags"]
            }

            for tag in metadata["tags"]:
                self._tools_by_tag.setdefault(tag, []).append(metadata["tool_name"])

            return func

        return decorator