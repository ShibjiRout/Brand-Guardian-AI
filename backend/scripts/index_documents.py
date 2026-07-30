import os
import sys
import logging
from typing import List
from dotenv import load_dotenv

load_dotenv(override=True)

# Document Loaders and Splitters
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Azure Vector Store & Embeddings
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

# 1. Setup Logging & Configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("indexer")


def clear_rules() -> dict:
    """Delete all documents from the Azure AI Search index."""
    endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    api_key = os.getenv("AZURE_SEARCH_API_KEY")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")

    client = SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(api_key)
    )

    results = list(client.search(search_text="*", select=["id"], top=1000))
    docs_to_delete = [{"id": r["id"]} for r in results]

    if not docs_to_delete:
        logger.info("Index is already empty.")
        return {"deleted": 0}

    client.delete_documents(documents=docs_to_delete)
    logger.info(f"Deleted {len(docs_to_delete)} documents from index.")
    return {"deleted": len(docs_to_delete)}


def index_docs(pdf_path: str) -> int:
    """
    Takes a single PDF path, chunks it, and uploads vectors to Azure AI Search.
    This is the same input a server.py upload endpoint would hand it: a path
    to a PDF already saved on disk.

    Returns the number of chunks indexed (0 if nothing was indexed).
    """
    # 2. Validate the Given Path
    if not os.path.isfile(pdf_path):
        logger.error(f"File not found: {pdf_path}")
        return 0

    if not pdf_path.lower().endswith(".pdf"):
        logger.error(f"Not a PDF file: {pdf_path}")
        return 0

    # 3. Debug: Check Environment Variables
    logger.info("=" * 60)
    logger.info("Environment Configuration Check:")
    logger.info(f"AZURE_SEARCH_ENDPOINT: {os.getenv('AZURE_SEARCH_ENDPOINT')}")
    logger.info(f"AZURE_SEARCH_INDEX_NAME: {os.getenv('AZURE_SEARCH_INDEX_NAME')}")
    logger.info("=" * 60)

    # 4. Validate Required Environment Variables
    required_vars = [
        "OPENAI_API_KEY",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_API_KEY",
        "AZURE_SEARCH_INDEX_NAME"
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        logger.error("Please check your .env file and ensure all variables are set.")
        return 0

    # 5. Initialize Embedding Model (The "Translator")
    # This turns text into numbers (vectors).
    try:
        logger.info("Initializing OpenAI Embeddings...")
        embeddings = OpenAIEmbeddings(
            model="text-embedding-3-small",
            api_key=os.getenv("OPENAI_API_KEY")
        )
        logger.info("✓ Embeddings model initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize embeddings: {e}")
        return 0

    # 6. Initialize Azure Search (The Database)
    try:
        logger.info("Initializing Azure AI Search vector store...")
        index_name = os.getenv("AZURE_SEARCH_INDEX_NAME")
        vector_store = AzureSearch(
            azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
            azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
            index_name=index_name,
            embedding_function=embeddings.embed_query
        )
        logger.info(f"✓ Vector store initialized for index: {index_name}")
    except Exception as e:
        logger.error(f"Failed to initialize Azure Search: {e}")
        logger.error("Please verify your Azure Search endpoint, API key, and index name.")
        return 0

    # 7. Load the PDF
    filename = os.path.basename(pdf_path)
    logger.info(f"Loading: {filename}...")

    try:
        loader = PyPDFLoader(pdf_path)
        raw_docs = loader.load()

        # 8. Chunking Strategy
        # We split text into 1000-character chunks with 200-character overlap
        # to ensure context isn't lost between cuts.
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        splits = text_splitter.split_documents(raw_docs)

        # Tag the source for citation later
        for split in splits:
            split.metadata["source"] = filename

        logger.info(f" -> Split into {len(splits)} chunks.")

    except Exception as e:
        logger.error(f"Failed to process {filename}: {e}")
        return 0

    if not splits:
        logger.warning(f"No content extracted from {filename}.")
        return 0

    # 9. Upload to Azure
    logger.info(f"Uploading {len(splits)} chunks to Azure AI Search Index '{index_name}'...")
    try:
        vector_store.add_documents(documents=splits)
        logger.info("=" * 60)
        logger.info("✅ Indexing Complete! The Knowledge Base is ready.")
        logger.info(f"Total chunks indexed: {len(splits)}")
        logger.info("=" * 60)
        return len(splits)
    except Exception as e:
        logger.error(f"Failed to upload documents to Azure Search: {e}")
        logger.error("Please check your Azure Search configuration and try again.")
        return 0


def index_pdf_files(file_paths: List[str]) -> dict:
    """
    Indexes multiple PDF files by calling index_docs() on each one.
    Returns files_processed and chunks_indexed, matching the shape
    server.py's /upload-rules endpoint expects.
    """
    total_chunks = 0
    for pdf_path in file_paths:
        total_chunks += index_docs(pdf_path)

    return {
        "files_processed": len(file_paths),
        "chunks_indexed": total_chunks
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python backend/scripts/index_documents.py <path-to-pdf>")
        sys.exit(1)
    index_docs(sys.argv[1])
