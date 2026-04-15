"""
Ticket Updater Scrum Agent - Fetches Jira tickets based on JQL from database configuration,
summarizes them using AI agent, and posts the summary as a comment to a specified ticket.
"""
import json
from datetime import datetime
from typing import List, Dict, Any
from strands.types.exceptions import StructuredOutputException, MaxTokensReachedException
from tools.strands_limit_hook import LimitToolCounts
from pydantic import BaseModel, Field
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
CHAR_SPLITTER = 3800  # max number of characters for context window

# Setup logging
logger = setup_logging(__name__)

# Initialize managers
config_manager = ConfigManager()
db_manager = DatabaseManager(config_manager)
api_manager = APIClientManager(config_manager)


class TicketSummary(BaseModel):
    """Structured output model for ticket summary."""
    total_tickets: int = Field(description="Total number of tickets analyzed")
    summary: str = Field(description="Comprehensive summary of all tickets")
    key_achievements: str = Field(description="Key achievements across all tickets")
    main_focus_areas: str = Field(description="Main focus areas identified")
    potential_risks: str = Field(description="Potential risks identified")
    status_breakdown: str = Field(description="Breakdown of ticket statuses")


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


def extract_ticket_info(ticket: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract relevant information from Jira ticket.
    
    Args:
        ticket: Jira ticket dictionary
        
    Returns:
        Dictionary with ticket information
    """
    fields = ticket.get('fields', {})
    
    # Safely extract priority
    priority = "Normal"
    if 'priority' in fields and fields['priority'] is not None:
        priority = fields['priority']['name']
    
    # Safely extract assignee
    assignee = "Unassigned"
    if 'assignee' in fields and fields['assignee'] is not None:
        assignee = fields['assignee'].get('displayName', fields['assignee'].get('emailAddress', 'Unassigned'))
    
    # Safely extract status
    status = "Unknown"
    if 'status' in fields and fields['status'] is not None:
        status = fields['status'].get('name', 'Unknown')
    
    return {
        "key": ticket['key'],
        "summary": fields.get('summary', 'No summary'),
        "priority": priority,
        "status": status,
        "description": fields.get('description', 'No description'),
        "assignee": assignee,
        "labels": fields.get('labels', []),
        "issue_type": fields.get('issuetype', {}).get('name', 'Unknown')
    }


def fetch_tickets_by_jql(jql: str) -> List[Dict[str, Any]]:
    """
    Fetch Jira tickets using JQL query.
    
    Args:
        jql: JQL query string
        
    Returns:
        List of Jira tickets
    """
    logger.info(f"Fetching tickets with JQL: {jql}")
    jira_api = api_manager.get_jira_api()
    tickets = jira_api.search_issues(jql=jql)
    logger.info(f"Found {len(tickets)} tickets")
    return tickets


def call_scrum_agent_for_summary(message: str) -> str:
    """
    Call scrum agent with a message for summarization.
    
    Args:
        message: Message to send to agent
        
    Returns:
        Agent response as string
    """
    logger.debug("Calling scrum agent for summary")
    agent = AgentFactory.create_scrum_agent()
    agent_result = agent(message)
    return agent_result.message['content'][0]['text']


def recursive_ticket_summary(ticket_infos: List[Dict[str, Any]]) -> str:
    """
    Create recursive summary of tickets that may exceed context window.
    Splits tickets into chunks and summarizes recursively if needed.
    
    Args:
        ticket_infos: List of ticket information dictionaries
        
    Returns:
        Summary string
    """
    logger.debug(f"Creating recursive summary for {len(ticket_infos)} tickets")
    
    # Convert ticket infos to string representation
    ticket_strings = [json.dumps(info, indent=2) for info in ticket_infos]
    
    summaries = []
    current_chunk = ""
    
    for ticket_str in ticket_strings:
        # If adding this ticket would exceed the limit, summarize current chunk first
        if len(current_chunk) + len(ticket_str) > CHAR_SPLITTER:
            if current_chunk:
                prompt = (
                    "Create a concise summary (max 500 characters) of the following Jira tickets, "
                    "highlighting key points, status, and main focus areas:\n\n"
                    f"{current_chunk}"
                )
                chunk_summary = call_scrum_agent_for_summary(prompt)
                summaries.append(chunk_summary)
                current_chunk = ""
        
        current_chunk += ticket_str + "\n"
    
    # Summarize remaining chunk
    if current_chunk:
        prompt = (
            "Create a concise summary (max 500 characters) of the following Jira tickets, "
            "highlighting key points, status, and main focus areas:\n\n"
            f"{current_chunk}"
        )
        chunk_summary = call_scrum_agent_for_summary(prompt)
        summaries.append(chunk_summary)
    
    # If we have multiple summaries, combine them
    if len(summaries) > 1:
        combined = "\n\n".join(summaries)
        if len(combined) > CHAR_SPLITTER:
            # Recursively summarize the summaries
            prompt = (
                "Combine and summarize the following ticket summaries into one cohesive summary "
                "(max 500 characters):\n\n"
                f"{combined}"
            )
            return call_scrum_agent_for_summary(prompt)
        return combined
    elif summaries:
        return summaries[0]
    else:
        return "No tickets to summarize"


def summarize_tickets_with_agent(tickets: List[Dict[str, Any]], context: str = "") -> TicketSummary:
    """
    Summarize multiple Jira tickets using AI agent with recursive summarization
    to handle large numbers of tickets that exceed context window.
    
    Args:
        tickets: List of Jira ticket dictionaries
        context: Additional context for the summary
        
    Returns:
        TicketSummary with analyzed information
        
    Raises:
        StructuredOutputException: If agent fails to produce structured output
        MaxTokensReachedException: If token limit is reached
    """
    logger.info(f"Summarizing {len(tickets)} tickets with AI agent")
    
    # Prepare ticket information
    ticket_infos = []
    for ticket in tickets:
        trim_ticket_description(ticket)
        info = extract_ticket_info(ticket)
        ticket_infos.append(info)
    
    # Calculate total size
    total_size = sum(len(json.dumps(info)) for info in ticket_infos)
    logger.info(f"Total ticket data size: {total_size} characters")
    
    # If total size exceeds limit, use recursive summarization
    if total_size > CHAR_SPLITTER:
        logger.info("Ticket data exceeds context window, using recursive summarization")
        pre_summary = recursive_ticket_summary(ticket_infos)
        
        # Now create structured summary from the pre-summary
        context_text = f"\nAdditional context: {context}" if context else ""
        prompt = f"""
        Based on the following pre-summarized ticket information, create a structured analysis.{context_text}
        Your response must be in English.
        
        Pre-summary of {len(tickets)} tickets:
        {pre_summary}
        
        Provide a comprehensive summary that includes:
        - Total number of tickets analyzed: {len(tickets)}
        - Overall summary of what these tickets represent
        - Key achievements or deliverables
        - Main focus areas (e.g., bug fixes, new features, backend, frontend, etc.)
        - Potential risks or blockers
        - Status breakdown (estimate based on the summary)
        
        Provide the result as JSON compliant with this pydantic schema:
        total_tickets: int = Field(description="Total number of tickets analyzed")
        summary: str = Field(description="Comprehensive summary of all tickets")
        key_achievements: str = Field(description="Key achievements across all tickets")
        main_focus_areas: str = Field(description="Main focus areas identified")
        potential_risks: str = Field(description="Potential risks identified")
        status_breakdown: str = Field(description="Breakdown of ticket statuses")
        
        DO NOT include anything else in your answer apart from valid JSON for the given pydantic schema.
        """
    else:
        # Normal processing for smaller datasets
        context_text = f"\nAdditional context: {context}" if context else ""
        prompt = f"""
        Analyze and summarize the following {len(tickets)} Jira tickets.{context_text}
        Your response must be in English.
        
        Provide a comprehensive summary that includes:
        - Total number of tickets analyzed
        - Overall summary of what these tickets represent
        - Key achievements or deliverables
        - Main focus areas (e.g., bug fixes, new features, backend, frontend, etc.)
        - Potential risks or blockers
        - Status breakdown (how many tickets in each status)
        
        Tickets to analyze:
        {json.dumps(ticket_infos, indent=2)}
        
        Provide the result as JSON compliant with this pydantic schema:
        total_tickets: int = Field(description="Total number of tickets analyzed")
        summary: str = Field(description="Comprehensive summary of all tickets")
        key_achievements: str = Field(description="Key achievements across all tickets")
        main_focus_areas: str = Field(description="Main focus areas identified")
        potential_risks: str = Field(description="Potential risks identified")
        status_breakdown: str = Field(description="Breakdown of ticket statuses")
        
        DO NOT include anything else in your answer apart from valid JSON for the given pydantic schema.
        """
    
    # Create LLM and agent
    llm = AgentFactory.create_ollama_model(max_tokens=OLLAMA_MAX_TOKENS)
    limit_hook = LimitToolCounts(max_tool_counts=MAX_TOOL_COUNTS)
    agent = AgentFactory.create_scrum_agent(model=llm, hooks=[limit_hook])
    
    # Execute agent
    response = agent(
        prompt,
        structured_output_model=TicketSummary,
        hooks=[limit_hook]
    )
    
    logger.info("Successfully summarized tickets")
    return response.structured_output


def format_summary_comment(summary: TicketSummary, jql: str) -> str:
    """
    Format the summary as a Jira comment.
    
    Args:
        summary: TicketSummary object
        jql: JQL query used to fetch tickets
        
    Returns:
        Formatted comment string
    """
    comment = f"""
[{datetime.today().strftime('%Y-%m-%d')}]
{summary.summary}

h3. Key Achievements
{summary.key_achievements}

h3. Main Focus Areas
{summary.main_focus_areas}

h3. Status Breakdown
{summary.status_breakdown}

h3. Potential Risks
{summary.potential_risks}

---
_This summary was automatically generated by the Scrum Agent._
"""
    return comment


def post_comment_to_ticket(ticket_key: str, comment: str) -> None:
    """
    Post a comment to a Jira ticket.
    
    Args:
        ticket_key: Jira ticket key (e.g., 'PROJ-123')
        comment: Comment text to post
    """
    logger.info(f"Posting comment to ticket {ticket_key}")
    jira_api = api_manager.get_jira_api()
    jira_api.add_comment(ticket_key, comment)
    logger.info(f"Successfully posted comment to {ticket_key}")
    

def load_comment_configs() -> List[Dict[str, Any]]:
    """
    Load comment configurations from database.
    If context is empty, fetch the target ticket's description from Jira API.
    
    Returns:
        List of comment configurations with target_ticket, source_jql, and context.
    """
    logger.info("Loading comment configurations from database")
    query = """
        SELECT target_ticket, source_jql, context
        FROM devops.crew_pm_comment;
    """
    rows = db_manager.execute_query(query)
    
    jira_api = api_manager.get_jira_api()
    configs = []
    
    for row in rows:
        target_ticket = row[0]
        source_jql = row[1]
        context = row[2] if row[2] else ""
        
        # If context is empty, fetch target ticket description from Jira
        if not context:
            try:
                logger.info(f"Context empty for {target_ticket}, fetching ticket description from Jira")
                ticket = jira_api.get_issue(target_ticket)
                description = ticket.get('fields', {}).get('description', '')
                if description:
                    context = description
                    logger.info(f"Using ticket description as context for {target_ticket}")
                else:
                    logger.warning(f"No description found for {target_ticket}")
            except Exception as e:
                logger.error(f"Failed to fetch ticket {target_ticket} from Jira: {e}")
        
        configs.append({
            "target_ticket": target_ticket,
            "source_jql": source_jql,
            "context": context
        })
    
    logger.info(f"Loaded {len(configs)} comment configurations")
    return configs


def process_comment_config(config: Dict[str, Any]) -> bool:
    """
    Process a single comment configuration.
    
    Args:
        config: Configuration dictionary with target_ticket, source_jql, and context
        
    Returns:
        True if successful, False otherwise
    """
    target_ticket = config['target_ticket']
    source_jql = config['source_jql']
    context = config['context']
    
    logger.info(f"Processing comment config for ticket {target_ticket}")
    logger.info(f"JQL: {source_jql}")
    
    try:
        # Fetch tickets
        tickets = fetch_tickets_by_jql(source_jql)
        
        if not tickets:
            logger.warning(f"No tickets found for JQL: {source_jql}")
            comment = f"*Automated Ticket Summary*\n\nNo tickets found for JQL: {{code}}{source_jql}{{code}}"
            post_comment_to_ticket(target_ticket, comment)
            return True
        
        # Summarize tickets
        summary = summarize_tickets_with_agent(tickets, context)
        
        # Format and post comment
        comment = format_summary_comment(summary, source_jql)
        post_comment_to_ticket(target_ticket, comment)
        
        logger.info(f"Successfully processed comment config for {target_ticket}")
        return True
        
    except StructuredOutputException as e:
        logger.error(f"Structured output failed for {target_ticket}: {e}")
        return False
    except MaxTokensReachedException as e:
        logger.error(f"Max tokens reached for {target_ticket}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error processing {target_ticket}: {e}")
        return False


if __name__ == "__main__":
    logger.info("Starting ticket updater scrum agent flow")
    
    # Load configurations from database
    configs = load_comment_configs()
    
    if not configs:
        logger.warning("No comment configurations found in database")
        exit(0)
    
    # Process each configuration
    total = len(configs)
    successful = 0
    failed = 0
    
    for config in configs:
        if process_comment_config(config):
            successful += 1
        else:
            failed += 1
    
    # Log summary
    logger.info("Ticket updater scrum agent flow complete")
    logger.info(f"Total configurations: {total}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
