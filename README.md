# 🧠 Agentic AI CRM — Intelligent Multi-Agent Backend

> 🚀 A fully agentic, MongoDB-powered backend for an **AI-driven Sales CRM**, featuring automated enrichment, lead scoring, contact discovery, and personalized email campaigns with Gemini-based replies.

---

## 🌟 Overview

The **Agentic AI CRM Backend** is the powerhouse behind a modern sales automation system.  
It uses multiple autonomous agents that collaborate to:

- Ingest customer requirements and target companies  
- Enrich and score leads using intelligent data extraction  
- Find key employees and verify contacts automatically  
- Send personalized campaigns and respond using Gemini AI  

Everything is **multi-user, database-backed, and fully API-accessible** — built for seamless integration with a future dashboard frontend.

---

## 🧩 System Architecture
```
                ┌──────────────────────────────┐
                │         FastAPI API          │
                │   (Dashboards + User Input)  │
                └──────────────┬───────────────┘
                               │
                ┌──────────────┴──────────────┐
                │        Agent Orchestrator   │
                │ (backend/main.py CLI Runner)│
                └──────────────┬──────────────┘
                               │
        ┌──────────────────────┼─────────────────────────────────────┐    
        │                      │                                     │
        ▼                      ▼                                     ▼
  enrichment_agent.py     scoring_agent.py                    email_sender.py
  employee_finder.py      contact_finder.py                   (Gemini + Gmail)
        │                      │                                     │
        └──────────► MongoDB (user_inputs / user_outputs) ◄──────────┘
                               │
                     ┌─────────┴─────────┐
                     │   Analytics API   │
                     │ (Backend REST)    │
                     └───────────────────┘
```

---

## ⚙️ Features

✅ **Multi-Agent Architecture**  
- 5 independent AI-driven agents run asynchronously.  
- Each has its own log, input/output, and MongoDB record.

✅ **Multi-User Sandbox**  
- Each user has isolated folders under `backend/users/<user_id>/`  
- Supports parallel agent runs for multiple clients.

✅ **MongoDB Integration**  
- Unified schema: `user_inputs` & `user_outputs`  
- Backward-compatible with legacy agent collections.

✅ **FastAPI REST Layer**  
- Upload user inputs, trigger agents, and fetch outputs/logs.  
- Analytics endpoints for dashboards and KPIs.

✅ **Gmail Campaigns + Gemini Replies**  
- Sends templated emails via Gmail API.  
- Handles auto-replies intelligently using **Gemini 2.5 Flash**.

✅ **Dynamic Token Handling**  
- Automatic Gmail token refresh via `generate_token.py`.

✅ **Complete Logging & Traceability**  
- Per-user agent logs in `/users/<user_id>/logs/`.  
- MongoDB timestamps for all operations.

---

## 🏗️ Folder Structure
```
backend/
│
├── .env
├── credentials.json
├── token.json
│
├── main.py                 # CLI orchestrator for all agents
├── test.py                 # MongoDB connection test
│
├── api/
│   ├── main.py             # FastAPI entrypoint
│   └── routes/
│       ├── users.py
│       ├── agents.py
│       ├── campaigns.py
│       ├── analytics.py
│       └── data.py
│
├── agents/
│   ├── enrichment_agent.py
│   ├── scoring_agent.py
│   ├── employee_finder.py
│   ├── contact_finder.py
│   └── email_sender.py
│
├── db/
│   └── mongo.py            # MongoDB unified handler
│
├── utils/
│   ├── generate_token.py
│   ├── logger.py
│   └── helpers.py
│
└── users/
    ├── user_demo/
    │   ├── inputs/
    │   ├── outputs/
    │   ├── logs/
    │   └── templates/
    └── abc/
```

---

## 🗄️ MongoDB Schema

### `user_inputs`
Stores user-provided inputs (uploaded via API or local CLI)
```json
{
  "user_id": "user_demo",
  "type": "companies",
  "data": {...},
  "timestamp": "2025-10-22T01:31:46Z"
}
```

