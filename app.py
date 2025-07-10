# Fraud Registration Chatbot Backend (Flask)
# -------------------------------------------------
# This Flask app provides a conversational assistant for fraud complaint registration.
# It supports step-by-step complaint collection, validation, voice input (Whisper),
# and a modern frontend UI. Designed for clarity, maintainability, and extensibility.

from flask import Flask, request, jsonify, render_template, send_from_directory
import requests
import re
import json
import os
import logging
import sys
import socket
import atexit
# Requirements for audio transcription:
# pip install openai-whisper torch
# ffmpeg must be installed and available in PATH
import tempfile
import whisper

# ---------------------- Logging Setup ----------------------
logging.basicConfig(level=logging.DEBUG, filename='chatbot.log', filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------------------- Flask App Setup ----------------------
app = Flask(__name__, template_folder='templates', static_folder='static')

# ---------------------- LM Studio API Config ----------------------
LM_STUDIO_API_URL = "http://localhost:1234/v1/completions"  # Update if needed
LM_STUDIO_API_KEY = ""  # Add your LM Studio API key if required

# ---------------------- State Variables ----------------------
conversation_history = []  # Stores the conversation for context
complaint_data = {}        # Stores current complaint info
is_collecting_complaint = False  # True if in complaint registration flow
current_complaint_step = None    # Current field being collected
complaint_step_index = 0         # Index in complaint_fields
just_registered_complaint = False  # True after complaint registration
pending_complaint_start = False    # True if waiting for user to confirm registration start
user_wants_more_detail = False     # Tracks if user wants more detail in general answers

# ---------------------- Complaint Form Fields ----------------------
complaint_fields = [
    "name", "mobile_number", "age", "pan_or_aadhar", "address", 
    "description", "bank_name", "account_number", "transaction_id", 
    "date_time", "recipient_name"
]
# Extra details field and prompt for complaint registration
extra_details_field = "extra_details"
extra_details_prompt = "Is there any other detail you'd like to provide about the fraud (e.g., suspicious link, email, or other information)? If not, type 'no'."

# ---------------------- Intent Patterns ----------------------
# Patterns to detect fraud-related queries and complaint intent
fraud_patterns = [
    r"scam", r"fraud", r"cheated", r"complaint", r"report", 
    r"money.*(stolen|debited|lost)", r"link.*clicked", r"phished"
]
complaint_intent_patterns = [
    r"file a complaint", r"register a complaint", r"report fraud", r"report a scam", r"register fraud", r"lodge a complaint", r"submit a complaint", r"want to complain", r"want to report", r"register a case",
    r"start.*complaint", r"begin.*complaint", r"complaint.*fraud", r"scammed.*register", r"scammed.*complaint", r"i got scammed.*complaint", r"i want.*complaint", r"i need.*complaint", r"i wish.*complaint", r"help.*complaint", r"help.*register.*fraud", r"help.*report.*fraud", r"i want to file.*complaint", r"i want to register.*complaint", r"i want to report.*fraud", r"i want to lodge.*complaint", r"i want to submit.*complaint", r"i want to make.*complaint", r"register.*fraud.*complaint", r"report.*fraud.*complaint", r"file.*fraud.*complaint", r"scammed.*register.*complaint", r"scammed.*file.*complaint"
]
fraud_info_patterns = [
    r"what is fraud", r"types of fraud", r"phishing", r"scam", r"fraud information", r"explain fraud", r"how to avoid fraud", r"what is a phishing scam", r"fraudulent", r"identity theft"
]
cancel_patterns = [r"exit", r"cancel", r"stop", r"quit", r"no i don't want", r"no i dont want", r"don't want to register", r"dont want to register"]

# ---------------------- Validation Functions ----------------------
def validate_name(name):
    """Accept only names, not sentences. Extract if user types 'my name is ...'."""
    match = re.match(r"^[A-Za-z .'-]{2,50}$", name.strip())
    if match:
        return name.strip()
    found = re.findall(r"(?:my name is|i am|this is)\s+([A-Za-z .'-]{2,50})", name.lower())
    if found:
        return found[0].title()
    return None

def validate_mobile(mobile):
    """Validate Indian mobile number (10 digits, starts with 6-9)."""
    match = re.match(r"^[6-9][0-9]{9}$", mobile.strip())
    return match is not None

def validate_age(age):
    """Validate age (1-120)."""
    try:
        age_int = int(age)
        return 1 <= age_int <= 120
    except:
        return False

def validate_pan_or_aadhar(value):
    """Validate PAN (ABCDE1234F) or 12-digit Aadhar."""
    value = value.strip()
    pan = re.match(r"^[A-Z]{5}[0-9]{4}[A-Z]$", value.upper())
    aadhar = re.match(r"^[0-9]{12}$", value)
    return pan is not None or aadhar is not None

def validate_address(address):
    """Validate address (at least 6 characters)."""
    return len(address.strip()) > 5

def validate_description(desc):
    """Validate description (at least 10 characters)."""
    return len(desc.strip()) > 10

def validate_bank_name(bank):
    """Validate bank name (common Indian banks or non-empty)."""
    banks = ["sbi", "hdfc", "icici", "axis", "kotak", "bob", "pnb", "canara", "union", "idbi", "yes bank", "indusind", "uco", "bandhan", "federal", "rbl", "bank of india", "bank of baroda"]
    return any(b in bank.lower() for b in banks) or len(bank.strip()) > 2

def validate_account_number(acc):
    """Validate account number (9-18 digits)."""
    return re.match(r"^[0-9]{9,18}$", acc.strip()) is not None

def validate_transaction_id(txn):
    """Accept blank, 'don't know', or valid alphanumeric."""
    if txn.strip() == '' or txn.strip().lower() in ["don't know", "dont know"]:
        return True
    return re.match(r"^[A-Za-z0-9\-]{5,30}$", txn.strip()) is not None

def validate_date_time(dt):
    """Accept dd/mm/yyyy, dd-mm-yyyy, yyyy-mm-dd, etc."""
    return re.match(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{1,2}-\d{1,2})$", dt.strip()) is not None

def validate_recipient_name(name):
    """Validate recipient name (same as validate_name)."""
    return validate_name(name)

# Map each field to its validator and prompt
complaint_field_validators = {
    "name": (validate_name, "Please enter your full name (e.g., Neel Patel):"),
    "mobile_number": (validate_mobile, "Please enter a valid 10-digit Indian mobile number (starting with 6-9):"),
    "age": (validate_age, "Please enter your age (1-120):"),
    "pan_or_aadhar": (validate_pan_or_aadhar, "Please enter a valid PAN (ABCDE1234F) or 12-digit Aadhar number:"),
    "address": (validate_address, "Please enter your address (at least 6 characters):"),
    "description": (validate_description, "Please briefly describe the fraud (at least 10 characters):"),
    "bank_name": (validate_bank_name, "Please enter your bank name (e.g., SBI, HDFC, ICICI, etc.):"),
    "account_number": (validate_account_number, "Please enter your bank account number (9-18 digits):"),
    "transaction_id": (validate_transaction_id, "Please enter your transaction ID (if available). If you don't know, type 'don't know':"),
    "date_time": (validate_date_time, "Please enter the date of the incident (e.g., 01/01/2023):"),
    "recipient_name": (validate_recipient_name, "Please enter the recipient's name (if known):")
}

# ---------------------- Intent Detection Functions ----------------------
def is_fraud_related(user_input):
    """Detect if input is fraud-related."""
    return any(re.search(pattern, user_input.lower()) for pattern in fraud_patterns)

def is_complaint_intent(user_input):
    """Detect if user wants to register a complaint."""
    return any(re.search(pattern, user_input.lower()) for pattern in complaint_intent_patterns)

def is_fraud_info_intent(user_input):
    """Detect if user is asking about fraud info."""
    return any(re.search(pattern, user_input.lower()) for pattern in fraud_info_patterns)

def is_cancel_intent(user_input):
    """Detect if user wants to cancel/exit registration."""
    return any(re.search(pattern, user_input.lower()) for pattern in cancel_patterns)

def analyze_description(description):
    """Analyze description to determine if extra fields are needed."""
    additional_fields = []
    if any(keyword in description.lower() for keyword in ["link", "clicked", "debited", "transferred"]):
        additional_fields.extend(["bank_name", "account_number", "transaction_id", "date_time", "recipient_name"])
    return additional_fields

# ---------------------- LM Studio API Helper ----------------------
def generate_response(prompt):
    """Generate a response using Hermes LLaMA via LM Studio API."""
    headers = {
        "Authorization": f"Bearer {LM_STUDIO_API_KEY}" if LM_STUDIO_API_KEY else "",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt,
        "max_tokens": 512,
        "temperature": 0.7,
        "top_p": 0.9
    }
    try:
        logger.debug(f"Sending request to LM Studio with prompt: {prompt}")
        response = requests.post(LM_STUDIO_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()["choices"][0]["text"].strip()
        logger.debug(f"Received response from LM Studio: {result}")
        return result
    except requests.exceptions.RequestException as e:
        logger.error(f"LM Studio API error: {str(e)}")
        return f"Error communicating with LM Studio API: {str(e)}"

# ---------------------- Complaint Summary Generator ----------------------
def generate_complaint_summary(complaint_data):
    """Generate a summary of the complaint for user confirmation."""
    summary = (
        f"Complaint Summary:\n"
        f"Name: {complaint_data.get('name', 'N/A')}\n"
        f"Mobile Number: {complaint_data.get('mobile_number', 'N/A')}\n"
        f"Age: {complaint_data.get('age', 'N/A')}\n"
        f"PAN/Aadhar Number: {complaint_data.get('pan_or_aadhar', 'N/A')}\n"
        f"Address: {complaint_data.get('address', 'N/A')}\n"
        f"Description of Fraud: {complaint_data.get('description', 'N/A')}\n"
    )
    if "bank_name" in complaint_data:
        summary += (
            f"Bank Name: {complaint_data.get('bank_name', 'N/A')}\n"
            f"Account Number: {complaint_data.get('account_number', 'N/A')}\n"
            f"Transaction ID: {complaint_data.get('transaction_id', 'N/A')}\n"
            f"Date and Time: {complaint_data.get('date_time', 'N/A')}\n"
            f"Recipient Name: {complaint_data.get('recipient_name', 'N/A')}\n"
        )
    if 'extra_details' in complaint_data:
        summary += f"Extra Details: {complaint_data.get('extra_details', 'N/A')}\n"
    return summary

# ---------------------- Flask Routes ----------------------
@app.route('/')
def index():
    """Serve the main chat UI."""
    global conversation_history
    try:
        if not os.path.exists(os.path.join(app.template_folder, 'index.html')):
            logger.error("index.html not found in templates folder")
            return "Error: index.html not found in templates folder", 500
        conversation_history = []  # Reset history on page load
        initial_message = "Hey there! I'm Siri, your friendly Fraud Registration Assistant. Ready to help—what's on your mind?"
        conversation_history.append({"role": "assistant", "content": initial_message})
        logger.debug("Serving index.html with initial message")
        return render_template('index.html', initial_message=initial_message)
    except Exception as e:
        logger.error(f"Error serving index.html: {str(e)}", exc_info=True)
        return f"Error serving index.html: {str(e)}", 500

@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files (CSS, images, JS)."""
    try:
        if not os.path.exists(os.path.join(app.static_folder, filename)):
            logger.error(f"Static file {filename} not found in static folder")
            return f"Static file {filename} not found", 404
        return send_from_directory(app.static_folder, filename)
    except Exception as e:
        logger.error(f"Error serving static file {filename}: {str(e)}", exc_info=True)
        return f"Error serving static file: {str(e)}", 500

# ---------------------- Main Chat/Process Logic ----------------------
def handle_chat_request():
    """Shared logic for /chat and /process endpoints. Handles all chat, registration, and validation flows."""
    global is_collecting_complaint, current_complaint_step, complaint_step_index, complaint_data, user_wants_more_detail, just_registered_complaint, pending_complaint_start
    try:
        logger.debug(f"Raw request data: {request.data.decode('utf-8', errors='ignore')}")
        data = request.get_json(force=False)
        if not data:
            logger.error("No JSON payload received")
            return jsonify({"response": "Error: No JSON payload received. Please send a valid JSON payload."}), 400
        user_input = data.get('message', data.get('text', '')).strip()
        if not user_input:
            logger.error(f"Invalid JSON payload, missing 'message' or 'text': {data}")
            return jsonify({"response": "Error: Invalid input. Please send a valid JSON payload with a 'message' or 'text' field."}), 400
        logger.debug(f"Received user input: {user_input}")

        conversation_history.append({"role": "user", "content": user_input})

        # 1. Allow user to cancel registration at any time
        if is_collecting_complaint and is_cancel_intent(user_input):
            is_collecting_complaint = False
            complaint_data = {}
            complaint_step_index = 0
            current_complaint_step = None
            pending_complaint_start = False
            logger.info("Complaint registration cancelled by user.")
            response = "Complaint registration has been cancelled. If you need help with anything else, just let me know!"
            logger.info(f"Outgoing response: {str(response)[:200]}")
            return jsonify({"response": response})

        # 1.5. Handle pre-registration confirmation
        if pending_complaint_start:
            if user_input.strip().lower() in ["yes", "y"]:
                pending_complaint_start = False
                is_collecting_complaint = True
                complaint_step_index = 0
                complaint_data = {}
                complaint_data['complaint_fields_to_collect'] = complaint_fields.copy()
                current_complaint_step = complaint_fields[complaint_step_index]
                prompt = complaint_field_validators.get(current_complaint_step, (None, None))[1] or f"Please provide your {current_complaint_step.replace('_', ' ')}:"
                conversation_history.append({"role": "assistant", "content": prompt})
                logger.debug(f"Starting registration after confirmation. Sending prompt: {prompt}")
                logger.info(f"Outgoing response: {str(prompt)[:200]}")
                return jsonify({"response": prompt})
            elif user_input.strip().lower() in ["no", "n"]:
                pending_complaint_start = False
                response = "Complaint registration has been cancelled. If you need help with anything else, just let me know!"
                logger.info(f"Outgoing response: {str(response)[:200]}")
                return jsonify({"response": response})
            else:
                prompt = ("Please reply 'yes' to proceed with registering your complaint, or 'no' to cancel.")
                conversation_history.append({"role": "assistant", "content": prompt})
                logger.info(f"Outgoing response: {str(prompt)[:200]}")
                return jsonify({"response": prompt})

        # 2. If in registration flow, handle registration and return (never call LLM)
        if is_collecting_complaint:
            if 'complaint_fields_to_collect' not in complaint_data:
                complaint_data['complaint_fields_to_collect'] = complaint_fields.copy()
            fields_to_collect = complaint_data['complaint_fields_to_collect']
            # Save the user's answer for the current step
            if current_complaint_step:
                validator, error_prompt = complaint_field_validators.get(current_complaint_step, (None, None))
                valid = True
                value = user_input
                if validator:
                    result = validator(user_input)
                    if not result:
                        valid = False
                    elif isinstance(result, str):
                        value = result
                if not valid:
                    logger.info(f"Invalid input for {current_complaint_step}: {user_input}")
                    conversation_history.append({"role": "assistant", "content": error_prompt})
                    logger.info(f"Outgoing response: {str(error_prompt)[:200]}")
                    return jsonify({"response": error_prompt})
                complaint_data[current_complaint_step] = value
            # If we just got the description, check if we need to add extra fields
            if current_complaint_step == 'description':
                additional_fields = analyze_description(user_input)
                for field in additional_fields:
                    if field not in fields_to_collect:
                        fields_to_collect.append(field)
            # Move to the next field
            complaint_step_index += 1
            # If all required fields are collected, prompt for extra details
            if complaint_step_index == len(fields_to_collect):
                current_complaint_step = extra_details_field
                prompt = extra_details_prompt
                conversation_history.append({"role": "assistant", "content": prompt})
                logger.debug(f"Sending prompt: {prompt}")
                logger.info(f"Outgoing response: {str(prompt)[:200]}")
                return jsonify({"response": prompt})
            # Handle extra details step
            elif current_complaint_step == extra_details_field:
                if user_input.strip().lower() in ["no", "nothing else", "none"]:
                    complaint_data[extra_details_field] = "No extra details provided."
                else:
                    complaint_data[extra_details_field] = user_input.strip()
                is_collecting_complaint = False
                summary = generate_complaint_summary(complaint_data)
                conversation_history.append({"role": "assistant", "content": summary})
                try:
                    with open("complaints.json", "a") as f:
                        data_to_save = {k: v for k, v in complaint_data.items() if k != 'complaint_fields_to_collect'}
                        json.dump(data_to_save, f)
                        f.write("\n")
                    logger.debug("Complaint saved to complaints.json")
                    logger.info(f"Complaint registered: {json.dumps(data_to_save)}")
                except Exception as e:
                    logger.error(f"Error saving complaint: {str(e)}", exc_info=True)
                    return jsonify({"response": f"Error saving complaint: {str(e)}"}), 500
                complaint_data = {}
                complaint_step_index = 0
                current_complaint_step = None
                response = summary + "\nYour complaint has been registered. How else can I assist you?"
                logger.info(f"Outgoing response: {str(response)[:200]}")
                just_registered_complaint = True
                return jsonify({"response": response})
            elif complaint_step_index < len(fields_to_collect):
                current_complaint_step = fields_to_collect[complaint_step_index]
                prompt = complaint_field_validators.get(current_complaint_step, (None, None))[1] or f"Please provide your {current_complaint_step.replace('_', ' ')}:"
                conversation_history.append({"role": "assistant", "content": prompt})
                logger.debug(f"Sending prompt: {prompt}")
                logger.info(f"Outgoing response: {str(prompt)[:200]}")
                return jsonify({"response": prompt})

        # 3. If complaint intent detected, show pre-registration message and set flag
        if is_complaint_intent(user_input):
            pending_complaint_start = True
            instruction_msg = (
                "Before we begin registering your fraud complaint, please note:\n"
                "- Only provide the specific information requested at each step.\n"
                "- Answer in a clear and concise manner (e.g., for 'name', just type your full name).\n"
                "- If at any point you wish to stop the registration process, simply type 'exit', 'cancel', or 'stop'.\n"
                "Would you like to proceed with registering your complaint? (yes/no)"
            )
            conversation_history.append({"role": "assistant", "content": instruction_msg})
            logger.info(f"Outgoing response: {str(instruction_msg)[:200]}")
            return jsonify({"response": instruction_msg})

        # 4. If just registered, handle post-registration and return
        if just_registered_complaint:
            thank_patterns = ["thank you", "thanks", "thankyou", "thx"]
            nextstep_patterns = [
                "money back", "next step", "what should i do", "what to do", "how to recover",
                "how do i get my money", "how to get my money", "how can i get my money back",
                "what should i do to get my money back", "how to get my money back", "recover my money",
                "get my money back", "how can i recover my money", "how do i recover my money",
                "help me get my money back", "help to get my money back", "help recover my money",
                "help me recover my money", "can you help me get my money back", "can you help recover my money",
                "can you help me recover my money", "can you help me with my money back", "can you help with my money back"
            ]
            user_lower = user_input.lower()
            if any(tp in user_lower for tp in thank_patterns):
                just_registered_complaint = False
                response = "You're welcome! If you need any further help or guidance, please let me know."
                return jsonify({"response": response})
            elif any(np in user_lower for np in nextstep_patterns):
                just_registered_complaint = False
                response = ("Please promptly report the incident to your bank and keep all evidence safe. "
                            "For further assistance, you may also visit your local police station. "
                            "If you need more guidance, let me know.")
                return jsonify({"response": response})

        # 5. Only call the LLM for general questions if none of the above apply
        # Short/long answer logic for general questions
        if user_input.lower() in ["yes", "more", "tell me more", "details", "explain more"]:
            user_wants_more_detail = True
        elif user_input.lower() in ["short", "in short", "brief", "summary"]:
            user_wants_more_detail = False
        system_prompt = (
            "You are Siri, a helpful assistant who specializes in fraud registration and fraud-related topics, but you can also answer general questions if asked. "
            "For general questions, first provide a concise summary. Then ask: 'Would you like to know more about this topic?' If the user says yes, provide a detailed answer. If the user says 'short', always provide a brief answer. "
            "If the user wants to register a complaint, guide them through the process. If they ask about fraud or general knowledge, answer helpfully.\n"
            "Do not use emoticons, asterisks, or describe actions like *smiles* or *waves* in your responses. Keep your answers professional and to the point."
        )
        prompt = system_prompt
        for entry in conversation_history[-5:]:
            role = "User" if entry["role"] == "user" else "Assistant"
            prompt += f"{role}: {entry['content']}\n"
        prompt += "Assistant: "
        if user_wants_more_detail:
            prompt += "(Please provide a detailed answer.)\n"
        response = generate_response(prompt)
        conversation_history.append({"role": "assistant", "content": response})
        logger.debug(f"Sending response: {response}")
        logger.info(f"Outgoing response: {str(response)[:200]}")
        return jsonify({"response": response})

    except Exception as e:
        logger.error(f"Error in handle_chat_request: {str(e)}", exc_info=True)
        return jsonify({"response": f"Server error: {str(e)}"}), 500

# ---------------------- Chat Endpoints ----------------------
@app.route('/chat', methods=['POST'])
def chat():
    """Chat endpoint for AJAX/web requests."""
    return handle_chat_request()

@app.route('/process', methods=['POST'])
def process():
    """Process endpoint (for compatibility with frontend)."""
    return handle_chat_request()

# ---------------------- Audio Transcription Endpoint ----------------------
@app.route('/process_audio', methods=['POST'])
def process_audio():
    """Transcribe audio using Whisper and process as chat message."""
    try:
        logger.debug(f"Received audio request: {request.files}")
        if 'audio' not in request.files:
            logger.error("No audio file in request")
            return jsonify({"response": "Error: No audio file provided.", "transcription": ""}), 400
        audio_file = request.files['audio']
        # Save audio to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name
        # Load Whisper model (use 'base' for speed, 'small' or 'medium' for better accuracy)
        model = whisper.load_model('base')
        result = model.transcribe(tmp_path)
        transcription = result['text'].strip()
        logger.info(f"Audio transcription: {transcription}")
        # Process the transcription as a normal chat message
        data = {'message': transcription}
        with app.test_request_context('/chat', method='POST', json=data):
            chat_response = chat()
            chat_json = chat_response.get_json()
        return jsonify({
            "transcription": transcription,
            "response": chat_json.get('response', '')
        })
    except Exception as e:
        logger.error(f"Error in process_audio: {str(e)}", exc_info=True)
        return jsonify({"response": f"Error processing audio: {str(e)}", "transcription": ""}), 500

# ---------------------- App Startup/Shutdown ----------------------
def on_shutdown():
    logger.info('--- Application Shutdown ---')

atexit.register(on_shutdown)

if __name__ == '__main__':
    try:
        logger.info('--- Application Startup ---')
        # Check for templates and static folders
        if not os.path.exists(app.template_folder):
            logger.error(f"Templates folder {app.template_folder} does not exist")
            print(f"Error: Templates folder {app.template_folder} does not exist")
            sys.exit(1)
        if not os.path.exists(app.static_folder):
            logger.error(f"Static folder {app.static_folder} does not exist")
            print(f"Error: Static folder {app.static_folder} does not exist")
            sys.exit(1)
        # Automatically find a free port starting from 5000
        def find_free_port(start=5000, end=5010):
            for port in range(start, end):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(('localhost', port)) != 0:
                        return port
            return None
        port = find_free_port()
        if port is None:
            logger.error("No free port found in range 5000-5010")
            print("Error: No free port found in range 5000-5010")
            sys.exit(1)
        logger.info(f"Starting Flask application on port {port}")
        print(f"Flask app running on http://localhost:{port}/")
        app.run(debug=True, port=port)
    except Exception as e:
        logger.error(f"Failed to start Flask app: {str(e)}", exc_info=True)
        print(f"Error starting Flask app: {str(e)}")
        sys.exit(1)
