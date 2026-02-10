import requests

print("Attempting to delete 'documents' collection from Qdrant @ localhost:6333...")
url = "http://localhost:6333/collections/documents"
try:
    response = requests.delete(url)
    if response.status_code == 200:
        print("Success! Collection deleted. It will be recreated with new vector size (2048) on API restart.")
    else:
        print(f"Server response: {response.status_code} - {response.text}")
except Exception as e:
    print(f"Error: {e}")
