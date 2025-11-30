import os
from dotenv import load_dotenv
import openai

load_dotenv()
key = os.getenv("OPENAI_API_KEY")
print("KEY FOUND?", bool(key))

openai.api_key = key

try:
    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role":"user","content":"Say test"}]
    )
    print("LLM WORKING:", r["choices"][0]["message"]["content"])
except Exception as e:
    print("ERROR:", e)
