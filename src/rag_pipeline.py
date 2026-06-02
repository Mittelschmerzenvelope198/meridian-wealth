# Document loading, embedding, and FAISS vector store management
import os
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
from src.config import CONFIG

def get_or_build_vectorstore():
    """Loads or builds the vector store structure exactly mirroring the notebook processing pipeline."""
    vector_db_dir = CONFIG['paths']['vector_db_dir']
    policy_dir = CONFIG['paths']['policy_documents_dir']
    db_name = CONFIG['rag']['retriever']['vector_db_name']
    embedding_model = OpenAIEmbeddings(model=CONFIG['embeddings']['model_name'])
    
    # Persistent file tracking mapping the index name
    if os.path.exists(os.path.join(vector_db_dir, f"{db_name}.faiss")):
        return FAISS.load_local(
            vector_db_dir, 
            embedding_model, 
            index_name=db_name,
            allow_dangerous_deserialization=True
        )
    
    # Step 1: Load all PDFs using LangChain's PyPDFLoader
    all_pages = []
    pdf_files = sorted([f for f in os.listdir(policy_dir) if f.endswith(".pdf")])

    for pdf_file in pdf_files:
        loader = PyPDFLoader(os.path.join(policy_dir, pdf_file))
        pages = loader.load()
        all_pages.extend(pages)

    # Step 2: Split into chunks
    splitter_cfg = CONFIG['rag']['text_splitter']
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=splitter_cfg['chunk_size'],
        chunk_overlap=splitter_cfg['chunk_overlap'],
        length_function=len
    )

    chunks = text_splitter.split_documents(all_pages)

    # Step 3 & 4: Embed and build FAISS vector store
    vectorstore = FAISS.from_documents(chunks, embedding_model)
    vectorstore.save_local(vector_db_dir, index_name=db_name)
    
    return vectorstore

policy_vectorstore = get_or_build_vectorstore()
policy_retriever_chain = policy_vectorstore.as_retriever(
    search_kwargs={"k": CONFIG['rag']['retriever']['k_results']}
)