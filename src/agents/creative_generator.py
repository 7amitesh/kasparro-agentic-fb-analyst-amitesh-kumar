import os
import json
import random
import re
from typing import Dict, Any, List
from collections import Counter
from src.utils.loader import load_config

STOPWORDS = set([
    "the","and","for","with","that","this","your","you","our","are","was","is","in","on","of","a","an",
    "to","it","we","by","as","be","from","at","or","its","have","has","but","not","these","those"
])

# Simple tokenizer & keyword extractor
def extract_keywords(text: str, top_k=6):
    if not text:
        return []
    text = re.sub(r'[^a-zA-Z0-9\s]', ' ', text.lower())
    tokens = [t for t in text.split() if len(t) > 2 and t not in STOPWORDS]
    ctr = Counter(tokens)
    return [w for w,_ in ctr.most_common(top_k)]

class CreativeGenerator:
    def __init__(self, config: Dict[str, Any]):
        self.cfg = config or load_config()
        random.seed(int(self.cfg.get("random_seed", 42)))

    def generate(self, low_ctr_creatives: List[Dict[str, Any]], top_n:int=40) -> Dict[str, Any]:
        """
        Produce up to top_n creative ideas grounded in low_ctr_creatives.
        Uses extracted keywords and templates to create diverse headlines/hooks/CTAs.
        """
        messages = [ (c.get("creative_message") or "") for c in (low_ctr_creatives or []) ]
        types = [ (c.get("creative_type") or "Image") for c in (low_ctr_creatives or []) ]
        audiences = [ (c.get("audience_type") or "Broad") for c in (low_ctr_creatives or []) ]
        platforms = [ (c.get("platform") or "Facebook") for c in (low_ctr_creatives or []) ]

        # build keyword pool
        pool = Counter()
        for msg in messages:
            for kw in extract_keywords(msg, top_k=8):
                pool[kw] += 1
        top_keywords = [k for k,_ in pool.most_common(12)] or ["comfort","breathable","seamless","cooling"]

        # templates
        headline_templates = [
            "{kw}: invisible comfort, visible confidence.",
            "Stay cool with {kw}.",
            "{kw} that moves with you.",
            "No ride-up. Just {kw}.",
            "Discover {kw} for all-day comfort.",
            "Engineered {kw} for performance & comfort."
        ]
        hook_templates = [
            "Real comfort designed for long days.",
            "Built with {kw} to wick away sweat.",
            "Trusted by thousands for comfort and fit.",
            "Seamless feel under any outfit.",
            "{kw} tested during workouts and travel."
        ]
        ctas = ["Shop Now","Buy Today","Try Now","Explore Collection","Upgrade Comfort","See Best Sellers","Claim Offer"]
        image_ideas = [
            "Close-up macro of fabric texture",
            "UGC-style candid in gym setting",
            "Studio flat-lay with neutral backdrop",
            "Split-screen before/after silhouette",
            "3-angle product showcase (front/back/close-up)"
        ]
        angles = ["performance","comfort","emotional","social_proof","offer","fabric_science"]
        platform_fit = ["Facebook","Instagram","Both"]

        ideas = []
        used = set()
        # generate combinatorially from keywords and templates
        for i in range(top_n):
            kw = random.choice(top_keywords)
            htmpl = random.choice(headline_templates)
            headline = htmpl.format(kw=kw.capitalize())
            hook = random.choice(hook_templates).format(kw=kw)
            cta = random.choice(ctas)
            image = random.choice(image_ideas)
            angle = random.choice(angles)
            pf = random.choice(platform_fit)
            idea = {
                "id": f"c_adv_{i+1}",
                "headline": headline,
                "hook": hook,
                "cta": cta,
                "image_idea": image,
                "angle": angle,
                "platform_fit": pf,
                # small provenance
                "source_keywords": top_keywords[:6]
            }
            key = (headline + hook + cta)[:120]
            if key in used:
                continue
            used.add(key)
            ideas.append(idea)
            if len(ideas) >= top_n:
                break

        return {"generated_at": None, "ideas": ideas}
