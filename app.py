from flask import Flask, request, jsonify
from channels.whatsapp import verify_webhook, extract_message, send_reply
from channels.instagram import extract_message as instagram_extract, send_reply as instagram_send
from sarah_brain import sarah_reply
from sheets import log_lead, get_lead
from calendar_booking import create_booking, parse_appointment_time
from channels.facebook import extract_message as facebook_extract, send_reply as facebook_send
import json

app = Flask(__name__)

conversation_store = {}
processed_messages = set()

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
    # Step 1: Get data Meta sent
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    # Step 2: Extract phone and message
    phone, text = extract_message(data)

    # Step 3: If extraction failed ignore
    if not phone or not text:
        return jsonify({"status": "ignored"}), 200

    # Step 3b: Deduplication
    message_id = data.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0].get("id", "")
    if message_id and message_id in processed_messages:
        print(f"Duplicate message ignored: {message_id}")
        return jsonify({"status": "duplicate"}), 200
    if message_id:
        processed_messages.add(message_id)

    # Step 4: Get conversation history
    history = conversation_store.get(phone, [])

    # Step 4b: Load from Sheets if memory is empty
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
                print(f"Loaded existing customer: {existing_lead.get('name')}")

    # Step 5: Send to Sarah's brain
    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=phone
    )

    # Step 6: Save updated history
    conversation_store[phone] = result.get("updated_history", history)

    # Step 7: Send reply to customer
    reply_text = result.get("reply", "").strip()
    if reply_text:
        send_reply(phone, reply_text)
    else:
        print(f"Empty reply detected — skipping send")

    # Step 8: Debug logs
    print(f"Sarah replied to {phone}")
    print(f"Urgency: {result.get('urgency')}")
    print(f"Name: {result.get('name')}")
    print(f"Service: {result.get('service')}")
    print(f"Area: {result.get('area')}")
    print(f"Ready to book: {result.get('ready_to_book')}")

    # Step 9: Handle booking
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
                print(f"Booking created for {phone}")
                conversation_history = result.get("updated_history", history)
                conversation_history.append({
                    "role": "system",
                    "content": "BOOKING SUCCESS: Appointment successfully created in calendar. Send the booking confirmed message with all details and emojis."
                })
                conversation_store[phone] = conversation_history
            else:
                booking_status = "Booking Failed"
                print(f"Booking failed: {message}")
                conversation_history = result.get("updated_history", history)
                conversation_history.append({
                    "role": "system",
                    "content": f"BOOKING FAILED: {message}. Tell the customer that time slot is unavailable and ask them to pick a different date and time. Do NOT say booking confirmed."
                })
                conversation_store[phone] = conversation_history
        else:
            booking_status = "Ready to Book"
    elif result.get("ready_to_book"):
        booking_status = "Ready to Book"

    # Step 10: Log to Google Sheets
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
        print("Instagram webhook verified!")
        return challenge, 200
    else:
        return 'Forbidden', 403

@app.route("/webhook/instagram", methods=["POST"])
def instagram_message():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "ignored"}), 200

    # Extract sender ID and message
    sender_id, text = instagram_extract(data)

    if not sender_id or not text:
        return jsonify({"status": "ignored"}), 200

    # Get conversation history
    history = conversation_store.get(sender_id, [])

    # Send to Sarah's brain
    result = sarah_reply(
        customer_message=text,
        conversation_history=history,
        customer_phone=sender_id
    )

    # Save updated history
    conversation_store[sender_id] = result.get("updated_history", history)

    # Send reply
    reply_text = result.get("reply", "").strip()
    if reply_text:
        instagram_send(sender_id, reply_text)
    else:
        print(f"Empty Instagram reply detected — skipping send")

    # Debug logs
    print(f"Sarah replied on Instagram to {sender_id}")
    print(f"Urgency: {result.get('urgency')}")
    print(f"Name: {result.get('name')}")
    print(f"Service: {result.get('service')}")

    # Log to Google Sheets
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
        print("Facebook webhook verified!")
        return challenge, 200
    else:
        return 'Forbidden', 403

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
