import os
import logging
import hvac
import psycopg2
import calendar
import html
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from pydantic import TypeAdapter
from typing import Set
from connectors.confluenceapi import ConfluenceApi
from connectors.jirapi import JiraApi
from jinja2 import Environment, FileSystemLoader
from strands import Agent
from strands.models.ollama import OllamaModel
from model.exec_summary import ExecSummary
from model.exec_summary_timeline import Timeline
from model.exec_summary_prereq import Prerequisities


ISOFORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
SPRINT_LENGTH = 14 # days
SPRINT_CLOSE_STATES = ['Implemented', 'Delivered', 'Done (Accepted)', 'Closed', 'Fixed', 'Done', 'verworfen' ]
CHAR_SPLITTER = 3800 # max number of characters for context window

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

llm_secret = client.secrets.kv.read_secret_version(path='secret/llm')

OLLAMA_HOST="http://localhost:11434"

jira_secret = client.secrets.kv.read_secret_version(path='secret/jira')
confluence_secret = client.secrets.kv.read_secret_version(path='secret/confluence')

jira_api = JiraApi(hostname=jira_secret['data']['data']['url'], auth_token=jira_secret['data']['data']['token'])
confluence_api = ConfluenceApi(hostname=confluence_secret['data']['data']['url'], auth_token=confluence_secret['data']['data']['token'])
   
jinja_env = Environment(loader=FileSystemLoader('templates'))
exec_template = jinja_env.get_template('exec_summary.html.j2')

PrereqsSetAdapter = TypeAdapter(Set[Prerequisities])

def load_items ():
  items = []
  with psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    ) as db_connection:
      db_connection.set_session(autocommit=True)
      with db_connection.cursor() as cursor:
          print("Successfully connected to PostgreSQL database.")
          select_sql = "SELECT id, confluence_id, jira_epic, title, summary_jql, goal, deliverables, success_criteria, due_date, confluence_architecture, status, status_desc, prerequisities FROM devops.crew_pm_exec;"
          cursor.execute(select_sql)
          for row in cursor.fetchall():
             items.append({"id": row[0], "jira": row[2], "confluence": row[1], "title": row[3], "jql": row[4], "goal": row[5], "deliverables": row[6], "success_criteria": row[7], "due_date": row[8], "confluence_architecture": row[9], "status": row[10], "status_desc": row[11], "prereq": row[12] })         
  return items

def load_ticket_context (confluenceId):
  items = []
  with psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    ) as db_connection:
      db_connection.set_session(autocommit=True)
      with db_connection.cursor() as cursor:
         select_sql = "SELECT key, metadata, context FROM devops.crew_pm_cache where confluence_id=%s;"
         cursor.execute(select_sql,(confluenceId,))
         for row in cursor.fetchall():
            items.append({"key": row[0], "metadata": row[1], "context": row[2]})       
         return items

def update_confluence(confluence_id, item):
      template_data = {
         "item": item
      }
      rendered_html = exec_template.render(template_data)
      with open("demo.html", "w") as f:
         f.write(rendered_html)
      confluence_api.update_page(confluence_id, rendered_html)

def recursive_summary (content):
   ctx = ""
   for line in content:
      if len(ctx) + len(line) > CHAR_SPLITTER:
         ctx = pm_agent(f"Create one line summary of MAXIMUM 255 characters long describing highilights, achievements, risks, focus and deliverables from following content {ctx}. Return only summary content MAX 255 characters long without any other additional information. ")
      ctx += line
   return pm_agent(f"Create one line summary of MAXIMUM 255 characters long describing highilights, achievements, risks, focus and deliverables from following content {ctx}. Return only summary content MAX 255 characters long without any other additional information. ")

def create_timeline(tickets, year=2025):
   result = set()
   for month in range(1, 13):
      _, num_days = calendar.monthrange(year, month)
      result.add (Timeline(
         start_date=date(year, month, 1),
         end_date=date(year, month, num_days),
         description="",
         metadata=set(),
         context= set()
      )) 
   for ticket in tickets:
      created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
      for month in result:
         if month.start_date < created_date and created_date < month.end_date:
            month.context.add(ticket['context']['focus'] + ticket['context']['achievements'] + ticket['context']['deliverable'])
   for month in result:
      month.description = recursive_summary (month.context)
   return result

def summarize_achievements (tickets):
   ctx = ""
   for ticket in tickets:
      created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
      if created_date > date.today() - timedelta(days=SPRINT_LENGTH) and ticket['metadata']['status'] in SPRINT_CLOSE_STATES: 
         ctx += ticket['context']['achievements']
   if ctx:
      return pm_agent(f"Summarize and highilight achievements in 5 lines, each max. 255 characters from the following content {ctx}. Return only those 5 lines without any other additional output. Do not include line numbers into the output.").split("\n")
   else:
      return set()

