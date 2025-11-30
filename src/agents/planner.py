import json
import os
from typing import Dict, Any, List
from src.openai_integration import call_llm
from src.utils.loader import load_config

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "planner_prompt.md")


class Planner:
    """Planner Agent — decomposes user query into structured analytical tasks."""

    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    def decompose(self, query: str) -> Dict[str, Any]:
        """Generate tasks from LLM or fallback."""
        prompt = self.prompt_template + f"\n\nUser Query:\n{query}\n\nReturn ONLY JSON."
        if self.cfg.get("openai_enabled", False):
            resp = call_llm(prompt, max_tokens=500)
            if resp:
                parsed = self._safe_parse(resp)
                if parsed:
                    return parsed

        # ----- FALLBACK PLANNER -----
        return {
            "query": query,
            "tasks": [
                {
                    "id": "t1",
                    "title": "load_and_filter_data",
                    "description": "Load dataset and filter past N days.",
                    "priority": "high",
                    "required_inputs": ["df_recent"]
                },
                {
                    "id": "t2",
                    "title": "audience_breakdown",
                    "description": "Analyze ROAS/CTR by audience.",
                    "priority": "high",
                    "required_inputs": ["by_audience"]
                },
                {
                    "id": "t3",
                    "title": "platform_analysis",
                    "description": "Analyze performance across platforms.",
                    "priority": "medium",
                    "required_inputs": ["by_platform"]
                },
                {
                    "id": "t4",
                    "title": "creative_performance",
                    "description": "Identify low CTR creatives.",
                    "priority": "high",
                    "required_inputs": ["low_ctr_creatives"]
                },
                {
                    "id": "t5",
                    "title": "generate_insights",
                    "description": "Create hypotheses explaining ROAS changes.",
                    "priority": "high",
                    "required_inputs": ["summary"]
                }
            ]
        }

    def _safe_parse(self, text: str):
        """Parse JSON from LLM text safely."""
        try:
            return json.loads(text)
        except Exception:
            # Attempt to extract JSON inside text
            idx = text.find("{")
            if idx >= 0:
                try:
                    return json.loads(text[idx:])
                except Exception:
                    return None
        return None
