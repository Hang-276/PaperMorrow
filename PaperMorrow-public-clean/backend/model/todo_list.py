from pydantic import BaseModel
from typing import Dict, List, Optional



class TodoItem(BaseModel):
    id: int
    """The id of the todo item."""

    title: str
    """The title of the todo item."""

    is_done: bool = False
    """Whether the todo item is done."""

    def __str__(self):
        return f"- [{'x' if self.is_done else ' '}] #{self.id} : {self.title}\n"

class TodoList(BaseModel):
    items: Dict[int, TodoItem] = {}
    sub_items: Dict[int, List[int]] = {} # key: Father, val: son
    father: Dict[int, int] = {} # key: son, val: Father

    id_counter: int = 0

    def next_id(self) -> int:
        self.id_counter += 1
        return self.id_counter

    def add_todo(self, f_id: int, title: str):
        _id = self.next_id()
        self.father[_id] = f_id
        if f_id not in self.sub_items:
            self.sub_items[f_id] = []
        self.sub_items[f_id].append(_id)
        self.items[_id] = TodoItem(
            id=_id,
            title=title,
            is_done=False,
        )

    def clear(self):
        self.items = []
        self.id_counter = 0

    def remove_todo(self, id: int):
        for item in self.items:
            if item.id == id:
                self.items.remove(item)
                break

    def mark_todo_as_done(self, id: int):
        if id in self.items:
            self.items[id].is_done = True

    def to_str(self, prefix: str, ids: list[int], out: list[str]):
        for _id in ids:
            if _id not in self.items:
                continue
            out.append(f"{prefix}{self.items[_id]}")
            if _id in self.sub_items:
                self.to_str(prefix+"    ", self.sub_items[_id], out)

    def to_markdown(self) -> str:
        content = ""
        if len(self.items) == 0:
            content = "(empty)\n\n> Should call the `react()` tool immediately to add Todo items as a your first plan."
        else:
            out = []
            self.to_str(prefix="", ids=self.sub_items[0], out=out)
            content = "".join(out)
        return f"# Todo List\n\n{content.strip()}"


def create_todo_list() -> TodoList:
    return TodoList(items=[])
