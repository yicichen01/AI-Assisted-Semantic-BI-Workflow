# Semantic BI Workflow

A modular, AI-native Python MVP for automating semantic setup and question validation in natural-language self-service BI.

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env
streamlit run app/app.py
```

## Project Structure

- **app/** - Streamlit UI and user-facing workflows
- **src/** - Core business logic (agents, validators, schemas)
- **config/** - Configuration management
- **domains/** - Domain-specific logic and workflows
- **outputs/** - Generated artifacts and results
- **tests/** - Unit and integration tests
- **prompts/** - LLM prompt templates
- **docs/** - Documentation and build journal

## Architecture

AI-native agentic workflow with:
1. **Semantic Agent** - Understands business context and data semantics
2. **Question Agent** - Parses and validates natural language questions
3. **Validators** - Ensures data quality and business rule compliance
4. **Field Profiler** - Analyzes data characteristics for semantic mapping

## Development Status

MVP Phase - Core scaffolding complete. See [docs/build_journal.md](docs/build_journal.md) for progress.
