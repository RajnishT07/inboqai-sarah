from flask import Flask, request, jsonify, send_from_directory
from channels.whatsapp import verify_webhook, extract_message, send_reply
from channels.instagram import extract_message as instagram_extract, send_reply as instagram_send
from channels.facebook import extract_message as facebook_extract, send_reply as facebook_send
from sarah_brain import sarah_reply
from sheets import log_lead, get_lead
from calendar_booking import create_booking, parse_appointment_time
from supabase_db import save_message, create_or_update_lead, update_lead_status  # ✅ added update_lead_status
import json
import config

app = Flask(__name__)

conversation_store = {}
processed_messages = set()

SPARKLE_CLIENT_ID = "1c08d4eb-5169-494c-88fc-41d919f6aa1e"

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "running",
        "app": "InboqAI Sarah",
        "version": "1.0"
    }), 200

# ===== WHATSAPP WEBHOOK =====

@app.route("/webhook/whatsapp", methods=["GET"])
def whatsapp_verify():
    return verify_webhook(request)

@app.route("/webhook/whatsapp", methods=["POST"])
def whatsapp_message():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    phone, text = extract_message(data)

    if not phone or not text:
        return jsonify({"status": "ignored"}), 200

    message_id = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0].get("id", "")
    if message_id and message_id in processed_messages:
        print(f"Duplicate message ignored: {message_id}")
        return jsonify({"status": "duplicate"}), 200
    if message_id:
        processed_messages.add(message_id)

    history = conversation_store.get(phone, [])

    if not history:
        existing_lead = get_lead(phone)
        if existing_lead:
            known_info = []
            if existing_lead.get("name"):
                known_info.append(f"Customer name: {existing_lead['name']}")
            if existing_lead.get("service"):
                known_info.append(f"Previously interested in: {existing_lead['service']}")
            if existing_lead.get("address"):
                known_info.append(f"Address: {existing_lead['address']}")
            if known_info:
                context = "RETURNING CUSTOMER — you already know: " + ", ".join(known_info)
                history = [{"role": "system", "content": context}]

    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=phone
    )

    conversation_store[phone] = result.get("updated_history", history)

    reply_text = result.get("reply", "").strip()
    if reply_text:
        send_reply(phone, reply_text)

    print(f"Sarah replied to {phone}")

    booking_status = "New Lead"
    full_address = result.get("address") or result.get("area") or ""

    if result.get("ready_to_book") and result.get("appointment_time"):
        appointment_dt = parse_appointment_time(result.get("appointment_time"))
        if appointment_dt:
            success, message = create_booking(
                name=result.get("name", "Customer"),
                phone=phone,
                service_name=result.get("service", ""),
                address=full_address,
                appointment_datetime=appointment_dt
            )
            if success:
                booking_status = "Booked"
                conversation_history = result.get("updated_history", history)
                conversation_history.append({
                    "role": "system",
                    "content": "BOOKING SUCCESS: Appointment successfully created in calendar. Send the booking confirmed message with all details and emojis."
                })
                conversation_store[phone] = conversation_history
            else:
                booking_status = "Booking Failed"
                conversation_history = result.get("updated_history", history)
                conversation_history.append({
                    "role": "system",
                    "content": f"BOOKING FAILED: {message}. Tell the customer that time slot is unavailable and ask them to pick a different date and time."
                })
                conversation_store[phone] = conversation_history
        else:
            booking_status = "Ready to Book"
    elif result.get("ready_to_book"):
        booking_status = "Ready to Book"

    # Save lead to Supabase
    lead_id = create_or_update_lead(
        client_id=SPARKLE_CLIENT_ID,
        phone=phone,
        name=result.get("name"),
        channel="whatsapp",
        urgency=result.get("urgency", "low")
    )

    # ✅ Auto-update status to "booked" when Sarah confirms the booking
    if result.get("booking_confirmed"):
        update_lead_status(lead_id, "booked")

    # Save the customer's message to Supabase
    save_message(
        client_id=SPARKLE_CLIENT_ID,
        lead_id=lead_id,
        role="user",
        message=text,
        session_id=f"whatsapp_{phone}",
        channel="whatsapp"
    )

    if reply_text:
        save_message(
            client_id=SPARKLE_CLIENT_ID,
            lead_id=lead_id,
            role="assistant",
            message=reply_text,
            session_id=f"whatsapp_{phone}",
            channel="whatsapp"
        )

    log_lead(
        phone=phone,
        name=result.get("name"),
        channel="WhatsApp",
        service=result.get("service"),
        address=full_address,
        urgency=result.get("urgency"),
        status=booking_status,
        last_message=text
    )

    return jsonify({"status": "ok"}), 200

# ===== INSTAGRAM WEBHOOK =====

@app.route("/webhook/instagram", methods=["GET"])
def instagram_verify():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == 'inboqai2024':
        return challenge, 200
    return 'Forbidden', 403

