import os
import re
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import StrOutputParser
from .itinerary_prompt import itinerary_prompt


# ------------------------------------------------------------
# Helper: Safely extract clean JSON from model output
# ------------------------------------------------------------
def _extract_json_block(text: str) -> dict:
    """
    Extract and safely parse the first JSON object in a text response.
    Handles Markdown, commentary, or pre/post text gracefully.
    """
    if not text:
        return {}

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        print("⚠️ No JSON block found in model output. First 400 chars:\n", text[:400])
        return {}

    json_text = match.group(0)
    try:
        return json.loads(json_text)
    except json.JSONDecodeError as e:
        print("⚠️ JSON decoding failed:", e)
        print("Raw JSON snippet (first 400 chars):\n", json_text[:400])
        return {}


# ------------------------------------------------------------
# Main Generator Function (Gemini Flash + Pro Fallback)
# ------------------------------------------------------------
def generate_ai_itinerary_narrative(
    origin: str,
    destination: str,
    start_date: str,
    end_date: str,
    traveler_type: str,
    budget_total: float,
    interests: list,
    context: str,
) -> dict:
    """
    Generate narrated itinerary summary & highlights using Gemini.
    Uses gemini-flash-latest (v1 API), with fallback to gemini-pro-latest.
    Always returns structured JSON.
    """

    # Step 1: Try Gemini Flash (faster)
    try:
        model = ChatGoogleGenerativeAI(
            model="gemini-flash-latest",  # ✅ stable for v1
            temperature=0.6,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            api_base="https://generativelanguage.googleapis.com/v1",  # ✅ production API
            convert_system_message_to_human=True,
        )
    except Exception as e:
        print(f"[⚠️ Fallback] Flash model unavailable: {e}. Using gemini-pro-latest.")
        model = ChatGoogleGenerativeAI(
            model="gemini-pro-latest",
            temperature=0.6,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
            api_base="https://generativelanguage.googleapis.com/v1",
            convert_system_message_to_human=True,
        )

    # Step 2: Create the chain
    chain = itinerary_prompt | model | StrOutputParser()

    # Step 3: Prepare inputs
    input_data = {
        "origin": origin,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "traveler_type": traveler_type,
        "budget_total": budget_total,
        "interests": ", ".join(interests),
        "context": context or "No retrieved context provided.",
    }

    # Step 4: Run chain and parse output
    try:
        result = chain.invoke(input_data)
        parsed = _extract_json_block(result)

        if not parsed:
            return {
                "summary_text": f"AI Itinerary for {origin} → {destination}, {start_date}–{end_date}.",
                "highlights": ["Could not parse structured JSON"],
                "ai_commentary": result[:600] if result else "No valid output returned.",
            }

        return parsed

    except Exception as e:
        print("❌ Error generating itinerary:", e)
        return {
            "summary_text": f"Trip plan {origin} → {destination} (AI generation failed).",
            "highlights": [str(e)],
            "ai_commentary": "Fallback response due to runtime error.",
        }
