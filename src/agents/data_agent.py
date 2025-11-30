import os
from typing import Dict, Any, List
from src.utils.loader import summarize_for_llm
from src.openai_integration import call_llm
from src.utils.loader import load_config

PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "prompts", "data_agent_prompt.md")


class DataAgent:
    """Data Agent — converts planner tasks into structured summaries."""

    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        with open(PROMPT_PATH, "r", encoding="utf-8") as f:
            self.prompt_template = f.read()

    def execute(self, tasks: List[Dict[str, Any]], raw_summary: Dict[str, Any]) -> Dict[str, Any]:
        # Prepare LLM prompt
        context = {
            "tasks": tasks,
            "raw_summary": raw_summary
        }
        prompt = self.prompt_template + f"\n\nContext JSON:\n```json\n{context}\n```\nReturn ONLY JSON."

        if self.cfg.get("openai_enabled", False):
            resp = call_llm(prompt, max_tokens=700)
            if resp:
                parsed = self._safe_parse(resp)
                if parsed:
                    return parsed

        # ----- FALLBACK -----
        summaries = []
        for t in tasks:
            summaries.append({
                "task_id": t["id"],
                "summary": raw_summary
            })
        return {"task_summaries": summaries}

    def _safe_parse(self, text: str):
        try:
            import json
            return json.loads(text)
        except:
            return None
