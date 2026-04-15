"""
Scrum Agent - Analyzes Jira tickets and stores context for executive summaries.
Uses AI agents to extract structured information from Jira tickets.
"""
import json
from typing import List, Dict, Any, Set
from strands.types.exceptions import StructuredOutputException, MaxTokensReachedException
from tools.strands_limit_hook import LimitToolCounts
from model.jira_context import JiraContext
from common_utils import (
    ConfigManager,
    DatabaseManager,
    APIClientManager,
    AgentFactory,
    setup_logging,
    OLLAMA_MAX_TOKENS
)

# Constants
MAX_DESCRIPTION_LENGTH = 2048
MAX_TOOL_COUNTS = {"sleep": 3}

# Setup logging
logger = setup_logging(__name__)

# Initialize managers
config_manager = ConfigManager()
db_manager = DatabaseManager(config_manager)
api_manager = APIClientManager(config_manager)


def load_items() -> List[Dict[str, Any]]:
    """
    Load project items from database.
    
    Returns:
        List of project items with their configuration.
    """
    logger.info("Loading project items from database")
    query = """
        SELECT id, confluence_id, jira_epic, title, summary_jql, goal, 
               deliverables, success_criteria, due_date, sprint_jql 
        FROM devops.crew_pm_exec;
    """
    rows = db_manager.execute_query(query)
    
    items = []
    for row in rows:
        items.append({
            "id": row[0],
            "confluence": row[1],
            "jira": row[2],
            "title": row[3],
            "jql": row[4],
            "goal": row[5],
            "deliverables": row[6],
            "success_criteria": row[7],
            "due_date": row[8],
            "sprint_jql": row[9]
        })
    
    logger.info(f"Loaded {len(items)} project items")
    return items


def get_cached_keys() -> Set[str]:
    """
    Get list of already cached Jira ticket keys.
    
    Returns:
        Set of cached ticket keys.
    """
    logger.info("Retrieving cached ticket keys")
    query = "SELECT key FROM devops.crew_pm_cache"
    rows = db_manager.execute_query(query)
    
    keys = {row[0] for row in rows}
    logger.info(f"Found {len(keys)} cached tickets")
    return keys


def store_context(key: str, confluence_id: str, content: str, metadata: str) -> None:
    """
    Store ticket context in database cache.
    
    Args:
        key: Jira ticket key
        confluence_id: Confluence page ID
        content: Analyzed context content
        metadata: Ticket metadata as JSON string
    """
    logger.info(f"Storing context for ticket {key}")
    query = """
        INSERT INTO devops.crew_pm_cache (key, confluence_id, context, metadata) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (key, confluence_id) 
        DO UPDATE SET context=%s, metadata=%s
    """
    db_manager.execute_query(
        query,
        (key, confluence_id, content, metadata, content, metadata),
        fetch=False
    )
    logger.info(f"Successfully stored context for ticket {key}")


def trim_ticket_description(ticket: Dict[str, Any], max_length: int = MAX_DESCRIPTION_LENGTH) -> None:
    """
    Trim ticket description to fit context window.
    
    Args:
        ticket: Jira ticket dictionary
        max_length: Maximum description length
    """
    description = ticket.get('fields', {}).get('description')
    if description and len(description) > max_length:
        ticket['fields']['description'] = description[:max_length]
        logger.debug(f"Trimmed description for {ticket['key']} to {max_length} characters")


