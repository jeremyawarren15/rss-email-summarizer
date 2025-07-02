# RSS Email Summarizer

This project fetches your recent emails, summarizes the important ones using Ollama (a local LLM), and publishes the results as an RSS feed you can read in any RSS reader (e.g., FreshRSS).

## Features

- Fetches new emails since the last run (via IMAP)
- Intelligent HTML stripping and content length limiting for reliable LLM processing
- Summarizes important emails using Ollama with smart categorization
- Publishes daily digest RSS feeds with clean formatting
- Persistent data storage with SQLite
- Docker deployable with volume mounting for data persistence
- Health monitoring and status endpoints
- Email whitelist/blacklist support

## Components

- **Email Fetcher:** Connects to your email account, retrieves new emails, and strips HTML content
- **Summarizer:** Sends cleaned email content to Ollama and receives importance classifications and summaries
- **RSS Generator:** Creates and serves daily digest RSS feeds with HTML formatting
- **Persistence:** SQLite database for email summaries and UID tracking for incremental processing
- **Dockerization:** Production-ready container with health checks and volume mounting

## Setup

### Prerequisites

- Python 3.10+
- Ollama running locally or on a network-accessible server
- An email account with IMAP access enabled

### Docker Deployment (Recommended)

The easiest way to deploy is using Docker Compose:

1. **Clone the repository:**

   ```bash
   git clone <repository-url>
   cd rss-email-summarizer
   ```

2. **Edit the docker-compose.yml file:**
   Update the environment variables in `docker-compose.yml` with your email credentials:

   ```yaml
   environment:
     - IMAP_HOST=your.imap.server.com
     - IMAP_USER=your-email@example.com
     - IMAP_PASSWORD=your-password
     - USER_NAME=Your Name
   ```

3. **Start the services:**

   ```bash
   docker-compose up -d
   ```

4. **Pull the Ollama model (first time only):**

   ```bash
   docker-compose exec ollama ollama pull llama3
   ```

5. **Check status:**
   ```bash
   curl http://localhost:5000/status
   ```

#### Manual Docker Build

If you prefer to build manually:

1. **Build the Docker image:**

   ```bash
   docker build -t rss-email-summarizer .
   ```

2. **Run with docker-compose or manually:**
   ```bash
   docker run -d \
     --name rss-email-summarizer \
     -p 5000:5000 \
     -v ./data:/app/data \
     -e IMAP_HOST=your.imap.server.com \
     -e IMAP_USER=your-email@example.com \
     -e IMAP_PASSWORD=your-password \
     -e OLLAMA_API_URL=http://ollama:11434/api/generate \
     -e USER_NAME="Your Name" \
     rss-email-summarizer
   ```

### Configuration

Key environment variables:

1. Copy `.env.example` to `.env` and configure your settings:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env` with your actual values:

   ```
   IMAP_HOST=imap.example.com
   IMAP_PORT=993
   IMAP_USER=your@email.com
   IMAP_PASSWORD="your_password"

   OLLAMA_API_URL=http://localhost:11434/api/generate
   OLLAMA_MODEL=phi3:mini

   FLASK_HOST=0.0.0.0
   FLASK_PORT=5000

   USER_NAME=Your Name
   EMAIL_WHITELIST=friend@example.com,alerts@bank.com
   EMAIL_BLACKLIST=promo@shopping.com,news@ads.com
   ```

### Accessing the RSS Feed

Once running, your RSS feed will be available at:

```
http://localhost:5000/rss
```

### Monitoring

Check the application status at:

```
http://localhost:5000/status
```

This endpoint shows:

- IMAP connection status and email count
- Ollama API status with test response
- Database status and summary count

## Usage

- The service will process emails on startup and then daily at 6am.
- Point your RSS reader to `http://localhost:5000/rss` to view summaries.
- Only emails deemed "important" by the AI will appear in the feed.
- The feed shows daily digests with all important emails for each day.

## Development

For local development without Docker:

1. **Create a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application:**
   ```bash
   python app.py
   ```

## Troubleshooting

- **IMAP connection issues:** Verify your email provider supports IMAP and check credentials.
- **Ollama connection issues:** Ensure Ollama is running and accessible at the configured URL.
- **No important emails:** Check the `/status` endpoint and adjust the AI prompt if needed.
- **Docker networking:** Use `host.docker.internal` instead of `localhost` when connecting to services on the host machine.
