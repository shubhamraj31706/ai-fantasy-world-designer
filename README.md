# AI Fantasy World Designer

Domain-Specific Generative AI Chatbot for **fantasy world-building** (academic/viva friendly).

## Problem statement
Building an immersive fictional world (geography, history, creatures, magic, plot hooks) takes time and consistency. A general chatbot may drift off-topic or forget details.

## Solution (what this project does)
- Generates a **structured fantasy world blueprint** from a single user idea.
- Provides a **ChatGPT-like lore chatbot** that:
  - stays **strictly in the fantasy domain**
  - maintains **session memory** (chat history + world context)
- Supports:
  - **save/load worlds** (simple JSON storage)
  - **download** saved worlds as `.txt`
  - **dark/light theme** toggle

## Tech stack
- **Frontend**: HTML, CSS, Vanilla JS (responsive, dark fantasy theme)
- **Backend**: Python **Flask**
- **Generative AI API**: **Google Gemini API**
- **Storage**: JSON file (`backend/storage/worlds.json`)
- **Session memory**: server-side sessions (`Flask-Session`)

## API used
This app calls the Gemini API from the backend:
- Generates a **JSON world object** (`response_mime_type: application/json` + JSON schema)
- Continues lore conversation using **session chat history**

## Data flow (important for viva)
User input → Frontend → Backend → OpenAI API → Backend → Frontend UI

Concrete mapping:
- **World generation**
  - User types idea in the UI → `POST /api/generate-world`
  - Flask builds a domain-restricted prompt → OpenAI returns **JSON**
  - Flask stores the world in the **session** and returns it to UI
  - UI renders world cards
- **Lore chat**
  - User message → `POST /api/chat`
  - Flask sends **(system + world context + chat history + user message)** to OpenAI
  - Reply returns to UI and is appended to the chat

## Folder structure
```
ai-fantasy-world-new/
  backend/
    app.py
    world_store.py
    storage/
      worlds.json
  frontend/
    index.html
    styles.css
    app.js
  requirements.txt
  .env.example
  README.md
```

## Setup & run (Windows)
1) Create a virtual environment:
```bash
python -m venv .venv
.venv\Scripts\activate
```

2) Install dependencies:
```bash
pip install -r requirements.txt
```

3) Create `.env` (copy from example):
```bash
copy .env.example .env
```
Edit `.env` and set:
- `OPENAI_API_KEY`
- `FLASK_SECRET_KEY`

4) Run the backend (serves frontend too):
```bash
python backend\app.py
```

5) Open in browser:
- `http://localhost:5000`

## Backend endpoints (for evaluation)
- `GET /health` → health check
- `POST /api/generate-world` → generate structured world
  - body: `{ "idea": "..." }`
- `POST /api/chat` → lore chatbot
  - body: `{ "message": "..." }`
- `GET /api/worlds` → list saved worlds
- `POST /api/worlds/save` → save current session world
  - body: `{ "title": "...", "id": "optional_existing_id" }`
- `POST /api/worlds/load` → load a saved world into session
  - body: `{ "id": "..." }`
- `GET /api/worlds/download/<id>.txt` → download saved world as text

## Prompt engineering (domain restriction)
The backend uses a **system prompt** that forces:
- fantasy-only content
- refusal + redirection if user asks non-fantasy topics
It also instructs the model to output a **single JSON object** for world generation.

## Viva Q&A (sample answers)
### What is temperature?
**Temperature controls randomness** in token selection.
- Low temperature (e.g., 0.1) → more deterministic, safer, repetitive
- Higher temperature (e.g., 1.0) → more creative, more variation, higher risk of drifting

### What is top-p?
**Top-p (nucleus sampling)** limits sampling to the smallest set of tokens whose cumulative probability is \(p\).
- If `top_p = 0.9`, the model samples only from the most likely tokens that together make 90% probability mass.

### Why temperature = 0.7 and top-p = 0.9 here?
- **temperature = 0.7**: balanced creativity for storytelling while keeping coherence.
- **top_p = 0.9**: allows variety without picking extremely unlikely tokens (reduces nonsense).

### How does the OpenAI API work in this project?
- Frontend never calls the Gemini API directly.
- Frontend calls Flask endpoints.
- Flask sends prompts (system + context + chat transcript) to Gemini.
- Gemini returns generated text/JSON; Flask forwards it back to the frontend as JSON.

### Why choose a domain-specific chatbot?
Because evaluation requires:
- **clear domain definition** (fantasy world-building)
- **reliable, on-topic responses**
- consistent memory inside a single generated world

