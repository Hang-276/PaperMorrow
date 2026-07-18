
from typing import Any

from pydantic import BaseModel

from backend.model.state import State, merge_messages
from backend.tools import (
    file_outline,
    file_tree,
    react,
    read_lines,
    search_in_file,
    search_in_folders,
)
from backend.prompts.prompt_template import apply_prompt_template

from langchain.agents.middleware import AgentMiddleware, before_model, after_model
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage
from langchain.agents import create_agent
from langgraph.runtime import Runtime

MAX_RESEARCH_STEPS = 64


def _requested_final_answer(state: State, max_research_steps: int = MAX_RESEARCH_STEPS) -> bool:
    """Return whether the next model call must produce the final document.

    The original prompt uses ``react(ready_to_answer=true)`` as its completion
    signal, but a plain LangGraph agent does not interpret that argument as a
    stop condition.  Some models naturally stop anyway; DeepSeek reliably keeps
    calling tools.  Inspecting the last assistant tool call makes the signal an
    actual graph-level protocol.  The round cap is a safety net for providers
    that never emit the signal.
    """
    if int(state.get("research_steps", 0)) >= max_research_steps:
        return True
    for message in reversed(state.get("messages", [])):
        if not isinstance(message, AIMessage):
            continue
        for tool_call in message.tool_calls or []:
            if tool_call.get("name") != "react":
                continue
            args = tool_call.get("args") or {}
            if isinstance(args, dict) and args.get("ready_to_answer") is True:
                return True
        # merge_messages retains only the most recent assistant turn, so there
        # is no useful older assistant message to inspect.
        break
    return False


@before_model
def log_before_model(state: State, runtime: Runtime) -> dict[str, Any] | None:
    msg = [
            HumanMessage(
                content=state["notepad"].to_markdown(), id="notepad"
            ),
            HumanMessage(
                content=state["todo_list"].to_markdown(), id="todo_list"
            ),
    ]
    if _requested_final_answer(state):
        msg.append(HumanMessage(
            content=(
                "执行控制：代码研究阶段已经结束。现在直接输出用户要求的最终 JSON 或 Markdown 正文；"
                "禁止再次调用任何工具，禁止解释过程，禁止使用 Markdown 外层围栏。"
            ),
            id="final_answer_control",
        ))
    return {"messages": merge_messages(state["messages"], msg), "research_steps": 1}

@after_model()
def log_after_model(state: State, runtime: Runtime) -> dict[str, Any] | None:
    last_message = state["messages"][-1]
    # state["token_counter"].completion_tokens += last_message.response_metadata["token_usage"]["completion_tokens"]
    # state["token_counter"].prompt_tokens += last_message.response_metadata["token_usage"]["prompt_tokens"]
    # state["token_counter"].total_tokens += last_message.response_metadata["token_usage"]["total_tokens"]
    # print("meta_msg", last_message.response_metadata["token_usage"])



def _tool_error_message(request, error: Exception) -> ToolMessage:
    """Turn a tool failure into an observation the researcher can recover from."""
    print("调用工具出错了", error)
    return ToolMessage(
        content=f"Tool error: Please check your input and try again. ({str(error)})",
        tool_call_id=request.tool_call["id"],
        status="error",
    )


class ToolErrorMiddleware(AgentMiddleware):
    """Keep the original error recovery in both sync and async agent runs.

    LangChain does not automatically adapt a synchronous ``wrap_tool_call`` hook
    when an agent is executed with ``ainvoke``. The integrated DeepWiki service
    is asynchronous, while the original standalone project also exposes a sync
    entry point, so both hooks are implemented deliberately.
    """

    def wrap_tool_call(self, request, handler):
        try:
            return handler(request)
        except Exception as error:
            return _tool_error_message(request, error)

    async def awrap_tool_call(self, request, handler):
        try:
            return await handler(request)
        except Exception as error:
            return _tool_error_message(request, error)


handle_tool_errors = ToolErrorMiddleware()


class ForceFinalAnswerMiddleware(AgentMiddleware):
    """Remove tools after the original researcher's completion signal."""

    def __init__(self, max_research_steps: int = MAX_RESEARCH_STEPS):
        self.max_research_steps = max_research_steps

    def _request(self, request):
        if _requested_final_answer(request.state, self.max_research_steps):
            return request.override(tools=[], tool_choice=None)
        return request

    def wrap_model_call(self, request, handler):
        return handler(self._request(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._request(request))


def create_researcher(chat_model=None, system_prompt_suffix: str = "", max_research_steps: int = MAX_RESEARCH_STEPS):
    if chat_model is None:
        # Kept for compatibility with the original standalone entry point.
        from backend.llm.chat_model import create_chat_model
        chat_model = create_chat_model()
    prompt = apply_prompt_template("researcher")
    if system_prompt_suffix:
        prompt = f"{prompt.rstrip()}\n\n{system_prompt_suffix.strip()}\n"
    tools = [
        file_outline,
        read_lines,
        search_in_file,
        search_in_folders,
        file_tree,
        react,
    ]
    agent = create_agent(
        model=chat_model,
        tools=tools,
        system_prompt=prompt,
        state_schema=State,
        middleware=[
            log_before_model,
            ForceFinalAnswerMiddleware(max_research_steps),
            handle_tool_errors,
            log_after_model,
        ],
        # response_format=ToolStrategy(WikiStructure)
    )
    return agent


# The integrated application builds one researcher from the currently selected
# API profile. Avoid constructing a provider-specific global model at import.
researcher = None
