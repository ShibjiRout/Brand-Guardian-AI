import json
import os
import logging
import re  # <--- Added Regex for cleaning
from typing import Dict, Any, List

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import AzureSearch
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

# Import the State schema .
from backend.src.graph.state import VideoAuditState, ComplianceIssue

# Import the Service
from backend.src.services.video_indexer import VideoIndexerService

# Configure Logger
logger = logging.getLogger("brand-guardian")
logging.basicConfig(level=logging.INFO)

# --- NODE 1: THE INDEXER ---
def index_video_node(state: VideoAuditState) -> Dict[str, Any]:
    """
    Downloads YouTube video, uploads to Azure VI, and extracts insights.
    """
    video_url = state.get("video_url")
    video_id_input = state.get("video_id", "vid_demo")
    
    logger.info(f"--- [Node: Indexer] Processing: {video_url} ---")
    
    video_file_path = state.get("video_file_path")  # set by Option 2 (manual upload)
    local_filename = "temp_audit_video.mp4"
    cleanup_local = False

    try:
        vi_service = VideoIndexerService()

        if video_file_path:
            # --- OPTION 2: Manual upload — use user-provided title/description (no yt-dlp) ---
            logger.info(f"[Option 2] Using pre-uploaded file: {video_file_path}")
            local_path = video_file_path
            yt_metadata = {
                "title": state.get("video_title", ""),
                "description": state.get("video_description", ""),
                "platform": "youtube",
            }
        else:
            # --- OPTION 1: Auto-download from YouTube ---
            logger.info("[Option 1] Downloading from YouTube...")
            if not (video_url and ("youtube.com" in video_url or "youtu.be" in video_url)):
                raise Exception("Please provide a valid YouTube URL.")
            local_path = vi_service.download_youtube_video(video_url, output_path=local_filename)
            yt_metadata = vi_service.get_youtube_metadata(video_url)
            cleanup_local = True

        # UPLOAD to Azure Video Indexer
        azure_video_id = vi_service.upload_video(local_path, video_name=video_id_input)
        logger.info(f"Upload Success. Azure ID: {azure_video_id}")

        # CLEANUP downloaded file (only for Option 1)
        if cleanup_local and os.path.exists(local_path):
            os.remove(local_path)

        # WAIT for processing
        raw_insights = vi_service.wait_for_processing(azure_video_id)

        # EXTRACT transcript/OCR
        clean_data = vi_service.extract_data(raw_insights)

        # Merge yt_metadata into video_metadata
        clean_data["video_metadata"] = {**clean_data.get("video_metadata", {}), **yt_metadata}

        logger.info("--- [Node: Indexer] Extraction Complete ---")
        return clean_data

    except Exception as e:
        logger.error(f"Video Indexer Failed: {e}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL",
            "transcript": "",
            "ocr_text": []
        }

