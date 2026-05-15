from llama_cloud import LlamaCloud
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import sqlite3
import uuid
from typing import Optional, Tuple, List
import json
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel


from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
import os
import shutil
from pathlib import Path
from dotenv import load_dotenv

app = FastAPI(title="Resume Parser & Chatbot API")

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React default port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

load_dotenv()

llama_client = LlamaCloud(api_key=os.getenv("LLAMA_API"))
model_name = "sentence-transformers/all-MiniLM-L6-v2"
model_kwargs = {'device': 'mps'} # Use 'cuda' for GPU
encode_kwargs = {'normalize_embeddings': False}

embeddings = HuggingFaceEmbeddings(
    model_name=model_name,
    model_kwargs=model_kwargs,
    encode_kwargs=encode_kwargs
)
vectorstore = Chroma(
    collection_name="documents",
    embedding_function=embeddings,
    persist_directory="./documents"
)
retriever = vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={'k': 2}
            )
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME")

DB_PATH = "chat_memory.db"



# =========================
# SQLITE SETUP
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS conversations (
        chat_id TEXT PRIMARY KEY,
        history TEXT,
        resume  TEXT,
        role    TEXT,
        questions  TEXT,
        verdict TEXT DEFAULT '[]'
    )
    """)

    conn.commit()
    conn.close()


# init_db()

# =========================
# HELPERS
# =========================

def get_history(chat_id: str) -> List[dict]:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT history FROM conversations WHERE chat_id = ?",
        (chat_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row and row[0]:
        return json.loads(row[0])

    return []

def save_history(chat_id: str, history: List[dict]):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    history_json = json.dumps(history)

    cursor.execute("""
    INSERT INTO conversations (chat_id, history)
    VALUES (?, ?)
    ON CONFLICT(chat_id)
    DO UPDATE SET history = excluded.history
    """, (chat_id, history_json))

    conn.commit()
    conn.close()

def parse_resume(file_path:str,role:str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    chat_id = str(uuid.uuid4())
    
    print(f"Uploading to LlamaParse...")
    file = llama_client.files.create(file=str(file_path), purpose="parse")
    print(f"File ID: {file.id} — parsing...")
    result = llama_client.parsing.parse(
                file_id=file.id,
                tier="agentic",
                version="latest",
                expand=["markdown"],
            )
    
    full_markdown = ""
    if hasattr(result, "markdown"):
        if hasattr(result.markdown, "pages") and result.markdown.pages:
            for page in result.markdown.pages:
                full_markdown += (
                    page.markdown if hasattr(page, "markdown") else str(page)
                ) + "\n\n"
        elif hasattr(result.markdown, "content"):
            full_markdown = result.markdown.content
        elif isinstance(result.markdown, str):
            full_markdown = result.markdown
        else:
            full_markdown = str(result.markdown)
    elif hasattr(result, "content"):
        full_markdown = result.content
    else:
        full_markdown = str(result)

    cursor.execute("""
    INSERT INTO conversations (chat_id, resume)
    VALUES (?, ?)
    ON CONFLICT(chat_id)
    DO UPDATE SET resume = excluded.resume
    """, (chat_id, full_markdown))

    conn.commit()
    
    cursor.execute("""
    INSERT INTO conversations (chat_id, role)
    VALUES (?, ?)
    ON CONFLICT(chat_id)
    DO UPDATE SET role = excluded.role
    """, (chat_id, role))
    conn.commit()
    
    conn.close()

    generate_questions(chat_id,resume_content=full_markdown)

    return (chat_id,full_markdown)

def get_questions_resume(chat_id:str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT questions,resume,role FROM conversations WHERE chat_id = ?",
        (chat_id,)
    )

    row = cursor.fetchone()
    conn.close()

    if row and row[0]:
        return json.loads(row[0]),row[1], row[2]

    return []
        
def get_data_from_chroma(query:str):
    retriever = vectorstore.as_retriever(
                search_type="similarity",
                search_kwargs={'k': 2}
            )

    docs = retriever.invoke(query)
    response = "\n".join(doc.page_content for doc in docs)

    return response

class Verdict(BaseModel):
    verdict: int
    
def generate_verdict(question:str,answer:str, chat_id:str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name=MODEL_NAME,
        temperature=0.2
    ).with_structured_output(Verdict)
    messages = [
        SystemMessage(
            content=f"""
You are a Answer checker, you generate the marks of the candidate based on their answer on a scale of 10.
- Generate a single integer in a range 0-10.

Question:
{question}

Answer:
{answer}
"""
        )
    ]

    response = llm.invoke(messages)

    verdict = response.verdict
    
    cursor.execute(
        "SELECT verdict FROM conversations WHERE chat_id = ?",
        (chat_id,)
    )

    row = cursor.fetchone()
    
    if row and row[0]:
        arr = json.loads(row[0])
        arr.append(verdict)
        cursor.execute(
            "UPDATE conversations SET verdict = ? WHERE chat_id = ?",
            (json.dumps(arr),chat_id,)
        )
    conn.commit()
    conn.close()
        
    return
    
    

    
class KeywordList(BaseModel):
    keywords: List[str]
class QuestionsList(BaseModel):
    questions: List[str]
    
def generate_questions(chat_id: str, resume_content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name=MODEL_NAME,
        temperature=0.1
    ).with_structured_output(KeywordList)

    # Build message history
    messages = [
        SystemMessage(
            content=f"""
You are a keyword extraction engine.

Extract only the most important technical keywords from the candidate resume.

Rules:
- Return ONLY a valid Python list.
- Maximum 10 items.
- Use short keywords or tech phrases only.
- No numbering.
- No explanations.
- No sentences.
- Cover all the technologies, tools and skills mentioned.
- No duplicate technologies and tools.
- Prefer technologies, frameworks, tools, databases, languages, cloud, APIs.