def summarize_focus (tickets):
   ctx = ""
   for ticket in tickets:
      created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
      if created_date > date.today() - timedelta(days=SPRINT_LENGTH) and ticket['metadata']['status'] in SPRINT_CLOSE_STATES: 
         ctx += ticket['context']['focus']
   if ctx:
      return pm_agent(f"Summarize the focus items which were taken in last sprint in 5 lines, each max. 255 characters from the following content {ctx}. Return only those 5 lines without any other additional output. Do not include line numbers into the output.").split("\n")
   else:
      return set()

def summarize_next_steps (tickets):
   ctx = ""
   for ticket in tickets:
      created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
      if created_date > date.today() - timedelta(days=SPRINT_LENGTH) and ticket['metadata']['status'] not in SPRINT_CLOSE_STATES: 
         ctx += ticket['metadata']['title'] + ticket['metadata']['description']
   if ctx:
      return scrum_agent(f"Summarize the next steps which should be taken in next sprint in 5 lines, each max. 255 characters from the following content {ctx}. Return only those 5 lines without any other additional output. Do not include line numbers into the output.").split("\n")
   else:
      return set()

def summarize_risks (tickets):
   ctx = ""
   for ticket in tickets:
      created_date = datetime.strptime(ticket['metadata']['created'], ISOFORMAT).date()
      if created_date > date.today() - timedelta(days=SPRINT_LENGTH) and ticket['metadata']['status'] not in SPRINT_CLOSE_STATES: 
         ctx += ticket['metadata']['title'] + ticket['metadata']['description']
   if ctx:
      return scrum_agent(f"Summarize the risks which might occur in next sprint in 5 lines, each max. 255 characters from the following content {ctx}. Return only those 5 lines without any other additional output. Do not include line numbers into the output.").split("\n")
   else:
      return set()

def scrum_agent (message):
   my_llm = OllamaModel(
      model_id="granite4",
      host = "http://localhost:11434",
      temperature=0
   )

   agent = Agent(
      model=my_llm,
      #tools=[get_ticket_timeline],
      system_prompt="""
      You are scrum master managing project team for which you need to report various information from Jira backlog to project manager. Your project is agile project with 2 weeks sprints and follows the standard flow of design, architecture,build and so on. You are given tools to retrieve information from Jira.
      """
   )
   agent_result = agent(message)
   return html.escape(agent_result.message['content'][0]['text'])

def pm_agent (message):
   my_llm = OllamaModel(
      model_id="granite4",
      host = "http://localhost:11434",
      temperature=0
   )
   agent = Agent(
      model=my_llm,
      #tools=[jira_retrieval_tool],
      system_prompt="""
      You are project manager who has to report executive summaries about project status to management board. Your project is agile project with 2 weeks sprints and follows the standard flow of design, architecture,build and so on. You get information from scrum master which you have to transform to high level summary for final report.
      """
   )
   agent_result = agent(message)
   return html.escape(agent_result.message['content'][0]['text'])

if __name__ == "__main__":
   for item in load_items():
      # we have to manually process issues because of context size and use AI just for atomic tasks
      tickets = load_ticket_context(item["confluence"])
      exec_summary_obj = ExecSummary(
         confluence_id=item["confluence"],
         name=item["title"],
         description=item["goal"],
         status=item['status'], 
         statusdesc=item['status_desc'], # Default status description
         duedate=item["due_date"],
         achievements=set(),
         deliverables=set(filter(None,item['deliverables'].split('###') + item['success_criteria'].split('###'))),
         prerequisites= PrereqsSetAdapter.validate_python(item['prereq']),
         focus=set(),
         next_steps=set(),
         risks=set(),
         decisions=set(),
         timeline=create_timeline(tickets),
         links=set(),
         raci=set(),
      )

      exec_summary_obj.achievements = sorted(set(filter(None, (summarize_achievements(tickets)))))
      exec_summary_obj.focus = sorted(set(filter(None, (summarize_focus(tickets)))))
      exec_summary_obj.next_steps = sorted(set(filter(None, (summarize_next_steps(tickets)))))
      exec_summary_obj.risks = sorted(set(filter(None, (summarize_risks(tickets)))))

      exec_summary_obj.timeline = sorted(
         exec_summary_obj.timeline,
         key=lambda item: item.start_date,
         reverse=True
      )

      # Populate exec_summary_obj.links
      exec_summary_obj.links.add(f"<a href='https://dth01.ibmgcloud.net/jira/browse/{item['jira']}'>{item['jira']} - Master ticket</a>")
      exec_summary_obj.links.add(f"<a href='https://dth01.ibmgcloud.net/confluence/spaces/EGA/pages/{item['confluence']}'> Executive summary</a>")
      exec_summary_obj.links.add(f"<a href='{item['confluence_architecture']}'>Platform architecture</a>")

      #print (exec_summary_obj.name)
      update_confluence (item["confluence"], exec_summary_obj)



