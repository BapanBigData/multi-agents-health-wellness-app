from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from app.agent.router import State
from app.agent.agent import * 

graph = StateGraph(State)

# Add nodes for all agents
graph.add_node("supervisor", supervisor)
graph.add_node("diet_planer_agent", diet_planer_agent)
graph.add_node("health_centers_agent", health_centers_agent)
graph.add_node("medication_agent", medication_agent)
graph.add_node("symtoms_checker_agent", symtoms_checker_agent)
graph.add_node("air_quality_checker_agent", air_quality_checker_agent)

# Define graph edges
graph.add_edge(START, "supervisor")
graph.add_edge("diet_planer_agent", "supervisor")
graph.add_edge("health_centers_agent", "supervisor")
graph.add_edge("medication_agent", "supervisor")
graph.add_edge("symtoms_checker_agent", "supervisor")
graph.add_edge("air_quality_checker_agent", "supervisor")
graph.add_edge("supervisor", END)

# Set up memory and compile the app
memory = MemorySaver()
app = graph.compile()