Example output:
["react", "node.js", "mongodb", "express.js", "rest api"]

Candidate Resume:
{resume_content}
"""
        )
    ]

    response = llm.invoke(messages)

    keywords = response.keywords

    context = """"""

    for keyword in keywords:
        context+= f"Keyword: {keyword} \n Content: {get_data_from_chroma(keyword)}\n\n"
    
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name=MODEL_NAME,
        temperature=0.5
    ).with_structured_output(QuestionsList)

    # Build message history
    messages = [
        SystemMessage(
            content=f"""
You are a Questions Generator Bot.

Generate the questions from the information provided to you, to test the ability of a interviewing candidate. You have access to Candidate Resume and ground context on technologies, use that to generate questions. Cover all the skills of candidate.

Rules:
- Return ONLY a valid Python list.
- Maximum 10 items.
- Do not generate duplicate questions.
- No numbering.
- No explanations.
- No duplicate meanings.
- Generate varying questions on different technologies and tools, according to the context provided.
- Prefer technologies, frameworks, tools, databases, languages, cloud, APIs.

Candidate Resume:
{resume_content}

Content:
{context}
"""
        )
    ]

    response = llm.invoke(messages)

    questions = response.questions
    
    cursor.execute("""
    INSERT INTO conversations (chat_id, questions)
    VALUES (?, ?)
    ON CONFLICT(chat_id)
    DO UPDATE SET questions = excluded.questions
    """, (chat_id, json.dumps(questions)))

    conn.commit()
    conn.close()
    
    return questions
    


# =========================
# MAIN FUNCTION
# =========================

def chat(query: str, chat_id: Optional[str] = None) -> Tuple[str, str]:
    """
    Args:
        query (str): User query
        chat_id (str | None): Existing chat_id

    Returns:
        tuple:
            response (str)
            chat_id (str)
    """

    # Create new chat_id if not provided
    if not chat_id:
        chat_id = str(uuid.uuid4())

    questions,resume,role = get_questions_resume(chat_id)
    
    # Fetch history from DB
    history = get_history(chat_id)


    if history:
        generate_verdict(history[-1]['content'],query,chat_id)
    
    # Initialize LLM
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name=MODEL_NAME,
        temperature=0.7
    )

    # Build message history
    messages = [
        SystemMessage(
            content=f"""
            You are a Technical Interviewer, you have list of questions to ask the candidate. 
            - You have the conversation history, do not ask the same question from the list of questions previously asked in conversation.
            - Based on the candidates responses in conversation history you can tweak the questions little bit.
            - Make the interview interactive like a real interviewer. DO NOT praise the candidate, just 1 line of compliment at most.
            - End the interview when all the questions were asked.
            
            Candidate Resume:
            {resume}
            
            Role Applying For:
            {role}
            
            Questions:
            {questions}
            """
        )
    ]

    for msg in history:
        if msg["role"] == "user":
            messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            messages.append(AIMessage(content=msg["content"]))

    # Add latest user query
    messages.append(HumanMessage(content=query))

    # Generate response
    response = llm.invoke(messages)

    assistant_reply = response.content

    # Update history
    history.append({
        "role": "user",
        "content": query
    })

    history.append({
        "role": "assistant",
        "content": assistant_reply
    })

    # Save updated history
    save_history(chat_id, history)

    return assistant_reply, chat_id

class ParseResponse(BaseModel):
    success: bool
    chat_id: str
    markdown_content: str
    filename: str
    
@app.post("/parse-resume", response_model=ParseResponse)
async def upload_and_parse_resume(
    file: UploadFile = File(..., description="Resume file to parse (PDF)"),
    role: str = Form(...)
):
    """
    Upload a resume file and parse it to markdown format
    """
    # Validate file type
    allowed_extensions = {'.pdf'}
    file_extension = Path(file.filename).suffix.lower()
    
    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Create uploads directory if it doesn't exist
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    
    # Save uploaded file temporarily
    temp_file_path = upload_dir / file.filename
    
    try:
        # Save the uploaded file
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Call your resume parsing function
        chat_id, markdown_content = parse_resume(temp_file_path,role)
        
        
        return ParseResponse(
            success=True,
            chat_id = chat_id,
            markdown_content=markdown_content,
            filename=file.filename
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing resume: {str(e)}")
    
    finally:
        # Clean up temporary file
        if temp_file_path.exists():
            temp_file_path.unlink()

class ChatRequest(BaseModel):
    chat_id: str
    query: str

class ChatResponse(BaseModel):
    response: str
    chat_id: str

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(chat_request: ChatRequest):
    """
    Generate chatbot response based on chat_id and query
    """
    if not chat_request.query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
    
    if not chat_request.chat_id:
        raise HTTPException(status_code=400, detail="chat_id is required")
    
    try:
        # Call your chatbot function
        response_text,chat_id = chat(
            chat_id=chat_request.chat_id,
            query=chat_request.query
        )
        
        return ChatResponse(
            response=response_text,
            chat_id=chat_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating response: {str(e)}")

class SessionResponse(BaseModel):
    chat_id: str
    role: str
    history: List[dict]
 
@app.get("/session/{chat_id}", response_model=SessionResponse)
async def get_session(chat_id: str):
    """
    Fetch session metadata + full chat history for a given chat_id.
    Used by the frontend to restore state after a page refresh.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
 
    cursor.execute(
        "SELECT role, history FROM conversations WHERE chat_id = ?",
        (chat_id,)
    )
    row = cursor.fetchone()
    conn.close()
 
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
 
    role, history_json = row
    history = json.loads(history_json) if history_json else []
 
    return SessionResponse(
        chat_id=chat_id,
        role=role or "",
        history=history
    )

init_db()