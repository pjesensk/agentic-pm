import os
import re
import logging
import hvac
import json
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
WATSONX_URL=llm_secret['data']['data']['WATSONX_URL']
WATSONX_APIKEY=llm_secret['data']['data']['WATSONX_APIKEY']
WATSONX_PROJECT_ID=llm_secret['data']['data']['WATSONX_PROJECT_ID']

os.environ["WATSONX_URL"] = WATSONX_URL
os.environ["WATSONX_APIKEY"] = WATSONX_APIKEY
os.environ["WATSONX_PROJECT_ID"] = WATSONX_PROJECT_ID

jira_secret = client.secrets.kv.read_secret_version(path='secret/jira')
confluence_secret = client.secrets.kv.read_secret_version(path='secret/confluence')

jira_api = JiraApi(hostname=jira_secret['data']['data']['url'], auth_token=jira_secret['data']['data']['token'])
confluence_api = ConfluenceApi(hostname=confluence_secret['data']['data']['url'], auth_token=confluence_secret['data']['data']['token'])
   
jinja_env = Environment(loader=FileSystemLoader('templates'))
exec_template = jinja_env.get_template('exec_summary.html.j2')

if __name__ == "__main__":
    jira_api.create_issue('DSO', 'Test agents manipulation', 'This ticket is used to test agent manipulation of issues', 'Task')