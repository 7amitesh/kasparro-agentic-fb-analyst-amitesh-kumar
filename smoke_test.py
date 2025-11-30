# from src.utils.loader import load_config, load_data, summarize_for_llm

# print("\n=== SMOKE TEST START ===")

# # 1. Load config
# cfg = load_config()
# print("CONFIG LOADED. Data path:", cfg.get("data_path"))

# # 2. Load CSV
# try:
#     df = load_data(cfg)
#     print("DATA LOADED. Rows:", len(df))
# except Exception as e:
#     print("DATA LOAD ERROR:", e)

# # 3. Summaries
# try:
#     s = summarize_for_llm(df, recent_days=7, top_n=3)
#     print("SUMMARY KEYS:", list(s.keys()))
# except Exception as e:
#     print("SUMMARY ERROR:", e)

# print("=== SMOKE TEST END ===\n")






# from src.utils.loader import load_config, load_data, summarize_for_llm
# from src.agents.planner import Planner
# from src.agents.data_agent import DataAgent
# from src.agents.insight_agent import InsightAgent

# if __name__ == "__main__":
# 	cfg = load_config()
# 	df = load_data(cfg)
# 	summary = summarize_for_llm(df, 7, 5)

# 	planner = Planner(cfg)
# 	plan = planner.decompose("Analyze ROAS drop in last 7 days")
# 	print("PLAN TASK COUNT:", len(plan["tasks"]))

# 	data_agent = DataAgent(cfg)
# 	tsums = data_agent.execute(plan["tasks"], summary)
# 	print("DATA SUMMARIES:", len(tsums["task_summaries"]))

# 	insight = InsightAgent(cfg)
# 	hyps = insight.generate(summary)
# 	print("HYPOTHESES:", len(hyps["hypotheses"]))





from src.utils.loader import load_config, load_data, summarize_for_llm
from src.agents.insight_agent import InsightAgent
from src.agents.evaluator import Evaluator
from src.agents.creative_generator import CreativeGenerator

if __name__ == "__main__":
    cfg = load_config()
    df = load_data(cfg)
    summary = summarize_for_llm(df, 7, 10)

    ia = InsightAgent(cfg)
    out = ia.generate(summary, df=df)
    print("HYP COUNT:", len(out.get("hypotheses", [])))
    for h in out.get("hypotheses", [])[:4]:
        print("-", h["id"], h["hypothesis"], "| conf_guess:", h.get("confidence_guess"))

    ev = Evaluator(cfg)
    sample_h = out.get("hypotheses", [])[0]
    evidence = {"pct_change_roas": out.get("hypotheses", [])[0].get("confidence_guess",0)*0.5, "sample_size": 300, "outlier_flag": False}
    res = ev.evaluate(sample_h, evidence)
    print("EVAL:", res["verdict"], "conf:", res["confidence"])

    cg = CreativeGenerator(cfg)
    ideas = cg.generate(summary.get("low_ctr_creatives", []), top_n=20)
    print("CREATIVES:", len(ideas.get("ideas",[])))
    print("SAMPLE:", ideas["ideas"][0])
