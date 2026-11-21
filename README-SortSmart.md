# 🌿 SortSmart — AI Waste Sorting Assistant for India

> One photo in. A clearer disposal decision out.  
> Built for everyday India — English · हिन्दी · ਪੰਜਾਬੀ

---

## 🚀 Quick Start (One Click)

**Double-click `SortSmart.command`** on your Desktop — it starts everything automatically:
1. Ollama service (AI vision)
2. LLaVA model (photo analysis)
3. SortSmart web server
4. Opens `http://localhost:8000` in your browser

> First time: macOS will ask "Are you sure?" — right-click → Open → Open

**To stop:** Double-click `StopSortSmart.command`

---

## 📱 Access from Your Phone

Connect phone to the **same WiFi**, then open:
```
http://192.168.105.18:8000
```
(Check your Mac's actual IP if this doesn't work: Apple menu → System Settings → WiFi)

---

## ✨ Features

### 🔍 AI Analysis
| Mode | How it works |
|---|---|
| 📷 **Photo mode** | Take or upload a photo → LLaVA (Ollama, local, FREE) analyses it |
| ✏️ **Description mode** | Type what it is → Groq AI analyses it in your language |
| 🎙️ **Voice input** | Tap the mic button, speak your item description |

### 🌐 Languages
- 🇬🇧 **English** — full support
- 🇮🇳 **हिन्दी (Hindi)** — full support (item, reason, prep steps all in Hindi)
- 🌾 **ਪੰਜਾਬੀ (Punjabi)** — full support (item, reason, prep steps all in Punjabi)

> **How languages work:**  
> Photo mode → Ollama/LLaVA (local vision model)  
> Description mode → Groq AI (multilingual text model) → proper Hindi/Punjabi output

### 🔊 Voice Output (Read Aloud)
- **Auto-read toggle** — check "🔊 Auto-read results aloud" to hear every result automatically
- **Manual** — click "🔊 Read result aloud" after any result
- Uses your device's built-in voice (en-IN / hi-IN / pa-IN)

### 📍 Location & Recycling Points
- **GPS** — tap "📍 Use my GPS location" for instant nearby search
- **City/area search** — type any city, area, or PIN code (e.g. "Ludhiana", "141001")
- **Interactive map** — Leaflet map with 📍 your location and ♻️ recycling points
- **Fallback** — if map data unavailable, shows a Google Maps search link
- Location shown as a permanent card (always visible, not hidden after results)

### 📊 Sorting Streams
| Stream | What goes in |
|---|---|
| 🟢 **Wet** | Food waste, vegetable peels, cooked food |
| 🔵 **Dry** | Paper, plastic, glass, metal, cardboard |
| 🟡 **Sanitary** | Used tissues, diapers, bandages |
| 🔴 **Special Care** | Batteries, e-waste, chemicals, medicine |

### 🧮 Personal Tally
Tracks how many items you've sorted correctly (saved in browser, never uploaded).

---

## 📂 Project Files

```
SortSmart/
├── SortSmart.command        ← ▶️ Double-click to START (macOS)
├── StopSortSmart.command    ← ⏹️ Double-click to STOP
├── run.sh                   ← Full startup script (called by .command)
├── web_app.py               ← Flask web server (main backend)
├── sortsmart.py             ← Groq AI backend (text/description mode + multilingual)
├── sortsmart_ollama.py      ← Ollama/LLaVA backend (photo mode)
├── sortsmart_claude.py      ← Anthropic Claude backend (optional)
├── .env                     ← API keys and settings (DO NOT SHARE)
├── requirements.txt         ← Python dependencies
├── templates/
│   └── index.html           ← Main web page
├── static/
│   ├── app.js               ← All frontend logic (location, voice, map, etc.)
│   ├── styles.css           ← UI styles (dark theme)
│   ├── manifest.webmanifest ← PWA manifest
│   └── service-worker.js    ← Offline support
└── tests/                   ← Test scripts
```

---

## ⚙️ Configuration (`.env`)

```env
# Groq API key — for description mode + Hindi/Punjabi support
# Free at: https://console.groq.com/keys
GROQ_API_KEY=your_key_here
GROQ_MODEL=openai/gpt-oss-120b

# Ollama — for photo/vision mode (FREE, runs locally)
OLLAMA_MODEL=llava

# Provider: ollama | groq | anthropic
SORTSMART_PROVIDER=ollama
```

> When `SORTSMART_PROVIDER=ollama`:  
> - 📷 Photos → Ollama/LLaVA (local, FREE)  
> - ✏️ Descriptions → Groq (multilingual, Hindi/Punjabi)

---

## 🛠️ Manual Setup (if one-click doesn't work)

```bash
# 1. Install Ollama
brew install ollama

# 2. Pull LLaVA vision model (4.7 GB, one-time download)
ollama pull llava

# 3. Start Ollama
brew services start ollama

# 4. Set up Python
cd ~/Desktop/SortSmart
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 5. Start the server
.venv/bin/python web_app.py --host 0.0.0.0 --port 8000

# 6. Open in browser
open http://localhost:8000
```

---

## 🌐 API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/` | GET | Main web app |
| `/api/analyze` | POST | Analyse photo or description |
| `/api/status` | GET | Check AI provider status |
| `/api/geocode?q=city` | GET | Convert city name to lat/lon |
| `/api/dropoffs?lat=&lon=` | GET | Find nearby recycling points |
| `/api/ollama-status` | GET | Check Ollama health |

---

## ⚠️ Notes

- **Sorting guidance is a prototype** — not an official municipal ruling. Local rules vary.
- **Photo confidence may be lower** for unusual or unclear images. Use description mode for better accuracy.
- **Recycling point data** comes from OpenStreetMap — coverage varies by city. If unavailable, a Google Maps fallback link is shown.
- **Privacy:** Photos are processed locally (Ollama). Descriptions go to Groq. Location only goes to OpenStreetMap's public API. Nothing is stored by SortSmart.

---

*SortSmart / Pilot — Built with ❤️ for everyday India*
