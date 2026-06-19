from flask import Flask, request, jsonify
from channels.whatsapp import verify_webhook, extract_message, send_reply
from sarah_brain import sarah_reply
import json

# === Create the Flask app ===
# This one line creates your entire web application
app = Flask(__name__)

# === In-memory conversation storage ===
# This dictionary holds conversation history for each customer
# Key = phone number, Value = list of messages
# Example: {"911234567890": [{"role": "user", "content": "Hi"}, ...]}
# NOTE: This resets when Render restarts your app
# In Phase 2 we will move this to Google Sheets for permanent storage
conversation_store = {}
processed_messages = set()  # Tracks processed message IDs to avoid duplicates

# === HOME ROUTE ===
# This is just a health check — visit your Render URL and you'll see this message
# Useful to confirm your app is running
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "app": "InboqAI Sarah",
        "version": "1.0"
    }), 200


# === WHATSAPP WEBHOOK — GET ===
# Meta calls this route ONCE when you first connect WhatsApp
# It's just a verification check — "are you really the app owner?"
@app.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_verify():
    return verify_webhook(request)


# === WHATSAPP WEBHOOK — POST ===
# Meta calls this route EVERY TIME a customer sends a message
# This is the main route — where everything happens
@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_message():
    # Step 1: Get the data Meta sent us
    data = request.get_json()

    # Step 2: Extract phone number and message text
    phone, text = extract_message(data)

    # Step 3: If extraction failed, ignore and return OK
    if not phone or not text:
        return jsonify({"status": "ignored"}), 200

    # Step 3b: Deduplication — ignore if same message was processed recently
    message_id = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0].get("id", "")
    if message_id and message_id in processed_messages:
        print(f"Duplicate message ignored: {message_id}")
        return jsonify({"status": "duplicate"}), 200
    if message_id:
        processed_messages.add(message_id)
    # Step 4: Get this customer's conversation history
    # If first time messaging, start with empty history
    history = conversation_store.get(phone, [])

    # Step 5: Send to Sarah's brain and get reply
    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=phone
    )

    # Step 6: Save updated conversation history back to store
    conversation_store[phone] = result.get("updated_history", history)

    # Step 7: Send Sarah's reply back to the customer on WhatsApp
    send_reply(phone, result["reply"])

    # Step 8: Print what Sarah detected (for debugging)
    print(f"Sarah replied to {phone}")
    print(f"Urgency: {result.get('urgency')}")
    print(f"Name: {result.get('name')}")
    print(f"Service: {result.get('service')}")
    print(f"Area: {result.get('area')}")
    print(f"Ready to book: {result.get('ready_to_book')}")

    return jsonify({"status": "ok"}), 200


# === RUN THE APP ===
# This starts your Flask app
# host="0.0.0.0" means accept connections from anywhere (required for Render)
# port=5000 is the default Flask port
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
