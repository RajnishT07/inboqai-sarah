import requests
import config

# === VERIFY WEBHOOK ===
# When you first connect WhatsApp to your app, Meta sends a verification request
# Meta is basically asking "are you really the owner of this app?"
# Your app must reply with the challenge token to prove it
def verify_webhook(request):
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    # Check if mode and token are correct
    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        print("WhatsApp webhook verified successfully")
        return challenge, 200
    else:
        print("WhatsApp webhook verification failed")
        return "Forbidden", 403


# === EXTRACT MESSAGE ===
# Meta sends a big messy JSON package when a customer messages you
# This function digs into that package and pulls out just what we need:
# the customer's phone number and their message text
def extract_message(data):
    try:
        # Dig into Meta's nested JSON structure
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        # Make sure this is actually a message (not a status update)
        if "messages" not in value:
            return None, None

        message = value["messages"][0]

        # We only handle text messages for now
        if message["type"] != "text":
            return None, None

        phone = message["from"]        # Customer's phone number
        text = message["text"]["body"] # Customer's message text

        return phone, text

    except Exception as e:
        print(f"Error extracting WhatsApp message: {e}")
        return None, None


# === SEND REPLY ===
# This function sends Sarah's reply back to the customer on WhatsApp
# It uses Meta's WhatsApp Business Cloud API
def send_reply(phone, message_text):
    url = f"https://graph.facebook.com/v19.0/{config.WHATSAPP_PHONE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    # This is the exact format Meta requires to send a WhatsApp message
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            print(f"Reply sent to {phone}")
            return True
        else:
            print(f"Failed to send reply: {response.text}")
            return False

    except Exception as e:
        print(f"Error sending WhatsApp reply: {e}")
        return False