### `user_outputs`
Stores agent-generated outputs (enriched data, leads, campaigns)
```json
{
  "user_id": "user_demo",
  "agent": "email_sender",
  "output_type": "campaign_summary",
  "data": {...},
  "timestamp": "2025-10-22T02:06:35Z"
}
```

---

## 🧰 Tech Stack

| Layer | Technology |
|-------|-------------|
| **API Framework** | FastAPI |
| **Database** | MongoDB Atlas (pymongo) |
| **AI Model** | Google Gemini 2.5 Flash |
| **Email System** | Gmail API (OAuth + REST) |
| **Authentication** | OAuth 2.0 via google-auth-oauthlib |
| **Environment Handling** | python-dotenv |
| **Logging** | Python logging + rotating file handlers |
| **Task Orchestration** | CLI Runner + Agent Folder Architecture |
| **Frontend (Upcoming)** | React + Tailwind (to consume FastAPI routes) |

---

## 🚀 Setup & Usage

### 1️⃣ Clone and Install Dependencies
```bash
git clone https://github.com/<your-username>/agentic-crm.git
cd "Agentic CRM"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2️⃣ Configure Environment
Create `backend/.env` with:
```
MONGO_URI=mongodb+srv://<username>:<password>@cluster.mongodb.net/?retryWrites=true&w=majority
GEMINI_API_KEY=<your_gemini_api_key>
```

Place your Gmail credentials:
```
backend/credentials.json
```

Generate Gmail token:
```bash
cd backend/utils
python generate_token.py
```

---

### 3️⃣ Run Agents from CLI
Example: Run the orchestrator
```bash
cd backend
python -m backend.main
```

Or run a single agent manually:
```bash
python -m backend.agents.email_sender user_demo
```

---

### 4️⃣ Run FastAPI Server
```bash
uvicorn backend.api.main:app --reload
```
API runs at → [http://127.0.0.1:8000](http://127.0.0.1:8000)

---

## 🧩 Example Endpoints

| Method | Endpoint | Description |
|---------|-----------|-------------|
| `POST` | `/api/{user_id}/upload_input` | Upload `companies.json` or `customer_requirements.json` |
| `GET` | `/api/{user_id}/outputs` | List generated output files |
| `GET` | `/api/analytics/overview/{user_id}` | Fetch agent activity & lead metrics |
| `GET` | `/api/analytics/recent/{user_id}` | Get recent campaign and scoring events |

---

## 🧠 Agents Summary

| Agent | Purpose | Output Type |
|--------|----------|-------------|
| `enrichment_agent` | Enrich company data from the web | `enriched_companies` |
| `scoring_agent` | Assign lead potential scores | `lead_scores` |
| `employee_finder` | Identify key employees | `employee_finder` |
| `contact_finder` | Find and verify contacts/emails | `contact_finder` |
| `email_sender` | Send campaigns + Gemini replies | `campaign_summary` |

---

## 🧪 Testing Mongo Connection
```bash
python backend/test.py
```

Expected output:
```
✅ Connected successfully!
Collections: ['user_inputs', 'user_outputs']
```

---

## 🛡️ Security Notes

- `.venv`, `.env`, and credentials are ignored in `.gitignore`  
- Sensitive files (`credentials.json`, `token.json`) **must not be committed**  
- Multi-user design prevents data overlap across users  

---

## 📊 Future Roadmap

- 🧩 **Frontend Dashboard** (React + Recharts)  
- 🧠 **AI Enrichment Pipeline Optimization**  
- 📬 **Smart Campaign Scheduling**  
- 🔐 **User Authentication via JWT**  
- ☁️ **Dockerized Deployment on Render / Railway**

---

## 👨‍💻 Author

**Arnav Joshi**  
B.Tech CSE, Thapar University  
AI/ML + Full-Stack Developer  
📧 [brodomyjob@gmail.com](mailto:brodomyjob@gmail.com)

---

## 🏁 License

**MIT License © 2025 Arnav Joshi**  
Use freely with attribution.
