import os
from dotenv import load_dotenv
from langchain_nvidia_ai_endpoints import NVIDIAEmbeddings

load_dotenv(".env")
api_key = os.getenv("NVIDIA_API_KEY")

if not api_key:
    with open(".env", "r") as f:
        for line in f:
            if line.startswith("NVIDIA_API_KEY="):
                api_key = line.split("=", 1)[1].strip()
                break

client = NVIDIAEmbeddings(
  model="nvidia/llama-nemotron-embed-vl-1b-v2",
  api_key=api_key,
  truncate="NONE",
)

embedding = client.embed_query("test dimension")
print(f"Embedding Dimension: {len(embedding)}")
