import requests
import config

# === EXTRACT MESSAGE ===
# Meta sends a JSON package when someone DMs you on Instagram
# This function digs in and pulls out the sender's ID and message text
def extract_message(data):
    try:
        entry = data["entry"][0]
        messaging = entry["messaging"][0]

        sender_id = messaging["sender"]["id"]  # Instagram user ID

        # Make sure it's a text message
        if "message" not in messaging:
            return None, None

        message = messaging["message"]

        # Ignore if it's an echo (your own sent messages)
        if message.get("is_echo"):
            return None, None

        # We only handle text messages for now
        if "text" not in message:
            return None, None

        text = message["text"]
        return sender_id, text

    except Exception as e:
        print(f"Error extracting Instagram message: {e}")
        return None, None

# === SEND REPLY ===
# Sends Sarah's reply back to the customer on Instagram DM
def send_reply(sender_id, message_text):
    url = f"https://graph.facebook.com/v19.0/{config.INSTAGRAM_ACCOUNT_ID}/messages"

    headers = {
        "Authorization": f"Bearer {config.INSTAGRAM_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {
            "id": sender_id
        },
        "message": {
            "text": message_text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"Instagram reply sent to {sender_id}")
            return True
        else:
            print(f"Failed to send Instagram reply: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending Instagram reply: {e}")
        return False
