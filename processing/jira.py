import json
import torch
from transformers import AutoModel, AutoTokenizer

class JiraEmbeddings():
    def __init__(self):
        self.model_path = "ibm-granite/granite-embedding-30m-english"
        self.model = AutoModel.from_pretrained(self.model_path)
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
        self.model.eval()

    def load_jira_embeddings(self, issue):
        tokenized_queries = self.tokenizer(json.dumps(issue), padding=True, truncation=True, return_tensors='pt')
        with torch.no_grad():
            model_output = self.model(**tokenized_queries)
            query_embeddings = model_output[0][:, 0]
            query_embeddings = torch.nn.functional.normalize(query_embeddings, dim=1)

        metadata = {
            'key': issue['key'],
        }
        
        return {
            'key': issue['key'],
            'embedding': query_embeddings,
            'metadata': metadata
        }