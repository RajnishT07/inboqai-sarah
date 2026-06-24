import requests
import config

# === EXTRACT MESSAGE ===
# Facebook sends a JSON package when someone messages your page
# This function pulls out the sender's ID and message text
def extract_message(data):
    try:
        print(f"Facebook raw data: {data}")

        entry = data["entry"][0]
        messaging = entry["messaging"][0]

        sender_id = messaging["sender"]["id"]

        # Ignore messages from your own page
        if sender_id == config.FACEBOOK_PAGE_ID:
            print("Ignoring own page event")
            return None, None

        if "message" not in messaging:
            return None, None

        message = messaging["message"]

        # Ignore echoes (your own sent messages)
        if message.get("is_echo"):
            return None, None

        if "text" not in message:
            return None, None

        text = message["text"]
        return sender_id, text

    except Exception as e:
        print(f"Error extracting Facebook message: {e}")
        return None, None

# === SEND REPLY ===
# Sends Sarah's reply back to the customer on Facebook Messenger
def send_reply(sender_id, message_text):
    url = f"https://graph.facebook.com/v19.0/{config.FACEBOOK_PAGE_ID}/messages"

    headers = {
        "Authorization": f"Bearer {config.FACEBOOK_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "recipient": {
            "id": sender_id
        },
        "message": {
            "text": message_text
        },
        "messaging_type": "RESPONSE"
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            print(f"Facebook reply sent to {sender_id}")
            return True
        else:
            print(f"Failed to send Facebook reply: {response.text}")
            return False
    except Exception as e:
        print(f"Error sending Facebook reply: {e}")
        return False
