// Chat logic for modern UI
const chatBox = document.getElementById('chat-box');
const chatForm = document.getElementById('chat-form');
const userInput = document.getElementById('user-input');
const micBtn = document.getElementById('mic-btn');

// Night mode toggle
let nightMode = false;
const nightToggle = document.createElement('button');
nightToggle.className = 'night-toggle';
nightToggle.title = 'Toggle Night Mode';
nightToggle.textContent = '🌙';
document.querySelector('.chat-header').appendChild(nightToggle);
nightToggle.onclick = () => {
    nightMode = !nightMode;
    document.body.classList.toggle('night-mode', nightMode);
    nightToggle.textContent = nightMode ? '☀️' : '🌙';
    localStorage.setItem('nightMode', nightMode);
};
window.addEventListener('DOMContentLoaded', () => {
    if (localStorage.getItem('nightMode') === 'true') {
        nightMode = true;
        document.body.classList.add('night-mode');
        nightToggle.textContent = '☀️';
    }
});

// Voice input (Web Speech API)
let recognition;
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.lang = 'en-IN';
    recognition.continuous = false;
    recognition.interimResults = false;
    micBtn.onclick = () => {
        recognition.start();
        micBtn.classList.add('listening');
    };
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        userInput.value = transcript;
        micBtn.classList.remove('listening');
    };
    recognition.onerror = () => {
        micBtn.classList.remove('listening');
    };
    recognition.onend = () => {
        micBtn.classList.remove('listening');
    };
} else {
    micBtn.disabled = true;
    micBtn.title = 'Speech recognition not supported';
}

// Message rendering
function appendMessage(message, sender = 'bot') {
    const msgDiv = document.createElement('div');
    // Always use correct class for alignment
    msgDiv.className = sender === 'user' ? 'chat-message user' : 'chat-message bot';
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    if (sender === 'bot') {
        const img = document.createElement('img');
        img.src = '/static/pngegg.png';
        img.alt = 'Bot';
        img.style.width = '32px';
        img.style.height = '32px';
        img.style.borderRadius = '50%';
        avatar.appendChild(img);
    } else {
        avatar.textContent = '🧑';
    }
    const box = document.createElement('div');
    box.className = 'message-box';
    box.textContent = message;
    msgDiv.appendChild(avatar);
    msgDiv.appendChild(box);
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
}

// Initial message
window.onload = () => {
    appendMessage("Hey there! I'm Siri, your friendly Fraud Registration Assistant. Ready to help—what's on your mind?", 'bot');
};

// Chat form submit
chatForm.onsubmit = async (e) => {
    e.preventDefault();
    const text = userInput.value.trim();
    if (!text) return;
    appendMessage(text, 'user');
    userInput.value = '';
    try {
        const response = await fetch('/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        appendMessage(data.response, 'bot');
        speak(data.response);
    } catch (err) {
        appendMessage('Sorry, something went wrong. Please try again.', 'bot');
    }
};

// Voice output (Text-to-Speech)
function speak(text) {
    if (!('speechSynthesis' in window)) return;
    function getUKVoice() {
        const voices = window.speechSynthesis.getVoices();
        // Prefer Google UK English Female, then any en-GB, then any female, then first
        let voice = voices.find(v => v.name === 'Google UK English Female');
        if (!voice) voice = voices.find(v => v.lang === 'en-GB');
        if (!voice) voice = voices.find(v => v.name.toLowerCase().includes('female'));
        if (!voice) voice = voices[0];
        return voice;
    }
    function doSpeak() {
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = 'en-GB';
        utterance.rate = 1.0;
        utterance.pitch = 1.1;
        utterance.volume = 1.0;
        utterance.voice = getUKVoice();
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
    }
    // Wait for voices to be loaded
    if (window.speechSynthesis.getVoices().length === 0) {
        window.speechSynthesis.onvoiceschanged = doSpeak;
    } else {
        doSpeak();
    }
} 
