import requests
import os

# === Telegram credentials from Render environment variables ===
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram_notification(lead_name, phone, channel, urgency, message, business_name="Sparkle Clean USA"):
    """
    Sends a Telegram notification when a CRITICAL or HIGH urgency lead comes in.
    MEDIUM and LOW leads are ignored — we don't want notification spam.
    """

    urgency_upper = urgency.upper()

    # ✅ Only notify for urgent leads — ignore MEDIUM and LOW
    if urgency_upper not in ["CRITICAL", "HIGH"]:
        return

    # 🚨 Set emoji and label based on urgency level
    if urgency_upper == "CRITICAL":
        urgency_emoji = "🚨"
        urgency_label = "CRITICAL — CALL NOW"
    else:
        urgency_emoji = "🔥"
        urgency_label = "HIGH PRIORITY"

    # 📣 Map channel name to a friendly label with emoji
    channel_emojis = {
        "whatsapp": "📱 WhatsApp",
        "facebook": "👥 Facebook",
        "webchat": "🌐 Webchat",
        "instagram": "📸 Instagram"
    }
    channel_label = channel_emojis.get(channel.lower(), f"💬 {channel}")

    # 📝 Build the notification message
    # Using HTML formatting — more reliable than Markdown for special characters
    notification = f"""{urgency_emoji} <b>{urgency_label}</b>

🏢 <b>Business:</b> {business_name}
👤 <b>Name:</b> {lead_name or "Unknown"}
📞 <b>Phone:</b> {phone}
📣 <b>Channel:</b> {channel_label}

💬 <b>Message:</b>
{message}

👉 <a href="https://dashboard.alwayzon.agency">Open Dashboard</a>"""

    try:
        # 📤 Send the message via Telegram Bot API
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": notification,
            "parse_mode": "HTML"  # HTML is safer than Markdown for user messages
        }
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 200:
            print(f"✅ Telegram notification sent — {urgency_upper} lead")
        else:
            print(f"❌ Telegram failed: {response.text}")

    except Exception as e:
        print(f"❌ Telegram error: {e}")
