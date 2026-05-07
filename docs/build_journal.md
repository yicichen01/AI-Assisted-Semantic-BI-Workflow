# Build Journal: Semantic BI Workflow MVP

## Phase 1: Scaffolding ✅

- [x] Project structure created
- [x] Core modules outlined
- [x] Requirements defined
- [x] Configuration template created

## Phase 2: Core Implementation (Next)

- [ ] Implement FieldProfiler
- [ ] Implement SemanticAgent with LLM integration
- [ ] Implement QuestionAgent with LLM integration
- [ ] Implement Validators (semantic + data quality)
- [ ] Create domain-specific workflow templates

## Phase 3: UI & Integration

- [ ] Build Streamlit main interface
- [ ] Create question intake workflow
- [ ] Add semantic layer management UI
- [ ] Implement results visualization

## Phase 4: Testing & Refinement

- [ ] Unit tests for agents
- [ ] Integration tests for workflows
- [ ] Performance optimization
- [ ] Documentation

## Design Decisions

1. **Modular agents**: Separate semantic and question agents for clear separation of concerns
2. **Pydantic schemas**: Type-safe data passing between components
3. **Config-driven**: Settings in YAML for non-code customization
4. **LLM-native**: Leverage LLMs for semantic understanding early on

## Next Steps

1. Set up environment and dependencies
2. Implement basic FieldProfiler for data analysis
3. Integrate OpenAI API for SemanticAgent
4. Build first end-to-end flow in Streamlit
