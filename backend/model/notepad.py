from pydantic import BaseModel
from typing import List


class Note(BaseModel):
    content: str


class Notepad(BaseModel):
    notes: List[Note]

    def add_note(self, content: str):
        self.notes.append(Note(content=content))

    def clear(self):
        self.notes = []

    def to_markdown(self) -> str:
        content = ""
        if len(self.notes) == 0:
            content = "(empty)\n\n> Should call the `react()` tool immediately to add your first note."
        else:
            for note in self.notes:
                content += f"{note.content}\n\n"
        return f"# Notepad\n\n{content.strip()}"
