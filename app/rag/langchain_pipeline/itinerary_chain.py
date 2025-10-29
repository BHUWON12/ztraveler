import os
import re
import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser  # ✅ updated import
from .itinerary_prompt import itinerary_prompt


# ------------------------------------------------------------
# 🧩 Helper: safely extract JSON from model output
# ------------------------------------------------------------
def _extract_json_block(text: str) -> dict:
    """
    Extract and safely parse the first JSON object in a text response.
    Handles Markdown, commentary, or pre/post text gracefully.
    """
    if not text:
        return {}

    match = re.search(r"\{[\s\S]*\}", text)
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
# 🚀 Main Function: Generate itinerary narrative (Gemini Flash + Pro Fallback)
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
    Uses gemini-flash-latest (v1 API) with fallback to gemini-pro-latest.
    Always returns structured JSON.
    """

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        print("⚠️ Missing GOOGLE_API_KEY environment variable.")
        return {
            "summary_text": "Missing Google API Key",
            "highlights": ["No valid API key provided."],
            "ai_commentary": "Set GOOGLE_API_KEY in environment variables.",
        }

    # Step 1️⃣: Try Gemini Flash model
    try:
        model = ChatGoogleGenerativeAI(
            model="gemini-flash-latest",
            temperature=0.6,
            google_api_key=google_api_key,
            api_base="https://generativelanguage.googleapis.com/v1",
            convert_system_message_to_human=True,
        )
    except Exception as e:
        print(f"[⚠️ Fallback] gemini-flash-latest failed: {e}")
        model = ChatGoogleGenerativeAI(
            model="gemini-pro-latest",
            temperature=0.6,
            google_api_key=google_api_key,
            api_base="https://generativelanguage.googleapis.com/v1",
            convert_system_message_to_human=True,
        )

    # Step 2️⃣: Build LangChain pipeline
    chain = itinerary_prompt | model | StrOutputParser()

    # Step 3️⃣: Input preparation
    input_data = {
        "origin": origin,
        "destination": destination,
        "start_date": start_date,
        "end_date": end_date,
        "traveler_type": traveler_type,
        "budget_total": budget_total,
        "interests": ", ".join(interests) if interests else "general",
        "context": context or "No retrieved context provided.",
    }

    # Step 4️⃣: Execute and handle response
    try:
        result = chain.invoke(input_data)
        parsed = _extract_json_block(result)

        if not parsed:
            return {
                "summary_text": f"AI Itinerary for {origin} → {destination}, {start_date}–{end_date}.",
                "highlights": ["Could not parse structured JSON from model output."],
                "ai_commentary": result[:800] if result else "Empty response.",
            }

        return parsed

    except Exception as e:
        print("❌ Exception during AI itinerary generation:", e)
        return {
            "summary_text": f"Trip plan {origin} → {destination} (AI generation failed).",
            "highlights": [str(e)],
            "ai_commentary": "Fallback response due to runtime error.",
        }
