# Agentura

Local workspace for reusable agent skills and operating procedures (filesystem-based).

This repo is model- and vendor-agnostic: skills are stored as files and can be consumed by
different runtimes (e.g., Claude, other LLM APIs, local runners).

## What is versioned
- skills/        reusable skill packages (each has SKILL.md + optional templates/examples/resources)
- templates/     reusable document templates (optional, if you want them versioned)

## What is NOT versioned by default
- outputs/, logs/, agent-sandbox/  generated artifacts
- inputs/                        working materials; commit only intentionally

## Conventions
- One skill = one folder with SKILL.md
- Keep skills modular; shared parts live in skills/_modules
- Global rules live in skills/_base
