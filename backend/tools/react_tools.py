from typing import List, Any
from langchain.tools import tool, ToolRuntime


@tool(parse_docstring=True)
def react(
    thoughts: str,
    add_note: str,
    mark_todo_as_done: list[int],
    ready_to_answer: bool,
    father_id: int,
    add_todo: list[str],
    runtime: ToolRuntime,
) -> str:
    """
    Update the notepad and todo list every time you access a file or directory using tools.
    To avoid repeating the same action, you **should** mention the file name and line numbers in both the notepad and todo list.
    Double check before adding. Never add duplicated todo item or note.

    Args:
        thoughts: Your concise thoughts about the current state.
        add_note: The note to add to the notepad, including your findings and key insights. Every note should starts with a level-2 heading. **Never** add follow-up steps in the note.
        mark_todo_as_done: The ids of the todo items to be marked as done. don't mark father done until son todo all be done
        ready_to_answer: Set to `true` if you're ready to generate the final answer.
        father_id: father task id, if first add todo, father_id will be 0.
        add_todo: The follow-up steps to be added to the father_id todo list. **Never** include `#` in the item. Keep empty if you're ready to generate the final answer.
    """
    runtime.state["notepad"].add_note(add_note)
    for id in mark_todo_as_done:
        runtime.state["todo_list"].mark_todo_as_done(id)
    for item in add_todo:
        runtime.state["todo_list"].add_todo(father_id, item)

    return "Done"


