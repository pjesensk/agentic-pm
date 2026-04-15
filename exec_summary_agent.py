"""
Executive Summary Agent - Generates executive summaries from Jira ticket analysis.
Creates comprehensive project status reports with achievements, risks, and timelines.
"""
import html
import calendar
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Set
from pydantic import TypeAdapter
from model.exec_summary import ExecSummary
from model.exec_summary_timeline import Timeline
from model.exec_summary_prereq import Prerequisities
from common_utils import (
    ConfigManager,
    DatabaseManager,
    APIClientManager,
    AgentFactory,
    setup_logging,
    jinja_env
)

# Constants
ISOFORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
SPRINT_LENGTH = 28  # days
SPRINT_CLOSE_STATES = [
    'Implemented', 'Delivered', 'Done (Accepted)', 
    'Closed', 'Fixed', 'Done', 'verworfen'
]
CHAR_SPLITTER = 3800  # max number of characters for context window
SUMMARY_MAX_LINES = 5
SUMMARY_MAX_CHARS = 255
DEFAULT_YEAR = 2026

# Setup logging
logger = setup_logging(__name__)

# Initialize managers
config_manager = ConfigManager()
db_manager = DatabaseManager(config_manager)
api_manager = APIClientManager(config_manager)

# Jinja2 template
exec_template = jinja_env.get_template('exec_summary.html.j2')

# Type adapter for prerequisites
PrereqsSetAdapter = TypeAdapter(Set[Prerequisities])


