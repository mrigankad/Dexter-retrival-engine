import requests
import time
import sys

API_BASE = "http://localhost:8000"
LOGIN_URL = f"{API_BASE}/auth/login"
DOC_ID = sys.argv[1] if len(sys.argv) > 1 else ""

USERNAME = "admin"
PASSWORD = "admin123"

def get_token():
    try:
        resp = requests.post(LOGIN_URL, json={"username": USERNAME, "password": PASSWORD})
        if resp.status_code == 200:
            return resp.json().get("access_token")
        else:
            return None
    except:
        return None

if not DOC_ID:
    print("Usage: python check_status.py <document_id>")
    sys.exit(1)

token = get_token()
if not token:
    print("Auth failed.")
    sys.exit(1)

STATUS_URL = f"{API_BASE}/documents/{DOC_ID}"
headers = {"Authorization": f"Bearer {token}"}

print(f"Monitoring document {DOC_ID}...")
while True:
    try:
        resp = requests.get(STATUS_URL, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status")
            graph_triplets = data.get("doc_metadata", {}).get("graph_triplets", 0)
            print(f"Status: {status} | Chunks: {data.get('chunks_count')} | Graph Triplets: {graph_triplets}")
            
            if status == "completed":
                print("\nIngestion and Graph Extraction COMPLETE! 🎉")
                break
            elif status == "failed":
                print(f"\nFailed: {data.get('error_message')}")
                break
        else:
            print(f"Error {resp.status_code}")
            break
        time.sleep(3)
    except Exception as e:
        print(f"Error: {e}")
        break
