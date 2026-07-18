import operator
from typing import Annotated, TypedDict, List, Dict, Optional, Any

from pydantic import BaseModel

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, BaseMessage

from langgraph.graph import add_messages

from backend.model.notepad import Notepad
from backend.model.todo_list import TodoList
from backend.workspace import Project


def merge_todo_list(left: dict | TodoList, right: dict | TodoList) -> TodoList:
    left = (
        TodoList.model_validate(left)
        if isinstance(left, dict)
        else left.model_copy(deep=True)
    )
    right = (
        TodoList.model_validate(right)
        if isinstance(right, dict)
        else right.model_copy(deep=True)
    )
    left_item_ids = [item.id for item in left.items]
    for right_item in right.items:
        if right_item.id in left_item_ids:
            left.items[left_item_ids.index(right_item.id)] = right_item
        else:
            left.items.append(right_item)
    left.id_counter = max(left.id_counter, right.id_counter)
    return left


def merge_notepad(left: dict | Notepad, right: dict | Notepad) -> Notepad:
    left = (
        Notepad.model_validate(left)
        if isinstance(left, dict)
        else left.model_copy(deep=True)
    )
    right = (
        Notepad.model_validate(right)
        if isinstance(right, dict)
        else right.model_copy(deep=True)
    )
    left_note_contents = [note.content for note in left.notes]
    for right_note in right.notes:
        if right_note.content not in left_note_contents:
            left.notes.append(right_note)
    return left


def merge_messages(
    left: list[BaseMessage], right: list[BaseMessage]
) -> list[BaseMessage]:
    messages = add_messages(left, right)
    last_assistant_message_index = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, AIMessage):
            last_assistant_message_index = i
    if last_assistant_message_index == -1:
        return messages
    merged_messages = []
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            merged_messages.append(msg)
        if isinstance(msg, AIMessage) or isinstance(msg, ToolMessage):
            if i >= last_assistant_message_index:
                merged_messages.append(msg)
    return merged_messages

class TokenCounter(BaseModel):
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0

class State(TypedDict):
    messages: Annotated[list[BaseMessage], merge_messages]
    remaining_steps: int
    project: Project
    todo_list: Annotated[TodoList, merge_todo_list]
    notepad: Annotated[Notepad, merge_notepad]
    token_counter: TokenCounter
    # Count model research rounds independently from LangGraph's recursion
    # counter.  This lets the original ReAct workflow finish gracefully even
    # when a provider keeps requesting tools instead of writing its answer.
    research_steps: Annotated[int, operator.add]

    def to_markdown(self) -> str:
        return f"""# User's Question

{self.messages[3].content if len(self.messages) > 3 else "(none)"}

# Notepad

{self.notepad.to_markdown()}

# Final Answer

{self.messages[-1].content if len(self.messages) > 0 else "(none)"}
"""
