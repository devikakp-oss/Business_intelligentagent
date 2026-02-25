from dotenv import load_dotenv
import os
from openai import OpenAI
import json

# Load environment variables
load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")

def extract_intent(question):
    client = OpenAI(
        api_key=openai_api_key
    )
    system_prompt = """
You are an AI assistant for a business intelligence system. Analyze the user's question and extract the intent as structured JSON.

Return ONLY valid JSON with the following structure:

{
  "board": "deals" | "work_orders" | "both" | null,
  "sector": string or null,
  "time_period": "this_quarter" | "last_quarter" | "all_time" | null,
  "analysis_type": "pipeline" | "revenue" | "execution" | "leadership_update" | null
}

If the question is unclear or missing key information, return:

{
  "clarification_needed": true,
  "message": "Please clarify your question, e.g., specify which board or time period."
}

Do not perform any calculations. Only extract intent.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question}
            ],
            max_tokens=300,
            temperature=0
        )
        content = response.choices[0].message.content.strip()
        # Parse JSON
        intent = json.loads(content)
        return intent
    except Exception as e:
        if "insufficient_quota" in str(e) or "rate" in str(e).lower():
            return {
                "llm_error": True,
                "message": "LLM service unavailable due to quota or rate limits."
            }
        else:
            return {"error": str(e)}

# Test
question = "What's the total pipeline value for Q1 2024?"
intent = extract_intent(question)
print(json.dumps(intent, indent=2))