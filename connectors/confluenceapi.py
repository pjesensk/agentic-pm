import requests
import json


class ConfluenceApi:
    def __init__(self, hostname, auth_token):
        self.hostname = hostname
        self.auth_token = auth_token
        self.session = requests.Session()
        self.session.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}",
        }

    def get_spaces(self):
        response = self.session.get(f"{self.hostname}/rest/api/space")
        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Error fetching api spec: {response.status_code}")

    def update_page(self, page_id, new_content):
        url = f"{self.hostname}/rest/api/content/{page_id}"
        # read actual page
        response = self.session.get(url)
        if response.status_code == 200:
            old_content = response.json()
            # construct new content
            data = {
                "id": old_content["id"],
                "type": "page",
                "title": old_content["title"],
                "space": old_content["space"],
                "body": {
                    "storage": {
                        "value": new_content,
                        "representation": "storage",
                    }
                },
                "version": {"number": old_content["version"]["number"] + 1},
            }
            r = self.session.put(url=url, data=json.dumps(data))
            print(r.json())
        else:
            raise Exception(f"Error getting old page: {response.status_code}")
