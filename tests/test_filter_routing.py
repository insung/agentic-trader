from backend.workflows.graph import create_workflow

def test_conditional_routing_on_tech_analyst():
    workflow = create_workflow()
    compiled = workflow.compile()
    
    edges = compiled.builder.edges
    has_conditional = any(
        getattr(edge, 'source', None) == 'tech_analyst' and hasattr(edge, 'conditions')
        for edge in edges
    ) or any(
        key == 'tech_analyst' for key in compiled.builder.branches.keys()
    )
    assert has_conditional, "tech_analyst should have a conditional edge"
