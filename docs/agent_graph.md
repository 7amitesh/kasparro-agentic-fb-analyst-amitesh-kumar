# Agent Graph & I/O Schema — Kasparro Agentic FB Analyst

This document explains the multi-agent architecture, responsibilities, and the I/O schema for each agent in the pipeline.

## Overview (ASCII diagram)

User Query
│
▼
┌──────────┐
│ Planner │ <-- generates ordered tasks (JSON)
└──────────┘
│
▼
┌──────────┐ ┌─────────────┐
│ Data │─────▶│ Insight │
│ Agent │ │ Agent │
└──────────┘ └─────────────┘
│ │
│ ▼
│ ┌──────────┐
│ │ Evaluator│
│ └──────────┘
▼ │
┌──────────┐ ▼
│ Creative │<────────┐
│ Generator│ │
└──────────┘ │
│ │
▼ ▼
Reports / logs / traces (reports/, logs/traces.json)

## Agent responsibilities & I/O

---

### 1) Planner Agent
**Goal:** Decompose user query into a set of concrete, prioritized tasks.

**Input:**
```json
{
  "query": "Analyze ROAS drop in last 7 days"
}