def extract_ticket_metadata(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from Jira ticket.
    
    Args:
        ticket: Jira ticket dictionary
        
    Returns:
        Dictionary with ticket metadata
    """
    fields = ticket.get('fields', {})
    
    # Safely extract priority
    priority = "Normal"
    if 'priority' in fields and fields['priority'] is not None:
        priority = fields['priority']['name']
    
    # Safely extract assignee
    assignee = "Unassigned"
    if 'assignee' in fields and fields['assignee'] is not None:
        assignee = fields['assignee']['emailAddress']
    
    return {
        "key": ticket['key'],
        "created": fields.get('created'),
        "title": fields.get('summary'),
        "priority": priority,
        "status": fields.get('status', {}).get('name'),
        "description": fields.get('description'),
        "assignee": assignee,
        "labels": fields.get('labels', [])
    }

def analyze_ticket_with_agent(ticket: Dict[str, Any], project_title: str) -> JiraContext:
    """
    Analyze a Jira ticket using AI agent.
    
    Args:
        ticket: Jira ticket dictionary
        project_title: Project title for context
        
    Returns:
        JiraContext with analyzed information
        
    Raises:
        StructuredOutputException: If agent fails to produce structured output
        MaxTokensReachedException: If token limit is reached
    """
    logger.info(f"Analyzing ticket {ticket['key']} with AI agent")
    
    # Create LLM and agent
    llm = AgentFactory.create_ollama_model(max_tokens=OLLAMA_MAX_TOKENS)
    limit_hook = LimitToolCounts(max_tool_counts=MAX_TOOL_COUNTS)
    agent = AgentFactory.create_scrum_agent(model=llm, hooks=[limit_hook])
    
    # Prepare prompt
    prompt = f"""
    Analyze the following Jira ticket in the context of the project '{project_title}'. Your response must be in English.
    You must provide a value for ALL fields. If information is not in the ticket, infer it from the context.
    For each field, provide a concise answer (max 255 characters).
    Provide the result json which is compliant with this pydantic schema: 
    key: str = Field(description="Jira issue key")
    summary: str = Field(description="Concise jira issue summary")
    achievements: str = Field(description="What was achieved with this ticket in relation to project goals.")
    deliverable: str = Field(description="The concrete deliverable from this ticket.")
    focus: str = Field(description="The main focus area of this ticket (e.g., bug fix, new feature, backend, frontend, etc.).")
    risks: str = Field(description="Any potential risks that could arise from or are highlighted by this ticket.")
    DO NOT include anything else to your answer apart from valid json for given pydantic schema.
    Given the following jira issue {ticket} provide only the result json.
    """
    
    # Execute agent
    response = agent(
        prompt,
        structured_output_model=JiraContext,
        hooks=[limit_hook]
    )
    
    logger.info(f"Successfully analyzed ticket {ticket['key']}")
    return response.structured_output

def process_ticket(
    ticket: Dict[str, Any],
    item: Dict[str, Any],
    cached_keys: Set[str]
) -> bool:
    """
    Process a single Jira ticket if not already cached.
    
    Args:
        ticket: Jira ticket dictionary
        item: Project item configuration
        cached_keys: Set of already cached ticket keys
        
    Returns:
        True if ticket was processed, False if skipped
    """
    ticket_key = ticket['key']
    logger.debug(f"Found jira issue {ticket_key}")
    
    if ticket_key in cached_keys:
        logger.debug(f"Skipping {ticket_key} - already cached")
        return False
    
    logger.info(f"Processing jira issue {ticket_key}")
    
    try:
        # Trim description to fit context window
        trim_ticket_description(ticket)
        
        # Analyze ticket with agent
        context = analyze_ticket_with_agent(ticket, item['title'])
        
        # Extract metadata
        metadata = extract_ticket_metadata(ticket)
        
        # Store results
        store_context(
            ticket_key,
            item['confluence'],
            context.model_dump_json(indent=2),
            json.dumps(metadata)
        )
        
        logger.info(f"Successfully processed {ticket_key}")
        return True
        
    except StructuredOutputException as e:
        logger.error(f"Structured output failed for {ticket_key}: {e}")
        return False
    except MaxTokensReachedException as e:
        logger.error(f"Max tokens reached for {ticket_key}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error processing {ticket_key}: {e}")
        return False

def process_project_item(item: Dict[str, Any]) -> Dict[str, int]:
    """
    Process all tickets for a project item.
    
    Args:
        item: Project item configuration
        
    Returns:
        Dictionary with processing statistics
    """
    logger.info(f"Processing project: {item['title']}")
    
    # Get Jira API client
    jira_api = api_manager.get_jira_api()
    
    # Search for tickets
    logger.info(f"Searching tickets with JQL: {item['sprint_jql']}")
    sprint_tickets = jira_api.search_issues(jql=item['sprint_jql'])
    logger.info(f"Searching tickets with JQL: {item['jql']}")
    summary_tickets = jira_api.search_issues(jql=item['jql'])
    
    tickets = sprint_tickets + summary_tickets
    logger.info(f"Found {len(tickets)} total tickets for project {item['title']}")
    
    # Get cached keys
    cached_keys = get_cached_keys()
    
    # Process each ticket
    processed = 0
    skipped = 0
    failed = 0
    
    for ticket in tickets:
        result = process_ticket(ticket, item, cached_keys)
        if result:
            processed += 1
        elif ticket['key'] in cached_keys:
            skipped += 1
        else:
            failed += 1
    
    stats = {
        'total': len(tickets),
        'processed': processed,
        'skipped': skipped,
        'failed': failed
    }
    
    logger.info(f"Project {item['title']} complete: {stats}")
    return stats


if __name__ == "__main__":
    logger.info("Starting scrum agent flow")
    items = load_items()
    overall_stats = {
        'projects': 0,
        'total_tickets': 0,
        'total_processed': 0,
        'total_skipped': 0,
        'total_failed': 0
    }
    if not items:
        logger.warning("No project items found")
    
    # Process each project item
    all_stats = []
    for item in items:
        stats = process_project_item(item)
        all_stats.append(stats)
    
    # Calculate overall statistics
    overall_stats = {
        'projects': len(items),
        'total_tickets': sum(s['total'] for s in all_stats),
        'total_processed': sum(s['processed'] for s in all_stats),
        'total_skipped': sum(s['skipped'] for s in all_stats),
        'total_failed': sum(s['failed'] for s in all_stats)
    }
    
    logger.info(f"Scrum agent flow complete: {overall_stats}")
