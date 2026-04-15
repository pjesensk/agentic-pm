# Agentic Project Manager

## Overview
This project provides an agentic application designed to assist Scrum Masters and Project Managers by automating the generation of reports and executive summaries. It integrates with Jira to fetch task information, uses AI agents to analyze tickets, and publishes structured reports to Confluence, streamlining communication and project oversight.

## Features
*   **Jira Integration:** Connects to Jira to retrieve issue data, including stories and tasks using JQL queries.
*   **AI-Powered Analysis:** Uses AI agents (Ollama-based) to analyze tickets and extract structured information including achievements, risks, focus areas, and deliverables.
*   **Confluence Reporting:** Generates and updates pages in Confluence with executive summaries and detailed reports based on analyzed Jira data.
*   **Automated Ticket Summaries:** Automatically posts AI-generated summaries as comments to specified Jira tickets.
*   **Context Caching:** Stores analyzed ticket context in a database to avoid redundant processing.
*   **Timeline Generation:** Creates monthly timelines showing project progress and achievements.

## Setup and Installation

### Prerequisites
*   Python 3.8+
*   `pip` (Python package installer)
*   PostgreSQL database
*   Ollama with appropriate models installed
*   Jira API credentials
*   Confluence API credentials

### Installation Steps
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/agentic-pm.git
    cd agentic-pm
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

This application requires API credentials for Jira and Confluence, as well as database connection details. Configuration is managed through the [`ConfigManager`](common_utils.py) class. Set the following environment variables or configure them in your configuration file:

*   Jira API credentials (URL, username, API token)
*   Confluence API credentials (URL, username, API token)
*   PostgreSQL database connection details
*   Ollama configuration (model name, API endpoint)

## Database Schema

The project uses PostgreSQL to store project configurations and ticket analysis cache. Create the following tables:

```sql
-- Project configuration table
CREATE TABLE devops.crew_pm_exec (
  id SERIAL PRIMARY KEY,
  confluence_id INTEGER,
  jira_epic VARCHAR(25),
  title VARCHAR(255),
  summary_jql TEXT,
  sprint_jql TEXT,
  goal TEXT,
  deliverables TEXT,
  success_criteria TEXT,
  due_date DATE,
  confluence_architecture TEXT,
  status VARCHAR(50),
  status_desc TEXT,
  prerequisities JSONB
);

-- Ticket analysis cache table
CREATE TABLE devops.crew_pm_cache (
  id SERIAL PRIMARY KEY,
  key VARCHAR(25),
  confluence_id INTEGER,
  context JSONB,
  metadata JSONB,
  UNIQUE(key, confluence_id)
);

-- Ticket comment configuration table
CREATE TABLE devops.crew_pm_comment (
  id SERIAL PRIMARY KEY,
  target_ticket VARCHAR(25),
  source_jql TEXT,
  context TEXT
);
```

## Usage

The application consists of three main flow scripts that can be run independently:

### 1. Ticket Ingestion and Analysis

[`ingest_tickets_with_scrum_agent.py`](ingest_tickets_with_scrum_agent.py) - Fetches Jira tickets and analyzes them using AI agents.

**Purpose:** 
- Retrieves tickets from Jira using configured JQL queries
- Analyzes each ticket using an AI agent to extract structured information (achievements, deliverables, focus areas, risks)
- Stores the analyzed context in the database cache for later use
- Skips tickets that have already been analyzed

**Run:**
```bash
python ingest_tickets_with_scrum_agent.py
```

**What it does:**
1. Loads project configurations from `devops.crew_pm_exec` table
2. For each project, fetches tickets using both `sprint_jql` and `summary_jql`
3. Checks which tickets are already cached
4. Analyzes new tickets using the scrum agent
5. Stores structured context (achievements, deliverables, focus, risks) in `devops.crew_pm_cache`

### 2. Executive Summary Generation

[`exec_summary_agent.py`](exec_summary_agent.py) - Generates comprehensive executive summaries and updates Confluence.

**Purpose:**
- Creates executive summaries from cached ticket analysis
- Generates timeline views showing monthly progress
- Summarizes achievements, focus areas, next steps, and risks
- Updates Confluence pages with formatted reports

**Run:**
```bash
python exec_summary_agent.py
```

**What it does:**
1. Loads project configurations from `devops.crew_pm_exec` table
2. Retrieves cached ticket contexts from `devops.crew_pm_cache`
3. Generates AI-powered summaries for:
   - Recent achievements (last 28 days of closed tickets)
   - Focus areas (what was worked on)
   - Next steps (upcoming work from open tickets)
   - Risks (potential issues identified)
