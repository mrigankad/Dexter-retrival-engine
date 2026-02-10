import os
import subprocess
import sys

def run_command(command, description):
    print(f"--- {description} ---")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print(f"Warning/Error: {result.stderr}")
    except subprocess.CalledProcessError as e:
        print(f"Failed: {e}")
        print(f"Output: {e.output}")

def nuke():
    print("WARNING: This will delete ALL data from your databases!")
    input("Press Enter to continue or Ctrl+C to abort...")
    
    # 1. PostgreSQL
    run_command(
        'docker exec rag-postgres psql -U raguser -d ragdb -c "TRUNCATE chat_messages, chat_sessions, document_chunks, documents, evaluations, users RESTART IDENTITY CASCADE;"',
        "Clearing PostgreSQL Tables"
    )
    
    # 2. Qdrant
    run_command(
        'docker exec rag-qdrant curl -X DELETE http://localhost:6333/collections/documents',
        "Deleting Qdrant Collection 'documents'"
    )
    
    # 3. Neo4j
    run_command(
        'docker exec rag-neo4j cypher-shell -u neo4j -p password123 "MATCH (n) DETACH DELETE n"',
        "Deleting all Neo4j Nodes and Relationships"
    )
    
    # 4. Redis
    run_command(
        'docker exec rag-redis redis-cli FLUSHALL',
        "Flushing Redis Cache"
    )
    
    # 5. Local Uploads
    if os.path.exists('backend/uploads'):
        run_command(
            'powershell "Remove-Item -Path ./backend/uploads/* -Recurse -Force -ErrorAction SilentlyContinue"',
            "Cleaning Local Uploads Folder"
        )

    print("\n--- ALL DATABASES CLEARED ---")
    print("Re-running migrations/init if necessary...")
    run_command('docker-compose restart api ingestion-worker', "Restarting Workers to Re-initialize")

if __name__ == "__main__":
    nuke()
