import requests
import os

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_notification(lead_name, phone, channel, urgency, message, business_name="Sparkle Clean USA"):
    """
    Sends a notification to your Telegram when a CRITICAL or HIGH urgency lead comes in.
    Only fires for CRITICAL and HIGH — ignores MEDIUM and LOW.
    """
    urgency_upper = urgency.upper()

    # Only notify for CRITICAL and HIGH
    if urgency_upper not in ["CRITICAL", "HIGH"]:
        return

    # Urgency emoji
    if urgency_upper == "CRITICAL":
        urgency_emoji = "🚨"
        urgency_label = "CRITICAL — CALL NOW"
    else:
        urgency_emoji = "🔥"
        urgency_label = "HIGH PRIORITY"

    # Channel emoji
    channel_emojis = {
        "whatsapp": "📱 WhatsApp",
        "facebook": "👥 Facebook",
        "webchat": "🌐 Webchat",
        "instagram": "📸 Instagram"
    }
    channel_label = channel_emojis.get(channel.lower(), f"💬 {channel}")

    # Build message
    notification = f"""{urgency_emoji} *{urgency_label}*

🏢 *Business:* {business_name}
👤 *Name:* {lead_name or "Unknown"}
📞 *Phone:* {phone}
📣 *Channel:* {channel_label}

💬 *Message:*
_{message}_

👉 [Open Dashboard](https://dashboard.alwayzon.agency)"""

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": notification,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print(f"✅ Telegram notification sent — {urgency_upper} lead")
        else:
            print(f"❌ Telegram failed: {response.text}")

    except Exception as e:
        print(f"❌ Telegram error: {e}")
