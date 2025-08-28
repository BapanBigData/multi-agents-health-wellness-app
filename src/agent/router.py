# app/agent/router.py
from typing import Literal, Optional, Dict, Any, List
from typing_extensions import TypedDict
from langgraph.graph import MessagesState

class Router(TypedDict):
    next: Literal["diet_planer_agent", "exercise_planer_agent", "health_centers_agent",
                "medication_agent", "symtoms_checker_agent", "air_quality_checker_agent", "FINISH"]

class State(MessagesState):
    next: str
    # 👇 added
    context: Optional[Dict[str, Any]]  # the JSON you receive from frontend
    flow: Optional[str]                # e.g. "phs" (personal health summary)
    queue: Optional[List[str]]         # pending agents for the flow
    results: Optional[Dict[str, str]]  # collected HTML from agents