4. Creates monthly timeline showing project evolution
5. Renders HTML report using Jinja2 template ([`exec_summary.html.j2`](templates/exec_summary.html.j2))
6. Updates Confluence page with the generated report

### 3. Automated Ticket Comments

[`ticket_updater_scrum_agent.py`](ticket_updater_scrum_agent.py) - Posts AI-generated summaries as comments to Jira tickets.

**Purpose:**
- Fetches tickets based on JQL queries from database configuration
- Generates comprehensive summaries using AI agents
- Posts formatted summaries as comments to specified target tickets
- Handles large ticket sets with recursive summarization

**Run:**
```bash
python ticket_updater_scrum_agent.py
```

**What it does:**
1. Loads comment configurations from `devops.crew_pm_comment` table
2. For each configuration:
   - Fetches tickets using the `source_jql` query
   - Analyzes and summarizes all tickets using AI agent
   - Generates structured summary including:
     - Overall summary
     - Key achievements
     - Main focus areas
     - Status breakdown
     - Potential risks
   - Posts formatted comment to the `target_ticket`
3. Uses recursive summarization for large ticket sets that exceed context window

## Workflow

A typical workflow involves running the scripts in sequence:

```bash
# Step 1: Ingest and analyze new tickets
python ingest_tickets_with_scrum_agent.py

# Step 2: Generate executive summaries and update Confluence
python exec_summary_agent.py

# Step 3: Post ticket summaries as comments (optional)
python ticket_updater_scrum_agent.py
```

## Project Structure

*   [`exec_summary_agent.py`](exec_summary_agent.py): Generates executive summaries from cached ticket analysis and updates Confluence pages.
*   [`ingest_tickets_with_scrum_agent.py`](ingest_tickets_with_scrum_agent.py): Fetches Jira tickets and analyzes them using AI agents, storing results in cache.
*   [`ticket_updater_scrum_agent.py`](ticket_updater_scrum_agent.py): Fetches tickets via JQL, summarizes them, and posts comments to target tickets.
*   [`common_utils.py`](common_utils.py): Shared utilities including ConfigManager, DatabaseManager, APIClientManager, and AgentFactory.
*   `connectors/`: Contains API client classes for integrating with external services.
    *   `jirapi.py`: Handles communication with the Jira API.
    *   `confluenceapi.py`: Handles communication with the Confluence API.
*   `model/`: Pydantic models for structured data.
    *   `exec_summary.py`: Executive summary data model.
    *   `jira_context.py`: Jira ticket context model.
    *   Other model files for timeline, prerequisites, etc.
*   `templates/`: Stores Jinja2 templates for generating reports.
    *   `exec_summary.html.j2`: Template for executive summary HTML rendering.
*   `tools/`: Custom tools and utilities.
    *   `strands_limit_hook.py`: Tool usage limiting for AI agents.
*   `requirements.txt`: Lists all Python dependencies.

## AI Agent Architecture

The application uses two types of AI agents:

1. **Scrum Agent** - Specialized in analyzing Jira tickets and extracting structured information about achievements, deliverables, focus areas, and risks.

2. **PM Agent** - Focused on creating summaries and generating executive-level insights from ticket data.

Both agents are created using the [`AgentFactory`](common_utils.py) and leverage Ollama models for local AI processing.

## Key Features

### Context Caching
The system caches analyzed ticket contexts to avoid redundant AI processing. Once a ticket is analyzed, its structured context is stored in the database and reused for executive summary generation.

### Recursive Summarization
For large datasets that exceed the AI model's context window, the system uses recursive summarization to break down the data into manageable chunks, summarize each chunk, and then combine the summaries.

### Timeline Generation
Automatically creates monthly timeline views showing project progress, with AI-generated descriptions of activities and achievements for each month.

### Structured Output
All AI agent responses use structured output (Pydantic models) to ensure consistent, parseable results that can be reliably stored and processed.

## Logging

All scripts use comprehensive logging to track execution progress, errors, and statistics. Logs include:
- Ticket processing status
- AI agent interactions
- Database operations
- API calls to Jira and Confluence
- Summary statistics

## Error Handling

The application includes robust error handling for:
- AI agent failures (StructuredOutputException, MaxTokensReachedException)
- Database connection issues
- API rate limits and failures
- Missing or malformed data

Failed operations are logged with detailed error messages, and processing continues for remaining items.