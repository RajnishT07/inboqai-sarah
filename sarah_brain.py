import json
import requests
from groq import Groq
import google.generativeai as genai
import config

# === Initialize AI clients ===
# This creates a connection to Groq and Gemini using our API keys from config.py
groq_client = Groq(api_key=config.GROQ_API_KEY)
genai.configure(api_key=config.GEMINI_API_KEY)

# === Build the system prompt ===
# This is Sarah's instruction manual — she reads this before every reply
def get_system_prompt():
    services_text = "\n".join([
        f"- {service}: {price}"
        for service, price in config.BUSINESS_SERVICES.items()
    ])
    areas_text = ", ".join(config.BUSINESS_AREAS)

    return f"""You are Sarah, a friendly and professional AI receptionist for {config.BUSINESS_NAME} in {config.BUSINESS_LOCATION}.

BUSINESS INFORMATION:
- Business Hours: {config.BUSINESS_HOURS}
- Service Areas: {areas_text}
- Services and Pricing:
{services_text}

YOUR JOB:
You help customers by answering questions, collecting their details, and booking appointments.
You must collect these 4 things naturally during the conversation:
1. Customer's full name
2. Service they need (Standard Clean, Deep Clean, or Move-Out Clean)
3. Their address (must be in our service area)
4. Preferred date and time for the appointment

URGENCY DETECTION:
At the end of every reply, you must secretly classify the lead.
If the customer uses words like "urgent", "emergency", "today", "right now", "ASAP" — they are URGENT.
Otherwise they are CASUAL.

RULES YOU MUST NEVER BREAK:
- Never ask for the customer's name if you already know it from the conversation
- Never use a different name once you know their name
- Never make up services or prices that are not listed above
- Never confirm a booking until you have all 4 details collected
- If asked about areas outside our service area, politely say we don't cover that area yet
- Always be warm, helpful, and natural — never sound like a robot
- Keep replies short — 2 to 4 sentences maximum
- Never mention you are an AI unless directly asked

RESPONSE FORMAT:
You must always reply in this exact JSON format and nothing else:
{{
  "reply": "your message to the customer here",
  "urgency": "URGENT or CASUAL",
  "name": "customer name or null if not known yet",
  "service": "service name or null if not known yet",
  "area": "their area or null if not known yet",
  "ready_to_book": true or false
}}"""


# === Ask Groq (Primary Brain) ===
# This function sends the conversation to Groq and gets Sarah's reply
def ask_groq(conversation_history):
    try:
        response = groq_client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=conversation_history,
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Groq failed: {e}")
        return None


# === Ask Gemini (Fallback Brain) ===
# This runs only if Groq fails — same job, different AI
def ask_gemini(conversation_history):
    try:
        # Gemini uses a different format so we convert the history
        model = genai.GenerativeModel(config.GEMINI_MODEL)
        
        # Build a single prompt from conversation history
        prompt = ""
        for msg in conversation_history:
            if msg["role"] == "system":
                prompt += f"INSTRUCTIONS: {msg['content']}\n\n"
            elif msg["role"] == "user":
                prompt += f"Customer: {msg['content']}\n"
            elif msg["role"] == "assistant":
                prompt += f"Sarah: {msg['content']}\n"
        
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Gemini failed: {e}")
        return None


# === Parse Sarah's JSON reply ===
# Sarah replies in JSON format — this function reads that JSON safely
def parse_sarah_reply(raw_reply):
    try:
        # Sometimes AI adds extra text before/after JSON — we clean that
        raw_reply = raw_reply.strip()
        if "```json" in raw_reply:
            raw_reply = raw_reply.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_reply:
            raw_reply = raw_reply.split("```")[1].split("```")[0].strip()
        
        parsed = json.loads(raw_reply)
        return parsed
    except Exception as e:
        print(f"JSON parse failed: {e}")
        # If parsing fails, return a safe default reply
        return {
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today?",
            "urgency": "CASUAL",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False
        }


# === Main Sarah Function ===
# This is the function every channel (WhatsApp, Instagram, Facebook) will call
def sarah_reply(customer_message, conversation_history, customer_phone):
    """
    customer_message     = the new message from the customer
    conversation_history = list of previous messages (from Google Sheets)
    customer_phone       = customer's phone number (for logging)
    
    Returns a dictionary with reply, urgency, name, service, area, ready_to_book
    """
    
    # Step 1: Build the full conversation for the AI
    # System prompt goes first, then history, then new message
    messages = [
        {"role": "system", "content": get_system_prompt()}
    ]
    
    # Add previous conversation history
    for msg in conversation_history:
        messages.append(msg)
    
    # Add the new customer message
    messages.append({
        "role": "user",
        "content": customer_message
    })
    
    # Step 2: Try Groq first
    raw_reply = ask_groq(messages)
    
    # Step 3: If Groq fails, try Gemini
    if raw_reply is None:
        print("Switching to Gemini fallback...")
        raw_reply = ask_gemini(messages)
    
    # Step 4: If both fail, return a safe default
    if raw_reply is None:
        return {
            "reply": "Hi! I'm Sarah from Sparkle Clean USA. How can I help you today?",
            "urgency": "CASUAL",
            "name": None,
            "service": None,
            "area": None,
            "ready_to_book": False
        }
    
    # Step 5: Parse the JSON reply
    result = parse_sarah_reply(raw_reply)
    
    # Step 6: Add the new messages to history for next time
    # We return updated history so it can be saved back to Google Sheets
    conversation_history.append({
        "role": "user",
        "content": customer_message
    })
    conversation_history.append({
        "role": "assistant",
        "content": raw_reply
    })
    
    result["updated_history"] = conversation_history
    
    return result
