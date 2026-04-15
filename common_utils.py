"""
Common utilities for agentic-pm project.
Provides shared functionality for database connections, Vault secrets, API clients, and agents.
"""
import os
import logging
import hvac
import psycopg2
from typing import Dict, Any, Optional
from dotenv import load_dotenv
from connectors.confluenceapi import ConfluenceApi
from connectors.jirapi import JiraApi
from jinja2 import Environment, FileSystemLoader
from strands import Agent
from strands.models.ollama import OllamaModel

# Configure logging
logger = logging.getLogger(__name__)

# Constants
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_MODEL = "granite4"
OLLAMA_TEMPERATURE = 0
OLLAMA_MAX_TOKENS = 4096

# Jinja2 environment
jinja_env = Environment(loader=FileSystemLoader('templates'))


class ConfigManager:
    """Manages configuration from Vault and environment variables."""
    
    def __init__(self):
        """Initialize configuration manager and load environment variables."""
        load_dotenv()
        self._vault_client = None
        self._db_config = None
        self._jira_config = None
        self._confluence_config = None
        self._llm_config = None
        
    def _get_vault_client(self) -> hvac.Client:
        """Get or create Vault client."""
        if self._vault_client is None:
            logger.info("Initializing Vault client")
            self._vault_client = hvac.Client(url=os.getenv('VAULT_URL'))
            self._vault_client.auth.approle.login(
                role_id=os.getenv('VAULT_ROLE_ID'),
                secret_id=os.getenv('VAULT_SECRET_ID'),
            )
            logger.info("Successfully authenticated with Vault")
        return self._vault_client
    
    def get_db_config(self) -> Dict[str, str]:
        """Get database configuration from Vault."""
        if self._db_config is None:
            logger.info("Loading database configuration from Vault")
            client = self._get_vault_client()
            db_secret = client.secrets.kv.read_secret_version(path='secret/cmdb')
            self._db_config = {
                'dbname': db_secret['data']['data']['psql_db'],
                'user': db_secret['data']['data']['psql_user'],
                'password': db_secret['data']['data']['psql_pw'],
                'host': db_secret['data']['data']['psql_host'],
                'port': db_secret['data']['data']['psql_port'],
            }
            logger.info("Database configuration loaded successfully")
        return self._db_config
    
    def get_jira_config(self) -> Dict[str, str]:
        """Get Jira configuration from Vault."""
        if self._jira_config is None:
            logger.info("Loading Jira configuration from Vault")
            client = self._get_vault_client()
            jira_secret = client.secrets.kv.read_secret_version(path='secret/jira')
            self._jira_config = {
                'url': jira_secret['data']['data']['url'],
                'token': jira_secret['data']['data']['token'],
            }
            logger.info("Jira configuration loaded successfully")
        return self._jira_config
    
    def get_confluence_config(self) -> Dict[str, str]:
        """Get Confluence configuration from Vault."""
        if self._confluence_config is None:
            logger.info("Loading Confluence configuration from Vault")
            client = self._get_vault_client()
            confluence_secret = client.secrets.kv.read_secret_version(path='secret/confluence')
            self._confluence_config = {
                'url': confluence_secret['data']['data']['url'],
                'token': confluence_secret['data']['data']['token'],
            }
            logger.info("Confluence configuration loaded successfully")
        return self._confluence_config
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration from Vault."""
        if self._llm_config is None:
            logger.info("Loading LLM configuration from Vault")
            client = self._get_vault_client()
            self._llm_config = client.secrets.kv.read_secret_version(path='secret/llm')
            logger.info("LLM configuration loaded successfully")
        return self._llm_config


class DatabaseManager:
    """Manages database connections and operations."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize database manager with configuration."""
        self.config = config_manager.get_db_config()
        logger.info("Database manager initialized")
    
    def get_connection(self):
        """Get a database connection."""
        logger.debug("Creating database connection")
        return psycopg2.connect(**self.config)
    
    def execute_query(self, query: str, params: tuple = None, fetch: bool = True):
        """Execute a database query."""
        logger.debug(f"Executing query: {query[:100]}...")
        with self.get_connection() as conn:
            conn.set_session(autocommit=True)
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                if fetch:
                    return cursor.fetchall()
                return None


class APIClientManager:
    """Manages API clients for Jira and Confluence."""
    
    def __init__(self, config_manager: ConfigManager):
        """Initialize API client manager with configuration."""
        self.config_manager = config_manager
        self._jira_api = None
        self._confluence_api = None
        logger.info("API client manager initialized")
    
    def get_jira_api(self) -> JiraApi:
        """Get or create Jira API client."""
        if self._jira_api is None:
            logger.info("Initializing Jira API client")
            config = self.config_manager.get_jira_config()
            self._jira_api = JiraApi(
                hostname=config['url'],
                auth_token=config['token']
            )
            logger.info("Jira API client initialized successfully")
        return self._jira_api
    
    def get_confluence_api(self) -> ConfluenceApi:
        """Get or create Confluence API client."""
        if self._confluence_api is None:
            logger.info("Initializing Confluence API client")
            config = self.config_manager.get_confluence_config()
            self._confluence_api = ConfluenceApi(
                hostname=config['url'],
                auth_token=config['token']
            )
            logger.info("Confluence API client initialized successfully")
        return self._confluence_api


class AgentFactory:
    """Factory for creating AI agents."""
    
    @staticmethod
    def create_ollama_model(
        model_id: str = OLLAMA_MODEL,
        host: str = OLLAMA_HOST,
        temperature: float = OLLAMA_TEMPERATURE,
        max_tokens: Optional[int] = None
    ) -> OllamaModel:
        """Create an Ollama model instance."""
        logger.debug(f"Creating Ollama model: {model_id}")
        kwargs = {
            'model_id': model_id,
            'host': host,
            'temperature': temperature,
        }
        if max_tokens is not None:
            kwargs['max_tokens'] = max_tokens
        return OllamaModel(**kwargs)
    
    @staticmethod
    def create_scrum_agent(
        model: Optional[OllamaModel] = None,
        tools: list = None,
        hooks: list = None
    ) -> Agent:
        """Create a scrum master agent."""
        logger.debug("Creating scrum agent")
        if model is None:
            model = AgentFactory.create_ollama_model()
        
        kwargs = {
            'model': model,
            'system_prompt': """
                You are scrum master managing project team for which you need to report various information from Jira backlog to project manager. Your project is agile project with 2 weeks sprints and follows the standard flow of design, architecture,build and so on.
            """
        }
        if tools:
            kwargs['tools'] = tools
        if hooks:
            kwargs['hooks'] = hooks
            
        return Agent(**kwargs)
    
    @staticmethod
    def create_pm_agent(
        model: Optional[OllamaModel] = None,
        tools: list = None
    ) -> Agent:
        """Create a project manager agent."""
        logger.debug("Creating PM agent")
        if model is None:
            model = AgentFactory.create_ollama_model()
        
        kwargs = {
            'model': model,
            'system_prompt': """
                You are project manager who has to report executive summaries about project status to management board. Your project is agile project with 2 weeks sprints and follows the standard flow of design, architecture,build and so on. You get information from scrum master which you have to transform to high level summary for final report.
            """
        }
        if tools:
            kwargs['tools'] = tools
            
        return Agent(**kwargs)


def setup_logging(name: str, level: int = logging.DEBUG) -> logging.Logger:
    """Setup logging for a module."""
    log = logging.getLogger(name)
    log.setLevel(level)
    
    # Only add handler if none exists
    if not log.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        log.addHandler(handler)
    
    return log