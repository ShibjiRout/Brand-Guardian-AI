import os
import logging
from typing import List

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

logger = logging.getLogger("rule-indexer")


def _get_vector_store() -> AzureSearch:
    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY")
    )
    return AzureSearch(
        azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        embedding_function=embeddings.embed_query
    )


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


def index_pdf_files(file_paths: List[str]) -> dict:
    """
    Chunk, embed, and upsert PDF files into Azure AI Search.
    Returns files_processed and chunks_indexed.
    """
    vector_store = _get_vector_store()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )

    all_splits = []

    for pdf_path in file_paths:
        filename = os.path.basename(pdf_path)
        try:
            logger.info(f"Loading PDF: {filename}")
            loader = PyPDFLoader(pdf_path)
            raw_docs = loader.load()
            splits = text_splitter.split_documents(raw_docs)
            for split in splits:
                split.metadata["source"] = filename
            all_splits.extend(splits)
            logger.info(f"{filename} -> {len(splits)} chunks")
        except Exception as e:
            logger.error(f"Failed to process {filename}: {e}")
            raise Exception(f"Failed to process {filename}: {str(e)}")

    if not all_splits:
        raise Exception("No content could be extracted from the uploaded PDFs.")

    logger.info(f"Uploading {len(all_splits)} chunks to Azure AI Search...")
    vector_store.add_documents(documents=all_splits)
    logger.info("Indexing complete.")

    return {
        "files_processed": len(file_paths),
        "chunks_indexed": len(all_splits)
    }