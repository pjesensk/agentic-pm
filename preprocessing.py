import os
import logging
import hvac
import psycopg2
import json
from dotenv import load_dotenv
from connectors.confluenceapi import ConfluenceApi
from connectors.jirapi import JiraApi
from model.jira_context import JiraContext
from jinja2 import Environment, FileSystemLoader
from strands import Agent
from strands.models.ollama import OllamaModel
from strands.types.exceptions import StructuredOutputException, MaxTokensReachedException
from tools.strands_limit_hook import LimitToolCounts

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
log.addHandler(logging.StreamHandler())
load_dotenv()

client = hvac.Client(url=os.getenv("VAULT_URL"))
client.auth.approle.login(
    role_id=os.getenv("VAULT_ROLE_ID"),
    secret_id=os.getenv("VAULT_SECRET_ID"),
)

db_secret = client.secrets.kv.read_secret_version(path="secret/cmdb")

DB_NAME = db_secret["data"]["data"]["psql_db"]
DB_USER = db_secret["data"]["data"]["psql_user"]
DB_PASSWORD = db_secret["data"]["data"]["psql_pw"]
DB_HOST = db_secret["data"]["data"]["psql_host"]
DB_PORT = db_secret["data"]["data"]["psql_port"]

llm_secret = client.secrets.kv.read_secret_version(path="secret/llm")

jira_secret = client.secrets.kv.read_secret_version(path="secret/jira")
confluence_secret = client.secrets.kv.read_secret_version(path="secret/confluence")

jira_api = JiraApi(
    hostname=jira_secret["data"]["data"]["url"],
    auth_token=jira_secret["data"]["data"]["token"],
)
confluence_api = ConfluenceApi(
    hostname=confluence_secret["data"]["data"]["url"],
    auth_token=confluence_secret["data"]["data"]["token"],
)

jinja_env = Environment(loader=FileSystemLoader("templates"))
exec_template = jinja_env.get_template("exec_summary.html.j2")


def load_items():
    items = []
    with psycopg2.connect(
        dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=DB_PORT
    ) as db_connection:
        db_connection.set_session(autocommit=True)
        with db_connection.cursor() as cursor:
          log.info("Successfully connected to PostgreSQL database.")
          select_sql = "SELECT id, confluence_id, jira_epic, title, summary_jql, goal, deliverables, success_criteria, due_date FROM devops.crew_pm_exec;"
          cursor.execute(select_sql)
          for row in cursor.fetchall():
             items.append({"id": row[0], "jira": row[2], "confluence": row[1], "title": row[3], "jql": row[4], "goal": row[5], "deliverables": row[6], "success_criteria": row[7], "due_date": row[8] })         
    return items

def store_context(key,confluence_id, content, metadata):
   with psycopg2.connect(
      dbname=DB_NAME,
      user=DB_USER,
      password=DB_PASSWORD,
      host=DB_HOST,
      port=DB_PORT,
   ) as db_connection:
      db_connection.set_session(autocommit=True)
      with db_connection.cursor() as cursor:
         sql_query = "INSERT INTO devops.crew_pm_cache (key, confluence_id, context,metadata) VALUES (%s,%s,%s,%s) ON CONFLICT (key,confluence_id) DO UPDATE SET context=%s, metadata=%s"
         cursor.execute(
            sql_query,
            (
               key,
               confluence_id,
               content,
               metadata,
               content, 
               metadata
            ),
         )

def get_cached_keys():
   keys = []
   with psycopg2.connect(
      dbname=DB_NAME,
      user=DB_USER,
      password=DB_PASSWORD,
      host=DB_HOST,
      port=DB_PORT,
   ) as db_connection:
      db_connection.set_session(autocommit=True)
      with db_connection.cursor() as cursor:
        sql_query = "Select key from devops.crew_pm_cache"
        cursor.execute(sql_query)
        for row in cursor.fetchall():
           keys.append(row[0])    
        return keys

if __name__ == "__main__":
    for item in load_items():
        tickets = jira_api.search_issues(jql=item["jql"])
        keys = get_cached_keys ()
        for ticket in tickets:
            log.debug (f"Found jira issue {ticket['key']}")
            if ticket['key'] not in keys:
                log.debug (f"Processing jira issue {ticket['key']} because not cached yet")
                #trim the description to fit context window
                if ticket['fields']['description'] and len(ticket['fields']['description']) > 2048:
                    ticket['fields']['description'] = ticket ['fields']['description'][:2048]
                try:
                    my_llm = OllamaModel(
                        model_id="granite4",
                        host = "http://localhost:11434",
                        temperature=0,
                        max_tokens=4096
                    )
                    limit_hook = LimitToolCounts(max_tool_counts={"sleep": 3})
                    scrum_agent = Agent(
                    model=my_llm,
                    system_prompt="""
                        You are scrum master managing project team for which you need to report various information from Jira backlog to project manager. Your project is agile project with 2 weeks sprints and follows the standard flow of design, architecture,build and so on.
                    """
                    )
                    response = scrum_agent(f"""
                    Analyze the following Jira ticket in the context of the project '{item['title']} Your response must be in English.
                    You must provide a value for ALL fields. If information is not in the ticket, infer it from the context.
                    For each field, provide a concise answer (max 255 characters).
                    Provide the result json which is compliant with this pydantic schema: 
                    key: str = Field(description="Jira issue key")
                    summary: str = Field(description="Concise jira issue summary")
                    achievements: str = Field(description="What was achieved with this ticket in relation to project goals.")
                    deliverable: str = Field(description="The concrete deliverable from this ticket.")
                    focus: str = Field(description="The main focus area of this ticket (e.g., bug fix, new feature, backend,  frontend, etc.).")
                    risks: str = Field(description="Any potential risks that could arise from or are highlighted by this ticket.")
                    DO NOT include anything else to your answer apart from valid json for given pydantic schema.
                    Given the following jira issue {ticket} provide only the result json.""",
                    structured_output_model=JiraContext,
                    hooks=[limit_hook]
                    )
                    store_context (ticket['key'],
                            item['confluence'],
                            response.structured_output.model_dump_json(indent=2),
                            json.dumps({
                                "key": ticket['key'],
                                "created": ticket['fields']['created'],
                                "title": ticket['fields']['summary'],
                                "priority": ticket['fields']['priority']['name'] if 'priority' in ticket['fields'] and ticket['fields']['priority'] is not None else "Normal",
                                "status": ticket['fields']['status']['name'],
                                "description": ticket['fields']['description'],
                                "assignee": ticket['fields']['assignee']["emailAddress"] if 'assignee' in ticket['fields'] and ticket['fields']['assignee'] is not None else "Unassigned" ,
                                "labels": ticket['fields']['labels']
                            }))
                    log.debug (f"{ticket['key']} was processed with response {response.structured_output.model_dump_json(indent=2)}")
                except StructuredOutputException as e:
                    log.error(f"Structured output failed: {e}")
                except MaxTokensReachedException as e:
                    log.error(f"Max tokens reached: {e}")
                    