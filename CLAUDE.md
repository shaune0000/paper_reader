# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Paper Reader is an automated system that fetches daily papers from Hugging Face, downloads PDFs, generates AI-powered summaries in Traditional Chinese (Taiwan usage), and posts them to Zulip for team discussion. It also provides a Q&A bot that can answer questions about papers using RAG (Retrieval-Augmented Generation) with FAISS vector embeddings.

## Key Commands

### Setup
```bash
pip install -r requirements.txt
```

### Running the System

**Daily paper monitoring (continuous mode)**:
```bash
python read_daily_papers.py --zulip True
```

**Read papers from a JSON file**:
```bash
python read_paper.py --json_file <path_to_json> --zulip True
```

**Disable Zulip posting**:
```bash
python read_daily_papers.py --zulip False
python read_paper.py --json_file <path> --zulip False
```

## Architecture

### Core Workflow
1. **Fetching** (`grab_huggingface.py`): Scrapes Hugging Face daily papers page, extracts paper metadata, downloads PDFs
2. **Analysis** (`gpt4o_technical_analyst.py`): Uses GPT-4o-mini with LangChain to generate structured summaries with specific Chinese academic tone
3. **Storage** (`database.py`): SQLite database tracks processed papers to avoid duplicates
4. **Publishing** (`zulip_handler.py`): Posts summaries to Zulip and handles interactive Q&A via bot mentions

### Main Entry Points
- `read_daily_papers.py`: Continuous monitoring mode that checks Hugging Face periodically with random sleep intervals (30-60 minutes)
- `read_paper.py`: One-time processing of papers from a JSON file

### Data Flow
```
Hugging Face → HTML scraping → JSON + PDF downloads →
LangChain PDF processing → GPT-4o-mini summarization →
Markdown formatting → Zulip posting + SQLite storage →
FAISS embeddings (for Q&A)
```

### Key Components

**grab_huggingface.py**:
- Fetches HTML from huggingface.co/papers
- Uses content hashing to detect changes
- Downloads PDFs with retry logic (up to 10 retries)
- Extracts paper ID, title, authors, upvotes, comments

**gpt4o_technical_analyst.py**:
- `load_paper()`: Uses PyPDFLoader + CharacterTextSplitter (1000 char chunks, 200 overlap)
- `sumarize_paper()`: Custom prompt for Taiwan academic style with structured output (標題, 短標題, 主題, 摘要, 分析, 結論)
- `get_paper_embedding_db()`: Creates/loads FAISS vector stores in `./embedding_db/`
- `answer_question()`: RAG-based Q&A using similarity search

**database.py**:
- Context manager pattern for SQLite connections
- Schema: id, title, summary (JSON), link, pdf_link, local_pdf, zulip_topic, timestamps
- `get_paper_by_zulip_topic()`: Links Zulip threads to papers

**zulip_handler.py**:
- Background thread listens for bot mentions (`@_**PaperReaderBot` or `@**PaperReaderBot**`)
- Extracts questions from quote blocks
- Matches Zulip topic to paper, retrieves embedding DB, answers via RAG
- Posts quoted replies with @mentions

### Configuration

**Environment variables** (in `.env`):
- `OPENAI_API_KEY`: Required for GPT-4o-mini
- `OPENAI_ORG_ID`: OpenAI organization ID
- `.zuliprc`: Zulip bot credentials (see zulip docs)

### Directory Structure
- `huggingface_dailypaper/`: Cached HTML and JSON from Hugging Face (dated with content hash)
- `paper_pdf/`: Downloaded PDFs (named by arXiv ID like `2407.19672.pdf`)
- `embedding_db/`: FAISS vector stores per paper (`{paper_id}.db/`)
- `md/`: Generated markdown summaries (named by paper ID)
- `log/`: Application logs (`daily_papers.log` with daily rotation, `error.log` for failures)
- `papers.db`: SQLite database

### Error Handling
- PDF download failures are logged to `log/error.log` with timestamps
- Failed PDFs are deleted from disk to allow retry (see read_paper.py:198-204)
- Papers that fail processing are skipped but not added to database

### Important Implementation Details

**Duplicate prevention**: Papers are only processed if `get_paper(conn, paper_id)` returns None

**Content hashing**: Hugging Face HTML is hashed (SHA256) to detect page updates even within same day

**LangChain prompt engineering**: The summarization prompt in `gpt4o_technical_analyst.py:112-141` defines the specific academic tone and structure. Key requirements:
- Taiwan usage (台灣用語)
- Academic but slightly witty/sarcastic tone
- Structured output with 6 fields
- Focus on purpose, methods, contributions, contradictions, future directions

**Zulip bot interaction**: Bot only responds to messages that quote it. Uses regex to extract new question from quoted content (zulip_handler.py:59-67)

**Random sleep intervals**: To avoid rate limiting, `read_daily_papers.py` sleeps 30-60 minutes between checks

## Notes for Development

- All user-facing text is in Traditional Chinese with Taiwan terminology
- The summarization prompt emphasizes critical analysis (purpose, methods, improvements, contradictions, future work)
- PDF downloads use ArXiv IDs extracted from Hugging Face links
- FAISS embeddings enable semantic search for Q&A without reprocessing papers
- The system is designed to run continuously with graceful handling of failures
