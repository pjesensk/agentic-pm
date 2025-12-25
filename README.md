# Agentic Project Manager

## Overview
This project provides an agentic application designed to assist Scrum Masters and Project Managers by automating the generation of reports and executive summaries. It integrates with Jira to fetch task information and publishes structured reports to Confluence, streamlining communication and project oversight.

## Features
*   **Jira Integration:** Connects to Jira to retrieve issue data, including stories and tasks.
*   **Confluence Reporting:** Generates and updates pages in Confluence with executive summaries and detailed reports based on Jira data.
*   **Issue Management:** Capabilities to create, update, link, and search Jira issues.
*   **Automated Summaries:** Transforms raw Jira data into digestible reports for various stakeholders.

## Setup and Installation

### Prerequisites
*   Python 3.8+
*   `pip` (Python package installer)

### Installation Steps
1.  **Clone the repository:**
    ```bash
    git clone https://github.com/your-repo/agentic-pm.git
    cd agentic-pm
    ```

2.  **Create and activate a virtual environment:**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

This application requires API credentials for Jira and Confluence. It is recommended to set these as environment variables.

*   **JIRA_HOSTNAME**: The base URL of your Jira instance (e.g., `https://your-jira.atlassian.net`)
*   **JIRA_AUTH_TOKEN**: A personal access token or API token for Jira. For API tokens, use `user:token` format for basic auth, or just the token for bearer auth.
*   **CONFLUENCE_HOSTNAME**: The base URL of your Confluence instance (e.g., `https://your-confluence.atlassian.net`)
*   **CONFLUENCE_AUTH_TOKEN**: A personal access token for Confluence.

Example of setting environment variables (for Linux/macOS):
```bash
export JIRA_HOSTNAME="https://your-jira.atlassian.net"
export JIRA_AUTH_TOKEN="your_jira_api_token"
export CONFLUENCE_HOSTNAME="https://your-confluence.atlassian.net"
export CONFLUENCE_AUTH_TOKEN="your_confluence_api_token"
```

## Usage

To run the application, execute the `main.py` script. Ensure your environment variables are set up correctly.

```bash
python main.py
```

The `main.py` script will orchestrate the fetching of data from Jira, processing it, and generating reports in Confluence.

## Database Schema

The project uses a database to store context information. The following DDL can be used to create the necessary table:

```sql
CREATE TABLE devops.crew_pm_exec (
  id SERIAL PRIMARY KEY,
  confluence_id INTEGER,
  jira_epic VARCHAR (25),
  title VARCHAR(255)
);
```
```sql
CREATE TABLE devops.crew_pm_cache (
  id SERIAL PRIMARY KEY,
  key VARCHAR(25),
  context JSONB
);
```

## Project Structure

*   `main.py`: The main entry point of the application.
*   `connectors/`: Contains API client classes for integrating with external services like Jira and Confluence.
    *   `jirapi.py`: Handles communication with the Jira API.
    *   `confluenceapi.py`: Handles communication with the Confluence API.
*   `templates/`: Stores Jinja2 templates for generating reports (e.g., `exec_summary.html.j2`).
*   `requirements.txt`: Lists all Python dependencies.