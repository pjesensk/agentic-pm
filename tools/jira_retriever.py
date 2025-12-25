import os
import logging
import hvac
import psycopg2
from strands import tool
from dotenv import load_dotenv
from datetime import datetime, timedelta
from connectors.jirapi import JiraApi

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())
load_dotenv()

client = hvac.Client(url=os.getenv('VAULT_URL'))
client.auth.approle.login(
    role_id=os.getenv('VAULT_ROLE_ID'),
    secret_id=os.getenv('VAULT_SECRET_ID'),
)

db_secret = client.secrets.kv.read_secret_version(path='secret/cmdb')

DB_NAME = db_secret['data']['data']['psql_db']
DB_USER = db_secret['data']['data']['psql_user']
DB_PASSWORD = db_secret['data']['data']['psql_pw']
DB_HOST = db_secret['data']['data']['psql_host']
DB_PORT = db_secret['data']['data']['psql_port']

jira_secret = client.secrets.kv.read_secret_version(path="secret/jira")

jira_api = JiraApi(
    hostname=jira_secret["data"]["data"]["url"],
    auth_token=jira_secret["data"]["data"]["token"],
)

@tool
def search_issues (jql):
    log.info (f"search_issues was called with following query {jql}")
    results = []
    tickets = jira_api.search_issues(jql=jql)
    for ticket in tickets:
        results.append (
            {
               "created": ticket['created'],
                "key": ticket['key'],
                "title": ticket['fields']['summary'],
                "priority": ticket['fields']['priority']['name'],
                "status": ticket['fields']['status']['name'],
                "description": ticket.get('description'), # Use .get for potentially missing fields
                "assignee": ticket['fields']['assignee']["emailAddress"] if ticket['fields']['assignee'] else "Unassigned" ,
                "labels": ticket['fields']['labels']
            }
        )
    return results

@tool
def create_jira_issue(project_key: str, summary: str, description: str, issue_type: str = "Story"):
    """
    Creates a new Jira issue.

    Args:
        project_key: The key of the project (e.g., "PROJ").
        summary: The summary (title) of the issue.
        description: The detailed description of the issue.
        issue_type: The type of issue to create (e.g., "Story", "Bug", "Task"). Defaults to "Story".

    Returns:
        A dictionary containing the details of the created Jira issue.
    """
    log.info(f"create_jira_issue called with project_key='{project_key}', summary='{summary}', issue_type='{issue_type}'")
    # Format the description into the structure expected by Jira API
    formatted_description = {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": description}],
            }
        ],
    }
    try:
        result = jira_api.create_issue(
            project_key=project_key,
            summary=summary,
            description=formatted_description, # Pass the formatted description
            issue_type=issue_type,
        )
        log.info(f"Jira issue created successfully: {result.get('key')}")
        return result
    except Exception as e:
        log.error(f"Failed to create Jira issue: {e}")
        raise e

@tool
def update_jira_issue(issue_key: str, fields: dict):
    """
    Updates an existing Jira issue.

    Args:
        issue_key: The key of the issue to update (e.g., "PROJ-123").
        fields: A dictionary of fields to update. Example:
                {"summary": "New summary", "description": "New description content"}
                or for custom fields:
                {"customfield_10000": "New value"}

    Returns:
        True if the update was successful, False otherwise.
    """
    log.info(f"update_jira_issue called for issue '{issue_key}' with fields: {fields}")
    try:
        success = jira_api.update_issue(issue_key=issue_key, fields=fields)
        log.info(f"Jira issue '{issue_key}' updated successfully: {success}")
        return success
    except Exception as e:
        log.error(f"Failed to update Jira issue '{issue_key}': {e}")
        raise e

@tool
def add_jira_comment(issue_key: str, comment_body: str):
    """
    Adds a comment to a Jira issue.

    Args:
        issue_key: The key of the issue to add a comment to (e.g., "PROJ-123").
        comment_body: The content of the comment.

    Returns:
        A dictionary containing the details of the added comment.
    """
    log.info(f"add_jira_comment called for issue '{issue_key}'")
    try:
        # The JiraApi.add_comment method handles formatting the comment_body string.
        result = jira_api.add_comment(issue_key=issue_key, comment_body=comment_body)
        log.info(f"Comment added successfully to Jira issue '{issue_key}'. Comment ID: {result.get('id')}")
        return result
    except Exception as e:
        log.error(f"Failed to add comment to Jira issue '{issue_key}': {e}")
        raise e

@tool
def resolve_jira_issue(issue_key: str, resolution_name: str = "Fixed"):
    """
    Resolves a Jira issue.

    Args:
        issue_key: The key of the issue to resolve (e.g., "PROJ-123").
        resolution_name: The name of the resolution to apply (e.g., "Fixed", "Done", "Won't Fix"). Defaults to "Fixed".

    Returns:
        True if the issue was resolved successfully, False otherwise.
    """
    log.info(f"resolve_jira_issue called for issue '{issue_key}' with resolution '{resolution_name}'")
    try:
        success = jira_api.resolve_issue(issue_key=issue_key, resolution_name=resolution_name)
        log.info(f"Jira issue '{issue_key}' resolved successfully: {success}")
        return success
    except Exception as e:
        log.error(f"Failed to resolve Jira issue '{issue_key}': {e}")
        raise e
