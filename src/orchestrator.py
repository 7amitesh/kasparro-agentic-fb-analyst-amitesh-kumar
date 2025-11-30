import os
import json
import time
from datetime import datetime
from typing import Dict, Any, List

from src.utils.loader import load_config, load_data, summarize_for_llm, get_recent_df
from src.utils.metrics import rolling_roas, detect_outliers, compute_group_metrics, pct_change
from src.agents.planner import Planner
from src.agents.data_agent import DataAgent
from src.agents.insight_agent import InsightAgent
from src.agents.evaluator import Evaluator
from src.agents.creative_generator import CreativeGenerator

LOGS_PATH_DEFAULT = "logs/traces.json"


class Orchestrator:
    """
    Orchestrator coordinates agents, implements a basic reflection loop,
    and writes traces for observability.
    """

    def __init__(self, cfg: Dict[str, Any] = None):
        self.cfg = cfg or load_config()
        # allow override of llm usage via run flags by mutating cfg externally
        self.planner = Planner(self.cfg)
        self.data_agent = DataAgent(self.cfg)
        self.insight_agent = InsightAgent(self.cfg)
        self.evaluator = Evaluator(self.cfg)
        self.creative_generator = CreativeGenerator(self.cfg)
        self.logs_path = self.cfg.get("logs_path", LOGS_PATH_DEFAULT)
        os.makedirs(os.path.dirname(self.logs_path) or ".", exist_ok=True)

    def _write_trace(self, trace_item: Dict[str, Any]):
        existing = []
        try:
            if os.path.exists(self.logs_path):
                with open(self.logs_path, "r", encoding="utf-8") as f:
                    existing = json.load(f) or []
        except Exception:
            existing = []
        existing.append(trace_item)
        with open(self.logs_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, default=str)

    def _assemble_report_text(self, evaluated_hypotheses: List[Dict[str, Any]], creatives: Dict[str, Any], summary_meta: Dict[str, Any]) -> str:
        ts = datetime.utcnow().isoformat() + "Z"
        lines = []
        lines.append("# Kasparro — Agentic FB Analyst Report")
        lines.append(f"Generated: {ts}")
        lines.append("")
        lines.append("## Executive summary")
        if not evaluated_hypotheses:
            lines.append("- No hypotheses were generated.")
        else:
            for ev in evaluated_hypotheses:
                lines.append(f"- Hypothesis: {ev.get('hypothesis')} (confidence: {ev.get('confidence')})")
        lines.append("")
        lines.append("## Key metrics (recent period)")
        lines.append(f"- Total impressions: {summary_meta.get('total_impressions')}")
        lines.append(f"- Total clicks: {summary_meta.get('total_clicks')}")
        lines.append(f"- Total spend: {summary_meta.get('total_spend'):.2f}")
        lines.append(f"- Total revenue: {summary_meta.get('total_revenue'):.2f}")
        lines.append(f"- Avg CTR: {summary_meta.get('avg_ctr'):.4f}")
        lines.append(f"- Avg ROAS: {summary_meta.get('avg_roas'):.4f}")
        lines.append("")
        lines.append("## Recommendations (sample)")
        if creatives.get("ideas") or creatives.get("creative_recommendations") or creatives.get("ideas"):
            ideas = creatives.get("ideas") or creatives.get("creative_recommendations") or creatives.get("ideas")
            for i, c in enumerate(ideas[:8]):
                if isinstance(c, dict):
                    headline = c.get("headline") or c.get("id") or "headline"
                    cta = c.get("cta") or c.get("platform_fit", "")
                    lines.append(f"- {i+1}. Headline: {headline} | CTA: {cta}")
                else:
                    lines.append(f"- {i+1}. {str(c)}")
        else:
            lines.append("- No creative ideas generated.")
        lines.append("")
        lines.append("## Full hypotheses & evidence")
        for ev in evaluated_hypotheses:
            lines.append(f"### {ev.get('id')}")
            lines.append(f"- Hypothesis: {ev.get('hypothesis')}")
            lines.append(f"- Verdict: {ev.get('verdict')} (confidence: {ev.get('confidence')})")
            lines.append(f"- Evidence: {json.dumps(ev.get('evidence', {}), default=str)[:1000]}")
            lines.append(f"- Notes: {ev.get('notes')}")
            lines.append("")
        return "\n".join(lines)

    def run(self, query: str, out_dir: str = "reports") -> Dict[str, Any]:
        """
        Run full pipeline:
         - Planner: decompose query
         - DataAgent: produce summaries
         - InsightAgent: produce hypotheses
         - Evaluator: validate hypotheses
         - CreativeGenerator: produce creatives
         - Logging and write reports
        """
        start_ts = datetime.utcnow().isoformat() + "Z"

        # 1) Load data
        df = load_data(self.cfg)
        recent_days = int(self.cfg.get("recent_days", 7))
        df_recent = get_recent_df(df, recent_days)

        # 2) Summarize for LLM/data agents
        summary = summarize_for_llm(df, recent_days, top_n=self.cfg.get("max_low_ctr_creatives", 20))
        # add a few derived items for evaluator use
        try:
            summary["rolling_roas"] = rolling_roas(df, window=self.cfg.get("trend_window_days", 7)).dropna().to_list()
        except Exception:
            summary["rolling_roas"] = []

        # 3) Planner
        plan = self.planner.decompose(query)
        tasks = plan.get("tasks", []) if isinstance(plan, dict) else []

        # 4) DataAgent
        data_agent_output = self.data_agent.execute(tasks, summary)
        task_summaries = data_agent_output.get("task_summaries", [])

        # 5) InsightAgent
        # Provide the condensed summary (not full CSV) for hypothesis generation
        insight_input = summary.copy()
        # also include task-level summaries for context
        insight_input["task_summaries"] = task_summaries
        insights_raw = self.insight_agent.generate(insight_input)
        hypotheses = insights_raw.get("hypotheses") or insights_raw.get("insights") or []

        # 6) Evaluator: validate each hypothesis with numerical checks
        evaluated = []
        for h in hypotheses:
            # build simple evidence object: pct change in roas & ctr for audience/platform if mentioned
            evidence = {}
            # sample computations - try to infer audience/platform mentions
            text = (h.get("hypothesis") or "").lower()
            # compute global pct change of roas between long and recent window if possible
            try:
                long_window = int(self.cfg.get("long_trend_window_days", 30))
                recent_window = int(self.cfg.get("trend_window_days", 7))
                # approximate by rolling averages last value vs earlier value
                roas_series = rolling_roas(df, window=recent_window)
                if len(roas_series) >= recent_window + 1:
                    last = float(roas_series.dropna().iloc[-1])
                    prev = float(roas_series.dropna().iloc[max(0, -recent_window-1)])
                    evidence["pct_change_roas"] = pct_change(prev, last)
                else:
                    evidence["pct_change_roas"] = 0.0
            except Exception:
                evidence["pct_change_roas"] = 0.0

            # sample_size approx = number of rows in recent df
            evidence["sample_size"] = int(len(df_recent))
            # outlier flag if any extreme roas present
            try:
                roas_vals = df["roas"].replace([float("inf"), -float("inf")], 0).fillna(0)
                evidence["outlier_flag"] = bool(detect_outliers(roas_vals, method=self.cfg.get("outlier_method", "iqr")).any())
            except Exception:
                evidence["outlier_flag"] = False

            # pass to evaluator
            ev = self.evaluator.evaluate(h, evidence)
            # normalize ev structure
            ev_out = {
                "id": h.get("id", "unknown"),
                "hypothesis": h.get("hypothesis"),
                "evidence": evidence,
                "confidence": ev.get("confidence") if isinstance(ev, dict) else ev,
                "verdict": ev.get("verdict"),
                "notes": ev.get("notes") if "notes" in ev else ev.get("evaluator_notes", "")
            }
            evaluated.append(ev_out)

        # reflection loop: if top hypothesis confidence below threshold, ask insight agent to expand
        confidences = [e.get("confidence", 0.0) for e in evaluated]
        top_conf = max(confidences) if confidences else 0.0
        if top_conf < float(self.cfg.get("confidence_min", 0.6)) and self.cfg.get("openai_enabled", False):
            # ask for additional checks (single retry)
            followup_prompt = {
                "note": "Confidence low. Requesting additional hypotheses and checks.",
                "previous_hypotheses": hypotheses,
                "summary": summary
            }
            extra = self.insight_agent.generate(followup_prompt)
            extra_hyp = extra.get("hypotheses", [])
            # evaluate extras quickly
            for h in extra_hyp:
                evidence = {"sample_size": int(len(df_recent))}
                ev = self.evaluator.evaluate(h, evidence)
                evaluated.append({
                    "id": h.get("id", "unknown"),
                    "hypothesis": h.get("hypothesis"),
                    "evidence": evidence,
                    "confidence": ev.get("confidence"),
                    "verdict": ev.get("verdict"),
                    "notes": ev.get("notes", "")
                })

        # 7) Creative Generator (based on low_ctr creatives)
        low_ctr = summary.get("low_ctr_creatives", [])
        creatives = self.creative_generator.generate(low_ctr)

        # 8) Assemble report and write outputs
        os.makedirs(out_dir, exist_ok=True)
        insights_path = os.path.join(out_dir, "insights.json")
        creatives_path = os.path.join(out_dir, "creatives.json")
        report_path = os.path.join(out_dir, "report.md")

        # write insights file
        with open(insights_path, "w", encoding="utf-8") as f:
            json.dump({"generated_at": datetime.utcnow().isoformat() + "Z", "insights": evaluated}, f, indent=2)

        # write creatives file (use returned structure directly)
        with open(creatives_path, "w", encoding="utf-8") as f:
            json.dump(creatives, f, indent=2)

        # assemble textual report
        report_text = self._assemble_report_text(evaluated, creatives, summary)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report_text)

        # 9) Log trace for observability
        trace = {
            "query": query,
            "time": datetime.utcnow().isoformat() + "Z",
            "plan": plan,
            "summary": {
                "recent_days": recent_days,
                "total_rows": int(len(df)),
                "total_impressions": summary.get("total_impressions")
            },
            "hypotheses_raw": hypotheses,
            "evaluated": evaluated
        }
        self._write_trace(trace)

        # 10) Return structured outputs for programmatic use
        return {
            "insights": evaluated,
            "creatives": creatives,
            "report": report_text,
            "trace": trace,
            "paths": {
                "insights": insights_path,
                "creatives": creatives_path,
                "report": report_path,
                "logs": self.logs_path
            }
        }
