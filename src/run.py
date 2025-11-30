#!/usr/bin/env python3
"""
CLI entrypoint for the Kasparro agentic FB analyst pipeline.

Usage:
    python -m src.run "Analyze ROAS drop in last 7 days"
    python -m src.run "Analyze ROAS drop" --no-llm --sample --out-dir reports/sample_run
"""
import os
import sys
import argparse
import json
from src.utils.loader import load_config, load_data
from src.orchestrator import Orchestrator

def parse_args(argv):
    p = argparse.ArgumentParser(prog="kasparro-agentic-run")
    p.add_argument("query", type=str, help="Natural language query (wrap in quotes)")
    p.add_argument("--no-llm", action="store_true", help="Force offline fallback (disable LLM calls)")
    p.add_argument("--sample", action="store_true", help="Use sample data (config.use_sample_data toggled)")
    p.add_argument("--out-dir", type=str, default="reports", help="Output directory for reports")
    return p.parse_args(argv)

def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    args = parse_args(argv)
    cfg = load_config()

    # toggle sample data
    if args.sample:
        cfg["use_sample_data"] = True

    # toggle LLM usage
    if args.no_llm:
        cfg["openai_enabled"] = False

    # instantiate orchestrator
    orchestrator = Orchestrator(cfg)
    try:
        result = orchestrator.run(args.query, out_dir=args.out_dir)
        print("Done. Reports written to", args.out_dir)
        print("Files:", json.dumps(result["paths"], indent=2))
        return 0
    except Exception as e:
        print("ERROR: pipeline failed:", e)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
