from backend.core.state_models import AgentStateSchema

# We export AgentState as an alias to AgentStateSchema to avoid breaking other imports that rely on AgentState name
AgentState = AgentStateSchema