@app.route("/webhook/instagram", methods=["POST"])
def instagram_message():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    sender_id, text = instagram_extract(data)
    if not sender_id or not text:
        return jsonify({"status": "ignored"}), 200

    history = conversation_store.get(sender_id, [])

    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=sender_id,
        channel="Instagram"
    )

    conversation_store[sender_id] = result.get("updated_history", history)

    reply_text = result.get("reply", "").strip()
    if reply_text:
        instagram_send(sender_id, reply_text)

    lead_id = create_or_update_lead(
        client_id=SPARKLE_CLIENT_ID,
        phone=sender_id,
        name=result.get("name"),
        channel="instagram",
        urgency=result.get("urgency", "low")
    )

    # ✅ Auto-update status to "booked" when Sarah confirms the booking
    if result.get("booking_confirmed"):
        update_lead_status(lead_id, "booked")

    save_message(
        client_id=SPARKLE_CLIENT_ID,
        lead_id=lead_id,
        role="user",
        message=text,
        session_id=f"instagram_{sender_id}",
        channel="instagram"
    )

    if reply_text:
        save_message(
            client_id=SPARKLE_CLIENT_ID,
            lead_id=lead_id,
            role="assistant",
            message=reply_text,
            session_id=f"instagram_{sender_id}",
            channel="instagram"
        )

    log_lead(
        phone=sender_id,
        name=result.get("name"),
        channel="Instagram",
        service=result.get("service"),
        address=result.get("address") or result.get("area") or "",
        urgency=result.get("urgency"),
        status="New Lead",
        last_message=text
    )

    return jsonify({"status": "ok"}), 200

# ===== FACEBOOK MESSENGER WEBHOOK =====

@app.route("/webhook/facebook", methods=["GET"])
def facebook_verify():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    if mode == 'subscribe' and token == 'inboqai2024':
        return challenge, 200
    return 'Forbidden', 403

@app.route("/webhook/facebook", methods=["POST"])
def facebook_message():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    message_id = ""
    try:
        message_id = data["entry"][0]["messaging"][0]["message"]["mid"]
    except:
        pass

    if message_id and message_id in processed_messages:
        return jsonify({"status": "duplicate"}), 200
    if message_id:
        processed_messages.add(message_id)

    sender_id, text = facebook_extract(data)
    if not sender_id or not text:
        return jsonify({"status": "ignored"}), 200

    history = conversation_store.get(sender_id, [])

    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=sender_id,
        channel="Facebook"
    )

    conversation_store[sender_id] = result.get("updated_history", history)

    reply_text = result.get("reply", "").strip()
    if reply_text:
        facebook_send(sender_id, reply_text)

    lead_id = create_or_update_lead(
        client_id=SPARKLE_CLIENT_ID,
        phone=sender_id,
        name=result.get("name"),
        channel="facebook",
        urgency=result.get("urgency", "low")
    )

    # ✅ Auto-update status to "booked" when Sarah confirms the booking
    if result.get("booking_confirmed"):
        update_lead_status(lead_id, "booked")

    save_message(
        client_id=SPARKLE_CLIENT_ID,
        lead_id=lead_id,
        role="user",
        message=text,
        session_id=f"facebook_{sender_id}",
        channel="facebook"
    )

    if reply_text:
        save_message(
            client_id=SPARKLE_CLIENT_ID,
            lead_id=lead_id,
            role="assistant",
            message=reply_text,
            session_id=f"facebook_{sender_id}",
            channel="facebook"
        )

    log_lead(
        phone=sender_id,
        name=result.get("name"),
        channel="Facebook",
        service=result.get("service"),
        address=result.get("address") or result.get("area") or "",
        urgency=result.get("urgency"),
        status="New Lead",
        last_message=text
    )

    return jsonify({"status": "ok"}), 200

# ===== WEBCHAT WEBHOOK =====

@app.route("/webhook/webchat", methods=["POST"])
def webchat_message():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    sender_id = data.get("sender_id")
    text = data.get("message")

    if not sender_id or not text:
        return jsonify({"status": "ignored"}), 200

    history = conversation_store.get(sender_id, [])

    if not history:
        history = [{
            "role": "system",
            "content": "IMPORTANT: The customer already received this greeting: 'Hi there! 👋 I'm Sarah from Sparkle Clean USA! 🧹 How can I help you today?' DO NOT say hi, hello, or greet them again. Jump straight into helping them."
        }]

    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=sender_id,
        channel="Webchat"
    )

    conversation_store[sender_id] = result.get("updated_history", history)

    reply_text = result.get("reply", "").strip()

    lead_id = create_or_update_lead(
        client_id=SPARKLE_CLIENT_ID,
        phone=result.get("phone_number") or sender_id,
        name=result.get("name"),
        channel="webchat",
        urgency=result.get("urgency", "low")
    )

    # ✅ Auto-update status to "booked" when Sarah confirms the booking
    if result.get("booking_confirmed"):
        update_lead_status(lead_id, "booked")

    save_message(
        client_id=SPARKLE_CLIENT_ID,
        lead_id=lead_id,
        role="user",
        message=text,
        session_id=f"webchat_{sender_id}",
        channel="webchat"
    )

    if reply_text:
        save_message(
            client_id=SPARKLE_CLIENT_ID,
            lead_id=lead_id,
            role="assistant",
            message=reply_text,
            session_id=f"webchat_{sender_id}",
            channel="webchat"
        )

    log_lead(
        phone=result.get("phone_number") or sender_id,
        name=result.get("name"),
        channel="Webchat",
        service=result.get("service"),
        address=result.get("address") or result.get("area") or "",
        urgency=result.get("urgency"),
        status="New Lead",
        last_message=text
    )

    return jsonify({
        "status": "ok",
        "reply": reply_text
    }), 200

# ===== SERVE CHAT WIDGET =====

@app.route("/chat")
def chat_widget():
    return send_from_directory('.', 'chat_widget.html')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