def load_items() -> List[Dict[str, Any]]:
    """
    Load project items from database.
    
    Returns:
        List of project items with their configuration.
    """
    logger.info("Loading project items from database")
    query = """
        SELECT id, confluence_id, jira_epic, title, summary_jql, goal, 
               deliverables, success_criteria, due_date, confluence_architecture, 
               status, status_desc, prerequisities 
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
            "confluence_architecture": row[9],
            "status": row[10],
            "status_desc": row[11],
            "prereq": row[12]
        })
    
    logger.info(f"Loaded {len(items)} project items")
    return items


def load_ticket_context(confluence_id: str) -> List[Dict[str, Any]]:
    """
    Load ticket context from cache for a specific confluence page.
    
    Args:
        confluence_id: Confluence page ID
        
    Returns:
        List of ticket contexts with metadata
    """
    logger.info(f"Loading ticket context for confluence page {confluence_id}")
    query = """
        SELECT key, metadata, context 
        FROM devops.crew_pm_cache 
        WHERE confluence_id=%s;
    """
    rows = db_manager.execute_query(query, (confluence_id,))
    
    items = []
    for row in rows:
        items.append({
            "key": row[0],
            "metadata": row[1],
            "context": row[2]
        })
    
    logger.info(f"Loaded {len(items)} ticket contexts")
    return items


def update_confluence(confluence_id: str, item: ExecSummary) -> None:
    """
    Update Confluence page with executive summary.
    
    Args:
        confluence_id: Confluence page ID
        item: Executive summary object
    """
    logger.info(f"Updating Confluence page {confluence_id}")
    
    template_data = {"item": item}
    rendered_html = exec_template.render(template_data)
    
    # Save to file for debugging
    with open("demo.html", "w") as f:
        f.write(rendered_html)
    logger.debug("Saved rendered HTML to demo.html")
    
    # Update Confluence
    confluence_api = api_manager.get_confluence_api()
    confluence_api.update_page(confluence_id, rendered_html)
    logger.info(f"Successfully updated Confluence page {confluence_id}")


def call_pm_agent(message: str) -> str:
    """
    Call PM agent with a message.
    
    Args:
        message: Message to send to agent
        
    Returns:
        Agent response as HTML-escaped string
    """
    logger.debug("Calling PM agent")
    agent = AgentFactory.create_pm_agent()
    agent_result = agent(message)
    return html.escape(agent_result.message['content'][0]['text'])


def call_scrum_agent(message: str) -> str:
    """
    Call scrum agent with a message.
    
    Args:
        message: Message to send to agent
        
    Returns:
        Agent response as HTML-escaped string
    """
    logger.debug("Calling scrum agent")
    agent = AgentFactory.create_scrum_agent()
    agent_result = agent(message)
    return html.escape(agent_result.message['content'][0]['text'])


def recursive_summary(content: Set[str]) -> str:
    """
    Create recursive summary of content that exceeds context window.
    
    Args:
        content: Set of content strings to summarize
        
    Returns:
        Summary string
    """
    logger.debug("Creating recursive summary")
    ctx = ""
    prompt_template = (
        "Create one line summary of MAXIMUM 255 characters long describing "
        "highlights, achievements, risks, focus and deliverables from following "
        "content {ctx}. Return only summary content MAX 255 characters long "
        "without any other additional information."
    )
    
    for line in content:
        if len(ctx) + len(line) > CHAR_SPLITTER:
            ctx = call_pm_agent(prompt_template.format(ctx=ctx))
        ctx += line
    
    return call_pm_agent(prompt_template.format(ctx=ctx))

def create_timeline(tickets: List[Dict[str, Any]], year: int = DEFAULT_YEAR) -> Set[Timeline]:
    """
    Create timeline from tickets.
    
    Args:
        tickets: List of ticket contexts
        year: Year for timeline
        
    Returns:
        Set of Timeline objects
    """
    logger.info(f"Creating timeline for year {year}")
    result = set()
    
    # Create monthly timeline entries
    for month in range(1, 13):
        _, num_days = calendar.monthrange(year, month)
        result.add(Timeline(
            start_date=date(year, month, 1),
            end_date=date(year, month, num_days),
            description="",
            metadata=set(),
            context=set()
        ))
    
    # Populate timeline with ticket data
    for ticket in tickets:
        created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
        for month in result:
            if month.start_date < created_date < month.end_date:
                context_str = (
                    ticket['context']['focus'] + 
                    ticket['context']['achievements'] + 
                    ticket['context']['deliverable']
                )
                month.context.add(context_str)
    
    # Generate descriptions for each month
    for month in result:
        if month.context:
            month.description = recursive_summary(month.context)
    
    logger.info(f"Created timeline with {len(result)} months")
    return result

def filter_recent_tickets(
    tickets: List[Dict[str, Any]], 
    days: int = SPRINT_LENGTH,
    closed_only: bool = True
) -> List[Dict[str, Any]]:
    """
    Filter tickets by date and status.
    
    Args:
        tickets: List of ticket contexts
        days: Number of days to look back
        closed_only: If True, only include closed tickets
        
    Returns:
        Filtered list of tickets
    """
    cutoff_date = date.today() - timedelta(days=days)
    filtered = []
    
    for ticket in tickets:
        created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
        if created_date > cutoff_date:
            status = ticket['metadata']['status']
            if closed_only:
                if status in SPRINT_CLOSE_STATES:
                    filtered.append(ticket)
            else:
                if status not in SPRINT_CLOSE_STATES:
                    filtered.append(ticket)
    
    return filtered

def summarize_achievements(tickets: List[Dict[str, Any]]) -> Set[str]:
    """
    Summarize achievements from recent closed tickets.
    
    Args:
        tickets: List of ticket contexts
        
    Returns:
        Set of achievement summaries
    """
    logger.info("Summarizing achievements")
    recent_tickets = filter_recent_tickets(tickets, closed_only=True)
    
    if not recent_tickets:
        logger.info("No recent closed tickets found")
        return set()
    
    ctx = "".join(ticket['context']['achievements'] for ticket in recent_tickets)
    
    prompt = (
        f"Summarize and highlight achievements in {SUMMARY_MAX_LINES} lines, "
        f"each max. {SUMMARY_MAX_CHARS} characters from the following content {ctx}. "
        f"Return only those {SUMMARY_MAX_LINES} lines without any other additional output. "
        "Do not include line numbers into the output."
    )
    
    result = call_pm_agent(prompt).split("\n")
    logger.info(f"Generated {len(result)} achievement summaries")
    return set(result)

def summarize_focus(tickets: List[Dict[str, Any]]) -> Set[str]:
    """
    Summarize focus areas from recent closed tickets.
    
    Args:
        tickets: List of ticket contexts
        
    Returns:
        Set of focus summaries
    """
    logger.info("Summarizing focus areas")
    recent_tickets = filter_recent_tickets(tickets, closed_only=True)
    
    if not recent_tickets:
        logger.info("No recent closed tickets found")
        return set()
    
    ctx = "".join(ticket['context']['focus'] for ticket in recent_tickets)
    
    prompt = (
        f"Summarize the focus items which were taken in last sprint in {SUMMARY_MAX_LINES} lines, "
        f"each max. {SUMMARY_MAX_CHARS} characters from the following content {ctx}. "
        f"Return only those {SUMMARY_MAX_LINES} lines without any other additional output. "
        "Do not include line numbers into the output."
    )
    
    result = call_pm_agent(prompt).split("\n")
    logger.info(f"Generated {len(result)} focus summaries")
    return set(result)

def summarize_next_steps(tickets: List[Dict[str, Any]]) -> Set[str]:
    """
    Summarize next steps from recent open tickets.
    
    Args:
        tickets: List of ticket contexts
        
    Returns:
        Set of next step summaries
    """
    logger.info("Summarizing next steps")
    recent_tickets = filter_recent_tickets(tickets, closed_only=False)
    
    if not recent_tickets:
        logger.info("No recent open tickets found")
        return set()
    
    ctx = ""
    for ticket in recent_tickets:
        ctx += ticket['metadata']['title']
        if ticket['metadata']['description'] is not None:
            ctx += ticket['metadata']['description']
    
    prompt = (
        f"Summarize the next steps which should be taken in next sprint in {SUMMARY_MAX_LINES} lines, "
        f"each max. {SUMMARY_MAX_CHARS} characters from the following content {ctx}. "
        f"Return only those {SUMMARY_MAX_LINES} lines without any other additional output. "
        "Do not include line numbers into the output."
    )
    
    result = call_scrum_agent(prompt).split("\n")
    logger.info(f"Generated {len(result)} next step summaries")
    return set(result)

def summarize_risks(tickets: List[Dict[str, Any]]) -> Set[str]:
    """
    Summarize risks from recent open tickets.
    
    Args:
        tickets: List of ticket contexts
        
    Returns:
        Set of risk summaries
    """
    logger.info("Summarizing risks")
    recent_tickets = filter_recent_tickets(tickets, closed_only=False)
    
    if not recent_tickets:
        logger.info("No recent open tickets found")
        return set()
    
    ctx = ""
    for ticket in recent_tickets:
        ctx += ticket['metadata']['title']
        if ticket['metadata']['description'] is not None:
            ctx += ticket['metadata']['description']
    
    prompt = (
        f"Summarize the risks which might occur in next sprint in {SUMMARY_MAX_LINES} lines, "
        f"each max. {SUMMARY_MAX_CHARS} characters from the following content {ctx}. "
        f"Return only those {SUMMARY_MAX_LINES} lines without any other additional output. "
        "Do not include line numbers into the output."
    )
    
    result = call_scrum_agent(prompt).split("\n")
    logger.info(f"Generated {len(result)} risk summaries")
    return set(result)

def process_executive_summary(item: Dict[str, Any]) -> ExecSummary:
    """
    Process executive summary for a project item.
    
    Args:
        item: Project item configuration
        
    Returns:
        ExecSummary object
    """
    logger.info(f"Processing executive summary for project: {item['title']}")
    
    # Load ticket contexts
    tickets = load_ticket_context(item["confluence"])
    logger.info(f"Loaded {len(tickets)} tickets for analysis")
    
    # Create base executive summary object
    exec_summary_obj = ExecSummary(
        confluence_id=item["confluence"],
        name=item["title"],
        description=item["goal"],
        status=item['status'],
        statusdesc=item['status_desc'],
        duedate=item["due_date"],
        achievements=set(),
        deliverables=set(filter(
            None,
            item['deliverables'].split('###') + item['success_criteria'].split('###')
        )),
        prerequisites=PrereqsSetAdapter.validate_python(item['prereq']),
        focus=set(),
        next_steps=set(),
        risks=set(),
        decisions=set(),
        timeline=create_timeline(tickets),
        links=set(),
        raci=set(),
    )
    
    # Generate summaries using AI agents
    exec_summary_obj.achievements = sorted(set(filter(None, summarize_achievements(tickets))))
    exec_summary_obj.focus = sorted(set(filter(None, summarize_focus(tickets))))
    exec_summary_obj.next_steps = sorted(set(filter(None, summarize_next_steps(tickets))))
    exec_summary_obj.risks = sorted(set(filter(None, summarize_risks(tickets))))
    
    # Sort timeline
    exec_summary_obj.timeline = sorted(
        exec_summary_obj.timeline,
        key=lambda item: item.start_date,
        reverse=True
    )
    
    # Populate links
    exec_summary_obj.links.add(
        f"<a href='https://jira/browse/{item['jira']}'>"
        f"{item['jira']} - Master ticket</a>"
    )
    exec_summary_obj.links.add(
        f"<a href='https://confluence/spaces/pages/{item['confluence']}'>"
        " Executive summary</a>"
    )
    exec_summary_obj.links.add(
        f"<a href='{item['confluence_architecture']}'>Platform architecture</a>"
    )
    
    logger.info(f"Completed executive summary for project: {item['title']}")
    return exec_summary_obj

if __name__ == "__main__":
    logger.info("Starting executive summary flow")
    items = load_items()
    
    if not items:
        logger.warning("No project items found")
    
    # Process each project item
    processed = 0
    failed = 0
    
    for item in items:
        try:
            exec_summary = process_executive_summary(item)
            update_confluence(item["confluence"], exec_summary)
            processed += 1
        except Exception as e:
            logger.error(f"Failed to process project {item['title']}: {e}")
            failed += 1
    
    stats = {
        'projects': len(items),
        'processed': processed,
        'failed': failed
    }
    
    logger.info(f"Executive summary flow complete: {stats}")