# --- NODE 2: THE COMPLIANCE AUDITOR ---
def audit_content_node(state: VideoAuditState) -> Dict[str, Any]:
    """
    Performs Retrieval-Augmented Generation (RAG) to audit the content.
    """
    logger.info("--- [Node: Auditor] querying Knowledge Base & LLM ---")
    
    transcript = state.get("transcript", "")
    
    if not transcript:
        logger.warning("No transcript available. Skipping Audit.")
        return {
            "final_status": "FAIL",
            "final_report": "Audit skipped because video processing failed (No Transcript)."
        }

    # Initialize Clients
    llm = ChatOpenAI(
        model="gpt-4o",
        api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.0
    )

    embeddings = OpenAIEmbeddings(
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY")
    )

    vector_store = AzureSearch(
        azure_search_endpoint=os.getenv("AZURE_SEARCH_ENDPOINT"),
        azure_search_key=os.getenv("AZURE_SEARCH_API_KEY"),
        index_name=os.getenv("AZURE_SEARCH_INDEX_NAME"),
        embedding_function=embeddings.embed_query
    )
    
    # RAG Retrieval
    ocr_text = state.get("ocr_text", [])
    query_text = f"{transcript} {' '.join(ocr_text)}"
    docs = vector_store.similarity_search(query_text, k=3)
    
    retrieved_rules = "\n\n".join([doc.page_content for doc in docs])
    
    system_prompt = f"""
You are a Senior Brand Compliance Auditor. Your job is to identify GENUINE violations — not theoretical risks.

RETRIEVED COMPLIANCE RULES (from the regulatory knowledge base):
{retrieved_rules}

━━━ CRITICAL INTERPRETATION GUIDELINES ━━━

1. READ FULL CONTEXT FIRST
   Before flagging anything, read the entire transcript and OCR as a whole. A claim that appears problematic in isolation may be fully qualified elsewhere in the same ad.

2. PUFFERY IS NOT A VIOLATION (Rule 3.2 equivalent)
   Brand slogans, taglines, and obvious exaggerations that a reasonable consumer would not take literally are puffery — not objective claims. Examples: "Beauty to a Science", "The best you'll ever feel", "Nothing works better". Do NOT flag these as misleading claims.

3. SUBSTANTIATION RULES ARE REQUIREMENTS ON THE ADVERTISER, NOT PROHIBITIONS ON CLAIMS
   If a rule states "claims must be supported by evidence", this means the advertiser must HOLD evidence — it does NOT mean the claim itself is a violation. Only flag if the ad makes a claim that is objectively false or unsubstantiated based on what is stated in the transcript/OCR. Do not flag a claim just because you cannot see the supporting data.

4. COMPOSITION vs APPLICATION (e.g., CAP Rule 12.22 equivalent)
   Only flag if the ad fails to distinguish between what an ingredient/formula does versus how to apply the product. If the voiceover or on-screen text explicitly attributes an effect to the formula, ingredient, or active component — the rule is satisfied. Do not flag.

5. ONLY FLAG CLEAR VIOLATIONS WITH TRANSCRIPT EVIDENCE
   Every violation you raise must be backed by a specific quote or phrase from the transcript or OCR. Do not infer violations from what the ad "might imply". If you cannot cite the exact line, do not flag it.

6. SEVERITY DEFINITIONS
   - CRITICAL: Clear, specific rule breach with direct transcript evidence (e.g., a prohibited absolute guarantee, a missing mandatory disclosure)
   - WARNING: Potential issue that may need legal review but is not a clear-cut breach

━━━ OUTPUT FORMAT (strict JSON only, no markdown) ━━━

{{
    "compliance_results": [
        {{
            "category": "<rule category>",
            "severity": "CRITICAL or WARNING",
            "description": "Specific violation with exact quote from transcript/OCR and the rule it breaches"
        }}
    ],
    "status": "PASS or FAIL",
    "final_report": "Plain-English summary of findings. If PASS, explain why the ad is compliant."
}}

If no genuine violations are found, set "status" to "PASS" and "compliance_results" to [].
"""

    user_message = f"""
    VIDEO METADATA: {state.get('video_metadata', {})}
    TRANSCRIPT: {transcript}
    ON-SCREEN TEXT (OCR): {ocr_text}
    """

    try:
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ])
        
        # --- FIX: Clean Markdown if present (```json ... ```) ---
        content = response.content
        if "```" in content:
            # Regex to find JSON inside code blocks
            content = re.search(r"```(?:json)?(.*?)```", content, re.DOTALL).group(1)
            
        audit_data = json.loads(content.strip())
        
        return {
            "compliance_results": audit_data.get("compliance_results", []),
            "final_status": audit_data.get("status", "FAIL"),
            "final_report": audit_data.get("final_report", "No report generated.")
        }

    except Exception as e:
        logger.error(f"System Error in Auditor Node: {str(e)}")
        # Log the raw response to see what went wrong
        logger.error(f"Raw LLM Response: {response.content if 'response' in locals() else 'None'}")
        return {
            "errors": [str(e)],
            "final_status": "FAIL"
        }