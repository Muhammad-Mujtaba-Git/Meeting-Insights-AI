import os 
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.documents import Document
from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder

class VectorStore:
    def __init__(self, top_n: int = 4):
        self.chroma_dir = "vector_db"
        self.collection_name = "meeting_transcript"
        
        self.embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-large-en-v1.5",
            model_kwargs={'device': 'cuda'}, 
            encode_kwargs={'normalize_embeddings': True} 
        )
        
        self.splitter = SemanticChunker(
            self.embeddings, 
            breakpoint_threshold_type="percentile"
        )
        
       
        self.reranker_model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
        self.compressor = CrossEncoderReranker(model=self.reranker_model, top_n=top_n)

    def split_transcript(self, transcript: str) -> list:
        """Splits a long transcript into semantically coherent chunks."""
        chunks = self.splitter.create_documents([transcript])
        docs = [
            Document(page_content=doc.page_content, metadata={'chunk_index': i, 'source': 'meeting'})
            for i, doc in enumerate(chunks)
        ]
        print(f"Transcript split into {len(chunks)} semantic chunks.")
        return docs  
    
    def build_vector_store(self, transcript: str):
        """Splits the transcript and saves it into the Chroma vector database."""
        chunks = self.split_transcript(transcript)
        
        print("Building and saving to Chroma Vector Store...")
        vectorstore = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=self.chroma_dir
        )
        print(f"Successfully saved {len(chunks)} chunks to '{self.chroma_dir}'.")
        return vectorstore 
    
    # FIX 2: load_vector_store ko theek kiya. Yeh purana database load karega
    def load_vector_store(self) -> Chroma: 
        """Loads an EXISTING Chroma vector database from the local directory."""
        print("Loading existing Chroma Vector Store...")
        vectorstore = Chroma(
            embedding_function=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=self.chroma_dir
        )
        print("Vector store loaded successfully.")
        return vectorstore

    # FIX 3: self add kiya aur indentation theek ki
    def get_production_retriever(self, vector_store: Chroma):
        """
        Creates a production-grade retriever using Contextual Compression and Reranking.
        """
        # 1. Base Retriever: Fetch MORE documents initially (e.g., 15)
        base_retriever = vector_store.as_retriever(
            search_type="similarity", 
            search_kwargs={"k": 15}
        )

        # 2. Combine them into a single production retriever
        # self.compressor ko use kar rahe hain jo __init__ mein banaya tha
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=self.compressor,
            base_retriever=base_retriever
        )

        return compression_retriever