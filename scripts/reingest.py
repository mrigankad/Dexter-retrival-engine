import requests
import os
import sys

API_BASE = "http://localhost:8000"
FILE_PATH = "Test1.pdf"
LOGIN_URL = f"{API_BASE}/auth/login"
INGEST_URL = f"{API_BASE}/ingest"

# Correct credentials from init_db.sql
USERNAME = "admin"
PASSWORD = "admin123"

def get_token():
    print(f"Attempting login as '{USERNAME}'...")
    try:
        # The API expects JSON body
        resp = requests.post(LOGIN_URL, json={"username": USERNAME, "password": PASSWORD})
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            print(f"Login failed: {resp.status_code} - {resp.text}")
            return None
    except Exception as e:
        print(f"Connection error: {e}")
        return None

token = get_token()
if not token:
    print("Could not authenticate. Cannot ingest file.")
    sys.exit(1)

if not os.path.exists(FILE_PATH):
    print(f"Error: {FILE_PATH} not found.")
    sys.exit(1)

print(f"Authenticated! Uploading {FILE_PATH}...")
with open(FILE_PATH, "rb") as f:
    files = {"file": (FILE_PATH, f, "application/pdf")}
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(INGEST_URL, files=files, headers=headers) 

if response.status_code == 200:
    print("Success! Document ingested.")
    print(response.json())
else:
    print(f"Error: {response.status_code} - {response.text}")
