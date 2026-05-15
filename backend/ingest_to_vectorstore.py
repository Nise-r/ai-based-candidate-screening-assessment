import argparse
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


def load_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def build_vectorstore():
    model_name = "sentence-transformers/all-MiniLM-L6-v2"
    model_kwargs = {"device": "mps"}  # change to "cuda" or "cpu" if needed
    encode_kwargs = {"normalize_embeddings": False}

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

    return vectorstore


def chunk_text(content: str, source: str):
    document = Document(
        page_content=content,
        metadata={"source": source}
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n## ", "\n### ", "\n", " ", ""]
    )

    return text_splitter.split_documents([document])


def main(file_path: str, source: str):
    print(f"Loading file: {file_path}")

    content = load_file(file_path)

    print("Building vectorstore...")
    vectorstore = build_vectorstore()

    print("Chunking document...")
    chunked_docs = chunk_text(content, source)

    print(f"Adding {len(chunked_docs)} chunks to vectorstore...")
    vectorstore.add_documents(documents=chunked_docs)

    print("Done. Data stored successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest text file into Chroma vectorstore")

    parser.add_argument(
        "--file",
        required=True,
        help="Path to the .txt file"
    )

    parser.add_argument(
        "--source",
        required=True,
        help='Metadata source (e.g. "Python basics notes, file from tutorial")'
    )

    args = parser.parse_args()

    main(args.file, args.source)