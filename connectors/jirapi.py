import requests
import json


class JiraApi:
    def __init__(self, hostname, auth_token):
        self.hostname = hostname
        self.auth_token = auth_token
        self.session = requests.Session()
        self.session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}",
        }

    def search_by_filter(self, filter_id):
        url = f"{self.hostname}/rest/api/2/filter/{filter_id}"
        try:
            filter_response = self.session.get(url)
            filter_response.raise_for_status()
            filter_data = filter_response.json()
            if not filter_data.get("searchUrl"):
                raise Exception("Filter searchUrl not found.")
            filter_jql = filter_data["values"][0]["jql"]
            return self.search_issues(filter_jql)
        except requests.exceptions.RequestException as e:
            raise Exception(f"An error occurred during filter search: {e}")
        except (KeyError, IndexError) as e:
            raise Exception(f"Failed to parse filter data: {e}. Filter response: {filter_data}")


    def search_issues(
        self,
        jql,
        fields="key,summary,assignee,created,updated,resolved,status,description,priority,team,labels,components",
        max_results=5000,
    ):
        issue_search_endpoint = f"{self.hostname}/rest/api/2/search"
        issue_params = {"jql": jql, "fields": fields, "maxResults": max_results}
        try:
            issue_response = self.session.get(
                issue_search_endpoint, params=issue_params
            )
            issue_response.raise_for_status()
            return issue_response.json().get("issues", [])
        except requests.exceptions.RequestException as e:
            raise Exception(f"An error occurred during issue search: {e}")
        except json.JSONDecodeError:
            raise Exception(
                f"Failed to decode JSON. Response text was: {issue_response.text}"
            )

    def create_issue(self, project_key, summary, description, issue_type="Story"):
        create_issue_endpoint = f"{self.hostname}/rest/api/2/issue"
        data = {
            "fields": {
                "project": {"key": project_key},
                "summary": summary,
                "description": description, # Expects structured description from the tool
                "issuetype": {"name": issue_type},
            }
        }
        try:
            response = self.session.post(create_issue_endpoint, data=json.dumps(data))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_message = f"An error occurred during issue creation: {e}"
            try:
                error_details = response.json()
                error_message += f"\nResponse details: {json.dumps(error_details, indent=2)}"
            except (json.JSONDecodeError, UnboundLocalError):
                error_message += f"\nRaw response text: {response.text if 'response' in locals() else 'No response object'}"
            raise Exception(error_message)

    def update_issue(self, issue_key, fields):
        update_issue_endpoint = f"{self.hostname}/rest/api/2/issue/{issue_key}"
        data = {"fields": fields}
        try:
            response = self.session.put(update_issue_endpoint, data=json.dumps(data))
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            error_message = f"An error occurred during issue update: {e}"
            try:
                error_details = response.json()
                error_message += f"\nResponse details: {json.dumps(error_details, indent=2)}"
            except (json.JSONDecodeError, UnboundLocalError):
                error_message += f"\nRaw response text: {response.text if 'response' in locals() else 'No response object'}"
            raise Exception(error_message)

    def link_issues(self, inward_issue_key, outward_issue_key, link_type="Relates"):
        link_issue_endpoint = f"{self.hostname}/rest/api/2/issueLink"
        data = {
            "type": {"name": link_type},
            "inwardIssue": {"key": inward_issue_key},
            "outwardIssue": {"key": outward_issue_key},
        }
        try:
            response = self.session.post(link_issue_endpoint, data=json.dumps(data))
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            error_message = f"An error occurred during issue linking: {e}"
            try:
                error_details = response.json()
                error_message += f"\nResponse details: {json.dumps(error_details, indent=2)}"
            except (json.JSONDecodeError, UnboundLocalError):
                error_message += f"\nRaw response text: {response.text if 'response' in locals() else 'No response object'}"
            raise Exception(error_message)

    def add_comment(self, issue_key, comment_body):
        add_comment_endpoint = f"{self.hostname}/rest/api/2/issue/{issue_key}/comment"
        data = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment_body}],
                    }
                ],
            }
        }
        try:
            response = self.session.post(add_comment_endpoint, data=json.dumps(data))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            error_message = f"An error occurred during adding comment: {e}"
            try:
                error_details = response.json()
                error_message += f"\nResponse details: {json.dumps(error_details, indent=2)}"
            except (json.JSONDecodeError, UnboundLocalError):
                error_message += f"\nRaw response text: {response.text if 'response' in locals() else 'No response object'}"
            raise Exception(error_message)

    # New method for resolving issues
    def resolve_issue(self, issue_key: str, resolution_name: str = "Fixed"):
        """
        Resolves a Jira issue by transitioning it to a 'Resolved' state.
        Args:
            issue_key: The key of the issue to resolve (e.g., "PROJ-123").
            resolution_name: The name of the resolution to apply (e.g., "Fixed", "Done").
        Returns:
            True if the issue was resolved successfully, False otherwise.
        """
        # 1. Get available transitions for the issue
        transitions_url = f"{self.hostname}/rest/api/2/issue/{issue_key}/transitions"
        try:
            transitions_response = self.session.get(transitions_url)
            transitions_response.raise_for_status()
            transitions_data = transitions_response.json()
            available_transitions = transitions_data.get("transitions", [])

            # 2. Find the 'Resolve' transition
            resolve_transition_id = None
            # Search for common names that indicate resolution
            possible_resolve_names = ["resolve", "done", "fixed", "closed", "completed"]
            for transition in available_transitions:
                if transition["name"].lower() in possible_resolve_names:
                    resolve_transition_id = transition["id"]
                    # Store the exact name found for potential error reporting
                    found_transition_name = transition["name"]
                    break
            
            if not resolve_transition_id:
                available_names = [t['name'] for t in available_transitions]
                raise Exception(f"Could not find a suitable 'resolve' transition for issue {issue_key}. Available transitions: {available_names}")

            # 3. Perform the transition
            # Jira API requires a resolution field when resolving issues through transitions.
            transition_payload = {
                "transition": {"id": resolve_transition_id},
                "fields": {
                    "resolution": {"name": resolution_name}
                }
            }

            transition_endpoint = f"{self.hostname}/rest/api/2/issue/{issue_key}/transitions"
            response = self.session.post(transition_endpoint, data=json.dumps(transition_payload))
            response.raise_for_status()
            
            # A successful POST to the transitions endpoint usually returns 204 No Content, 
            # but the API might return JSON with the updated issue if not 204.
            # If raise_for_status() doesn't raise an exception, it's successful.
            return True

        except requests.exceptions.RequestException as e:
            error_message = f"An error occurred during issue resolution for {issue_key}: {e}"
            # Attempt to get more details from the response
            if 'response' in locals() and response is not None:
                try:
                    error_details = response.json()
                    error_message += f"\nResponse details: {json.dumps(error_details, indent=2)}"
                except json.JSONDecodeError:
                    error_message += f"\nRaw response text: {response.text}"
            raise Exception(error_message)
        except Exception as e: # Catch other potential errors like missing transition
            raise Exception(f"An unexpected error occurred during issue resolution for {issue_key}: {e}")