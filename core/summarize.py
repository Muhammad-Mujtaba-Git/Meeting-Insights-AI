from langchain_groq import ChatGroq
from config import settings
import os
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_experimental.text_splitter import SemanticChunker
from langchain_huggingface import HuggingFaceEndpointEmbeddings


class TranscriptSummarizer:
    """
    A class to handle the semantic chunking and summarization of long transcripts
    using a Map-Reduce strategy with local LLMs and Embeddings.
    """
    
    def __init__(self):
        """Initializes the LLM, Embeddings, and Semantic Chunker."""
        self.llm = ChatGroq(model="qwen/qwen3.6-27b", temperature=0.0,api_key=settings.GROQ_API_KEY)
        
        self.embeddings = HuggingFaceEndpointEmbeddings(
        model="BAAI/bge-large-en-v1.5",
        task="feature-extraction",
        huggingfacehub_api_token=settings.HUGGINGFACEHUB_API_TOKEN
)
        
        self.splitter = SemanticChunker(
            self.embeddings, 
            breakpoint_threshold_type="percentile"
        )

    def split_transcript(self, transcript: str) -> list:
        """Splits a long transcript into semantically coherent chunks."""
        chunks = self.splitter.create_documents([transcript])
        print(f"Transcript split into {len(chunks)} semantic chunks.")
        return chunks  

    def summarize(self, transcript: str) -> str:
        """Summarizes the transcript using a Map-Reduce approach."""
        chunks = self.split_transcript(transcript)
        
        map_prompt = ChatPromptTemplate.from_messages([
            ("system", "Summarize this portion of a meeting transcript concisely, capturing key points."),
            ("human", "{text}"),
        ])
        map_chain = map_prompt | self.llm | StrOutputParser()
        
       
        print("Summarizing individual chunks (Batched)...")
        inputs = [{"text": chunk.page_content} for chunk in chunks]
        intermediate_summaries = map_chain.batch(inputs)
        
        combined_text = "\n\n".join(intermediate_summaries)
        
        reduce_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert assistant. Combine these partial summaries into one cohesive, well-structured final summary."),
            ("human", "{text}"),
        ])
        reduce_chain = reduce_prompt | self.llm | StrOutputParser()
        
        print("Generating final consolidated summary...")
        final_summary = reduce_chain.invoke({"text": combined_text})
        
        return final_summary
    

    def make_title(self, context: str) -> str:
        """
        Generates a short, professional title.
        
        Note: Pass a SUMMARY here, not the raw transcript, to avoid 
        context overflow and improve speed.
        """
        title_prompt = ChatPromptTemplate.from_messages([
            ("system", "Based on the text, generate a short professional meeting title. Max 8 words. Return only the title, nothing else."),
            ("human", "{text}"),
        ])
        title_chain = title_prompt | self.llm | StrOutputParser()
        
        print("Generating title...")
       
        title = title_chain.invoke({"text": context[:1000]})
        
        return title

