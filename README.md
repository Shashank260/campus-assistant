# Campus Assistant 📚

Campus Assistant is an AI-powered personal study assistant for college students. It uses a hybrid intent-routing architecture, powered by Google AI Studio (Gemma 4) and LangGraph, to provide an intelligent, personalized, and private learning experience.

## Features

- **Personalized RAG (Retrieval-Augmented Generation)**: Upload PDFs and YouTube videos to create your own isolated knowledge base. The system uses local CPU-based embeddings (`BAAI/bge-small-en`) via ChromaDB, ensuring complete data privacy and zero embedding latency costs.
- **Visual Question Answering**: Upload images of diagrams, charts, or notes and ask questions. The system leverages Gemma 4's multimodal capabilities to understand visual context.
- **Short-Term Memory (STM)**: Natural, continuous conversations with an automatic sliding-window memory manager. Older messages are dynamically summarized in the background to prevent context window bloat while maintaining conversational flow.
- **Hybrid Intent Router**: Dynamically routes your queries to the most appropriate AI agent (`conversational`, `personal_rag`, or `introspect`) using a mix of rule-based triggers and LLM classification.
- **The Learning Coach (Introspection)**: Synthesizes a metacognitive review of your study habits, analyzing your uploaded documents and chat history to provide encouraging, data-backed academic advice.
- **Notion Integration**: Push AI responses, study summaries, and notes directly to your Notion workspace as neatly formatted subpages.

## System Architecture

Campus Assistant uses a localized multi-tenant architecture:
- **FastAPI Backend**: Handles all client requests, SQLite interactions, and asynchronous background tasks.
- **LangGraph Workflow**: Manages the state machine, intent routing, and node execution for each query.
- **SQLite**: Stores conversation histories, user settings, and STM summaries using WAL (Write-Ahead Logging) for high concurrency.
- **ChromaDB**: Each user has a completely isolated namespace for their vector embeddings, ensuring absolute privacy.

## Getting Started

### Prerequisites

- Python 3.10+
- Google AI Studio API Key (Gemma 4)
- (Optional) Notion Integration Token

### Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd campus-assistant
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Create a `.env` file in the root directory based on `.env.example`.

5. **Run the Backend Server:**
   ```bash
   uvicorn main:app --reload
   ```

6. **Run the Streamlit Demo App:**
   In a separate terminal, run:
   ```bash
   streamlit run demo.py
   ```
