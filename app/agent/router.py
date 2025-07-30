from typing import Literal
from typing_extensions import TypedDict
from langgraph.graph import MessagesState

class Router(TypedDict):
    next: Literal["diet_planer_agent", "exercise_planer_agent", "health_centers_agent", "medication_agent", "symtoms_checker_agent", "air_quality_checker_agent", "FINISH"]

class State(MessagesState):
    next: str