import zipfile
from pathlib import Path
from xml.etree import ElementTree

from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.storage import UPLOAD_DIR, get_db, utc_now
from backend.tools.config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
vectorstore = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embeddings,
    persist_directory=CHROMA_DIR,
)
text_splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=160)


def _docx_to_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def load_file(path: Path) -> list[Document]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        docs = PyPDFLoader(str(path)).load()
        for doc in docs:
            if "page" in doc.metadata:
                doc.metadata["page"] += 1
        return docs
    if suffix == ".docx":
        return [Document(page_content=_docx_to_text(path), metadata={"page": 1})]
    raise ValueError("Only PDF and DOCX files are supported")


def add_document(user_id: int, file_path: str, original_filename: str, content_type: str = "") -> dict:
    path = Path(file_path)
    documents = load_file(path)
    chunks = text_splitter.split_documents(documents)

    for chunk in chunks:
        chunk.metadata["source"] = original_filename
        chunk.metadata["user_id"] = str(user_id)

    existing = get_document_by_filename(user_id, original_filename)
    if existing:
        remove_document(user_id, original_filename, delete_file=False)

    if chunks:
        vectorstore.add_documents(chunks)

    with get_db() as db:
        db.execute(
            """
            INSERT INTO documents (user_id, filename, stored_name, content_type, pages, chunks, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, original_filename, path.name, content_type, len(documents), len(chunks), utc_now()),
        )

    return {"filename": original_filename, "pages": len(documents), "chunks": len(chunks)}


def get_document_by_filename(user_id: int, filename: str):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM documents WHERE user_id = ? AND filename = ?",
            (user_id, filename),
        ).fetchone()


def list_documents(user_id: int) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT id, filename, pages, chunks, uploaded_at FROM documents WHERE user_id = ? ORDER BY uploaded_at DESC",
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def remove_document(user_id: int, filename: str, delete_file: bool = True) -> dict:
    row = get_document_by_filename(user_id, filename)
    if not row:
        return {"deleted": False, "filename": filename}

    vectorstore.delete(where={"$and": [{"user_id": str(user_id)}, {"source": filename}]})

    with get_db() as db:
        db.execute("DELETE FROM documents WHERE user_id = ? AND filename = ?", (user_id, filename))

    if delete_file:
        path = UPLOAD_DIR / row["stored_name"]
        if path.exists():
            path.unlink()

    return {"deleted": True, "filename": filename}


def retrieve_for_user(user_id: int, query: str, k: int = 5) -> dict:
    docs = vectorstore.similarity_search(query, k=k, filter={"user_id": str(user_id)})
    return {
        "query": query,
        "results": [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "Unknown"),
                "page": doc.metadata.get("page", "Unknown"),
            }
            for doc in docs
        ],
    }


@tool
def search_knowledge_base(query: str) -> str:
    """Search the current user's uploaded knowledge base."""
    return "This tool must be bound to a logged-in user before use."
