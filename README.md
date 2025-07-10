# CompliBot
CompliBot is a dual-purpose AI assistant designed to simplify fraud complaint registration and answer general queries using large language models. With voice-enabled interaction, real-time validation, and smooth chat UX, it offers an intuitive user experience for both formal complaint filing and informal knowledge-seeking.

🚀 Features
Conversational Fraud Complaint Registration
Step-by-step collection of all required details for fraud reporting, with validation for Indian context.
Voice Input
Users can speak their complaint using browser voice recognition or upload audio (transcribed with Whisper).
Modern Chat UI
Responsive, glassmorphic chatbox with avatars, night/day mode, and animated backgrounds.
AI-Powered
Uses a local LLM (Hermes LLaMA via LM Studio) for natural conversation and fraud-related queries.
Professional Guidance
Provides actionable next steps after complaint registration.
Easy to Customize
Well-commented code, modular design, and ready for extension.

🛠️ Tech Stack
Backend: Python, Flask
Frontend: HTML, CSS, JavaScript
AI/LLM: Hermes LLaMA via LM Studio API
Voice: OpenAI Whisper (for audio transcription)
UI: Responsive, animated, glassmorphic design

⚙️ Setup & Installation
1. Clone the repository

2. Install Python dependencies
pip install flask requests openai-whisper torch

3. Install ffmpeg (required for Whisper)
Download ffmpeg and add it to your system PATH.

4. (Optional) Set up LM Studio
Download and run LM Studio and load a compatible LLM (e.g., Hermes LLaMA).
Ensure the API is available at http://localhost:1234/v1/completions (or update in app.py).

5. Run the app
python app.py
(The app will start on the first available port (e.g., http://localhost:5000/).)

🎤 Voice Input
Browser voice input: Click the microphone button to use your browser’s speech recognition.
Audio file upload: (If enabled) Record and upload audio; the backend will transcribe it using Whisper.

📝 How It Works
Users can chat with the bot to ask about fraud, register a complaint, or get guidance.
When registering a complaint, the bot collects all required details step-by-step, with validation.
After registration, the bot provides professional next steps (e.g., contact your bank, visit police).
All logic is explained in the code with clear comments for easy understanding.

📁 Project Structure
Fraud_Chatbot/
├── app.py                # Main Flask backend
├── templates/
│   └── index.html        # Chat UI
├── static/
│   ├── style.css         # Chat UI styles
│   ├── chat.js           # Chat/voice/night mode logic
│   └── pngegg.png        # Bot avatar/logo
└── README.md             # Project documentation

🛡️ Security & Privacy
No complaints are stored by default (unless you enable saving in the code).
Voice/audio is processed locally using Whisper; no data is sent to third-party APIs.
For production, consider using HTTPS and secure deployment practices.

🤝 Contributing
Contributions, issues, and feature requests are welcome!
Feel free to open an issue or submit a pull request.

