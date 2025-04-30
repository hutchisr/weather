import requests
import json
import os

response = requests.get(
  url="https://openrouter.ai/api/v1/auth/key",
  headers={
    "Authorization": f"Bearer {os.getenv("OPENROUTER_API_KEY")}"
  }
)

print(json.dumps(response.json(), indent=2))
