"""
Ticket Categorizer Scrum Agent - Fetches Jira tickets based on JQL and categorizes them
using AI agent into predefined categories with optional Confluence architecture context.
"""
import json
import re
import pandas as pd
from typing import List, Dict, Any, Optional
from tools.strands_limit_hook import LimitToolCounts
from common_utils import (
    ConfigManager,
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
api_manager = APIClientManager(config_manager)

# Configuration
jql = "assignee = pjesensky AND resolution = Unresolved"

category_configs = [{
    "name": "SBOM - Software supply chain security",
    "description": "All security related topics",
    "architecture": "326031619"
}]


def load_confluence_context(page_id: str) -> Optional[str]:
    """
    Load Confluence page content as additional context for categorization.
    
    Args:
        page_id: Confluence page ID
        
    Returns:
        Page content as string, or None if loading fails
    """
    try:
        confluence_api = api_manager.get_confluence_api()
        page_data = confluence_api.get_page_content(page_id)
        logger.info(f"Loaded Confluence page: {page_data['title']}")
        return f"Architecture Context ({page_data['title']}):\n{page_data['content']}"
    except Exception as e:
        logger.error(f"Failed to load Confluence page {page_id}: {e}")
        return None


def parse_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Try to extract and parse JSON from plain text response.
    Handles cases where JSON is wrapped in markdown code blocks or mixed with other text.
    
    Args:
        text: Plain text that may contain JSON
        
    Returns:
        Parsed JSON dictionary or None if parsing fails
    """
    try:
        # First, try direct JSON parse
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    json_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
    matches = re.findall(json_pattern, text, re.DOTALL)
    if matches:
        try:
            return json.loads(matches[0])
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON object in text (between { and })
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    matches = re.findall(json_pattern, text, re.DOTALL)
    for match in matches:
        try:
            parsed = json.loads(match)
            # Validate it has expected fields
            if 'key' in parsed and 'category' in parsed:
                return parsed
        except json.JSONDecodeError:
            continue
    
    return None


def categorize_ticket_with_agent(
    ticket: Dict[str, Any],
    category_config: Dict[str, Any],
    confluence_context: Optional[str] = None
) -> Dict[str, Any]:
    """
    Categorize a Jira ticket using AI agent.
    
    Args:
        ticket: Jira ticket dictionary
        category_config: Category configuration with name, description, and optional architecture
        confluence_context: Optional Confluence page content for additional context
        
    Returns:
        Dictionary with categorization results including ticket info, category match, confidence, and explanation
    """
    ticket_key = ticket['key']
    logger.info(f"Categorizing ticket {ticket_key} with AI agent")
    
    # Create LLM and agent
    llm = AgentFactory.create_ollama_model(max_tokens=OLLAMA_MAX_TOKENS)
    limit_hook = LimitToolCounts(max_tool_counts=MAX_TOOL_COUNTS)
    agent = AgentFactory.create_scrum_agent(model=llm, hooks=[limit_hook])
    
    # Extract ticket fields
    fields = ticket.get('fields', {})
    summary = fields.get('summary', 'No summary')
    description = fields.get('description', 'No description')
    
    # Trim description if too long
    if description and len(description) > MAX_DESCRIPTION_LENGTH:
        description = description[:MAX_DESCRIPTION_LENGTH]
        logger.debug(f"Trimmed description for {ticket_key} to {MAX_DESCRIPTION_LENGTH} characters")
    
    issue_type = fields.get('issuetype', {}).get('name', 'Unknown')
    labels = ', '.join(fields.get('labels', []))
    
    # Build context section
    context_section = ""
    if confluence_context:
        context_section = f"\n\nAdditional Architecture Context:\n{confluence_context[:1000]}"
    
    # Prepare prompt
    prompt = f"""
    Analyze the following Jira ticket and determine if it belongs to this category.
    Your response must be in English.
    
    Category to evaluate:
    - Name: {category_config['name']}
    - Description: {category_config['description']}{context_section}
    
    Determine if this ticket matches the category above.
    Provide the result as JSON compliant with this pydantic schema:
    key: str = Field(description="Jira issue key")
    summary: str = Field(description="Brief summary of the ticket")
    category: str = Field(description="The category name if it matches, or 'No Match' if it doesn't")
    confidence: str = Field(description="Confidence level of the categorization (high/medium/low)")
    reasoning: str = Field(description="Detailed explanation of why this ticket does or doesn't match the category")
    
    DO NOT include anything else in your answer apart from valid JSON for the given pydantic schema.
    
    Ticket to categorize:
    Key: {ticket_key}
    Summary: {summary}
    Description: {description}
    Type: {issue_type}
    Labels: {labels}
    """
    
    try:
        # Execute agent
        response = agent(
            prompt,
            hooks=[limit_hook]
        )
        json_response = parse_json_from_text( response.message ['content'] [0] ['text'])
        logger.info(f"Successfully categorized ticket {ticket_key}")
        
        # Build result dictionary
        result = {
            'ticket_key': ticket_key,
            'ticket_summary': summary,
            'ticket_type': issue_type,
            'ticket_labels': labels,
            'category_name': category_config['name'],
            'matches_category': json_response ['category'] != 'No Match',
            'confidence': json_response ['confidence'],
            'explanation': json_response ['reasoning']
        }
        return result
        
    except Exception as e:
        logger.error(f"Unexpected error processing {ticket_key}: {e}")
        return {
            'ticket_key': ticket_key,
            'ticket_summary': summary,
            'ticket_type': issue_type,
            'ticket_labels': labels,
            'category_name': category_config['name'],
            'matches_category': False,
            'confidence': 'error',
            'explanation': f"Unexpected error: {str(e)}"
        }

def process_tickets(
    tickets: List[Dict[str, Any]],
    category_configs: List[Dict[str, Any]]
) -> pd.DataFrame:
    """
    Process all tickets against all category configurations.
    
    Args:
        tickets: List of Jira ticket dictionaries
        category_configs: List of category configuration dictionaries
        
    Returns:
        pandas DataFrame with categorization results
    """
    results = []
    
    for category_config in category_configs:
        logger.info(f"Processing category: {category_config['name']}")
        
        # Load Confluence context if architecture page is specified
        confluence_context = None
        if 'architecture' in category_config:
            confluence_context = load_confluence_context(category_config['architecture'])
        
        # Process each ticket for this category
        for ticket in tickets:
            result = categorize_ticket_with_agent(
                ticket,
                category_config,
                confluence_context
            )
            if result:
                results.append(result)
    
    # Create DataFrame
    df = pd.DataFrame(results)
    
    logger.info(f"Processed {len(tickets)} tickets against {len(category_configs)} categories")
    logger.info(f"Total categorization results: {len(results)}")
    
    return df


def save_results_to_csv(df: pd.DataFrame, output_path: str = "ticket_categorization_results.csv") -> None:
    """
    Save categorization results to CSV file.
    
    Args:
        df: DataFrame with categorization results
        output_path: Path to output CSV file
    """
    df.to_csv(output_path, index=False)
    logger.info(f"Results saved to {output_path}")


if __name__ == "__main__":
    logger.info("Starting ticket categorizer scrum agent flow")
    
    # Step 1: Load tickets via JQL
    jira_api = api_manager.get_jira_api()
    logger.info(f"Searching tickets with JQL: {jql}")
    tickets = jira_api.search_issues(jql=jql)
    logger.info(f"Found {len(tickets)} tickets")
    
    # Step 2-3: Process tickets against categories (with Confluence context if available)
    df_results = process_tickets(tickets, category_configs)
    
    # Step 4: Display results summary
    logger.info("\n=== Categorization Results Summary ===")
    logger.info(f"Total rows: {len(df_results)}")
    logger.info("\nMatches by category:")
    for category in df_results['category_name'].unique():
        category_df = df_results[df_results['category_name'] == category]
        matches = category_df['matches_category'].sum()
        logger.info(f"  {category}: {matches}/{len(category_df)} matches")
    
    logger.info("\nConfidence distribution:")
    logger.info(df_results['confidence'].value_counts().to_string())
    
    # Step 5: Save to CSV
    output_file = "ticket_categorization_results.csv"
    save_results_to_csv(df_results, output_file)
    
    logger.info("\nTicket categorizer scrum agent flow complete")
    logger.info(f"Results saved to: {output_file}")