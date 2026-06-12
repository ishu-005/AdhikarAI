"""LCEL answer chain: prompt | llm | parser (supports sync invoke and async stream)."""
from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import Runnable

from backend.rag.llm import get_llm
from backend.rag.prompts import PROMPT


def build_answer_chain() -> Runnable:
    """Prompt is filled by the pipeline (context already retrieved & formatted)."""
    return PROMPT | get_llm() | StrOutputParser()
