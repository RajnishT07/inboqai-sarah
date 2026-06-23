import requests
import config

# === FETCH MESSAGE TEXT BY ID ===
# Instagram doesn't send message text in the webhook
# We have to fetch it separately using the message ID
def fetch_message_text(mid):
    url = f"https://graph.facebook.com/v19.0/{mid}"
    params = {
        "fields": "message",
        "access_token": config.INSTAGRAM_TOKEN
    }
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            text = data.get("message", "")
            print(f"Fetched message text: {text}")
            return text
        else:
            print(f"Failed to fetch message: {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching message text: {e}")
        return None

# === EXTRACT MESSAGE ===
def extract_message(data):
    try:
        print(f"Instagram raw data: {data}")

        entry = data["entry"][0]

        # Real DMs come as 'messaging' structure
        if "messaging" in entry:
            messaging = entry["messaging"][0]
            sender_id = messaging.get("sender", {}).get("id")

            if not sender_id:
                return None, None

            # Ignore events from our own account
            if sender_id == config.INSTAGRAM_ACCOUNT_ID:
                print("Ignoring own account event")
                return None, None

            # Real DMs come as message_edit — fetch the text using mid
            if "message_edit" in messaging:
                mid = messaging["message_edit"].get("mid")
                if not mid:
                    return None, None
                text = fetch_message_text(mid)
                if not text:
                    return None, None
                return sender_id, text

            # Normal message structure
            if "message" not in messaging:
                return None, None

            message = messaging["message"]

            if message.get("is_echo"):
                return None, None

            if "text" not in message:
                return None, None

            text = message["text"]
            return sender_id, text

        # Meta test events come as 'changes' structure
        elif "changes" in entry:
            change = entry["changes"][0]
            value = change["value"]
            sender_id = value["sender"]["id"]

            if "message" not in value:
                return None, None

            message = value["message"]

            if "text" not in message:
                return None, None

            text = message["text"]
            return sender_id, text

        return None, None

    except Exception as e:
        print(f"Error extracting Instagram message: {e}")
        return None, None

# === SEND REPLY ===
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
