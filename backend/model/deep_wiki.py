from typing import Dict, List, Optional, Union, Literal, Any

from pydantic import BaseModel, Field

class Section(BaseModel):
    id: str = Field(..., description="Section identifier")
    title: str = Field(..., description="Section title")
    pages: List[str] = Field(..., description="List of page references")
    subsections: List[str] = Field(..., description="Reference to a subsection")


class Page(BaseModel):
    id: str = Field(..., description="Page identifier")
    title: str = Field(..., description="Page title")
    description: str = Field(..., description="Brief description of what this page will cover")
    importance: Literal["high", "medium", "low"] = Field(..., description="Importance level")
    relevant_files: List[str] = Field(..., description="Relevant file list for this page")
    related_pages: List[str] = Field(..., description="Related page list for this page")
    parent_section: Optional[str] = Field(None, description="Parent section identifier")


class WikiStructure(BaseModel):
    title: str = Field(..., description="Overall title for the wiki")
    description: str = Field(..., description="Brief description of the repository")
    sections: List[Section] = Field(..., description="Sections of the wiki")
    pages: List[Page] = Field(..., description="Pages of the wiki")