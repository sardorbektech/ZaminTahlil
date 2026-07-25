# AGENTS.md

This file helps Autohand understand how to work with this project.

## Project Overview

- **Language**: Python
- **Package Manager**: pip
- **Runtime mode**: `APP_ENV` in `.env` — default `demo`; `prod` disables API docs (`/docs`, `/redoc`, `/openapi.json`), wildcard CORS (requires explicit `CORS_ORIGINS`), and enables log masking (see README).

## Commands

- **Install**: `pip install -r requirements.txt`
- **Run**: `uvicorn app.main:app --reload`
- **Test**: `venv\\Scripts\\python.exe -m pytest -q`

## Instruction Sources

- Check saved memories and preferences before implementation work.
- Follow this AGENTS.md file for repository-specific guidance.
- AGENTS.md takes precedence over CLAUDE.md when both files provide instructions.

## Code Style

- Follow PEP 8 style guidelines
- Use type hints for function signatures
- Use docstrings for public functions
- Follow existing patterns in the codebase
- Use meaningful variable and function names
- Add comments for complex logic
- Keep functions focused and small

## OpenCode Setup

- **Config**: `.opencode/opencode.json`
- **Primary model (commander)**: `openrouter/moonshotai/kimi-k3` — plans, delegates, reviews.
- **Subagent models (workers)**: `openrouter/z-ai/glm-5.2` — `general` and `explore` subagents execute the hands-on work.
- **Orchestration rules**: `.opencode/orchestration.md` (loaded via `instructions` in the config).

## Constraints

- Do not modify files outside the project directory
- Ask before making breaking changes
- Prefer editing existing files over creating new ones
- Do not delete files without confirmation
- Keep dependencies minimal - avoid adding new ones without good reason
- Do not commit sensitive data (API keys, secrets, credentials)
