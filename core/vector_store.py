from config import settings
from langchain_huggingface import HuggingFaceEndpointEmbeddings
from langchain_experimental.text_splitter import SemanticChunker
from langchain_core.documents import Document
from langchain_classic.retrievers import ContextualCompressionRetriever
from langchain_classic.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_postgres import PGVector
from sqlalchemy import create_engine


class VectorStore:
    """
    A wrapper class around PGVector for managing meeting transcripts.
    
    Handles semantic chunking of text, generating embeddings, storing them 
    in a PostgreSQL database, and setting up a production-grade retriever 
    with cross-encoder reranking.
    """

    def __init__(self, top_n: int = 4):
        """
        Initializes the VectorStore with necessary models and database connections.

        Args:
            top_n (int): The number of top documents to keep after reranking. Defaults to 4.
        """
        self.collection_name = "Meeting"

        self.engine = create_engine(settings.DATABASE_URL)
        self.embeddings = HuggingFaceEndpointEmbeddings(
            model="BAAI/bge-large-en-v1.5",
            task="feature-extraction",
            huggingfacehub_api_token=settings.HUGGINGFACEHUB_API_TOKEN
        )

        self.splitter = SemanticChunker(
            self.embeddings,
            breakpoint_threshold_type="percentile"
        )

        self.reranker_model = HuggingFaceCrossEncoder(model_name="BAAI/bge-reranker-base")
        self.compressor = CrossEncoderReranker(model=self.reranker_model, top_n=top_n)

    def split_transcript(self, transcript: str, meeting_id: str) -> list:
        """
        Splits a long transcript into semantically coherent chunks.
        
        Enriches each chunk with metadata including its index, source, 
        and the meeting_id for later filtering during retrieval.

        Args:
            transcript (str): The raw text transcript of the meeting.
            meeting_id (str): The unique identifier for the meeting.

        Returns:
            list: A list of LangChain Document objects containing chunked text and metadata.
        """
        chunks = self.splitter.create_documents([transcript])
        for i, doc in enumerate(chunks):
            doc.metadata.update({
                "chunk_index": i,
                "source": "meeting",
                "meeting_id": meeting_id
            })
        return chunks

    def build_vector_store(self, transcript: str, meeting_id: str) -> PGVector:
        """
        Splits the transcript, embeds each chunk, and stores them into the pgvector database.

        Args:
            transcript (str): The raw text transcript of the meeting.
            meeting_id (str): The unique identifier for the meeting.

        Returns:
            PGVector: The initialized PGVector instance with the documents added.
        """
        chunks = self.split_transcript(transcript, meeting_id)
        vectorstore = PGVector(
            embeddings=self.embeddings,
            collection_name=self.collection_name,
            connection=self.engine,
            use_jsonb=True
        )
        vectorstore.add_documents(chunks)
        return vectorstore

    def load_vector_store(self) -> PGVector:
        """
        Loads an existing PGVector collection from the PostgreSQL database.
        
        Use this method when embeddings are already persisted and you just need 
        a retriever instance.

        Returns:
            PGVector: The loaded PGVector instance.
        """
        print("Loading existing PGVector Store...")
        vectorstore = PGVector(
            embeddings=self.embeddings,
            collection_name=self.collection_name,
            connection=self.engine,
            use_jsonb=True
        )
        print("Vector store loaded successfully.")
        return vectorstore

    def get_production_retriever(self, vector_store: PGVector, meeting_id: str) -> ContextualCompressionRetriever:
        """
        Creates a production-grade retriever using Contextual Compression and Cross-Encoder Reranking.
        
        First retrieves the top 15 chunks filtered by meeting_id, then reranks them 
        using the cross-encoder to return only the most relevant chunks.

        Args:
            vector_store (PGVector): The PGVector instance to retrieve from.
            meeting_id (str): The unique identifier for the meeting to filter by.

        Returns:
            ContextualCompressionRetriever: The configured retriever object.
        """
        base_retriever = vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": 15, "filter": {"meeting_id": meeting_id}}
        )
        compression_retriever = ContextualCompressionRetriever(
            base_compressor=self.compressor,
            base_retriever=base_retriever
        )
        return compression_retriever