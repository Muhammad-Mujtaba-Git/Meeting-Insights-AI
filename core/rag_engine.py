import os
from langchain_groq import ChatGroq
from config import settings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from core.vector_store import VectorStore
from prompts.prompts import rag_chain_prompt


class RAGEngine:
    def __init__(self):
        self.llm = ChatGroq(model="qwen/qwen3.6-27b", temperature=0.3,api_key=settings.GROQ_API_KEY)
        
        
        self.vs = VectorStore() 
        vectorstore = self.vs.load_vector_store()
        self.retriever = self.vs.get_production_retriever(vectorstore)

    
    def format_doc(self, docs):
        return "\n\n".join([doc.page_content for doc in docs])
    
    def build_rag_chain(self):
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", rag_chain_prompt),
            ("human", "{question}")
        ])
        
        
        rag_pipeline = (
            {"context": self.retriever | RunnableLambda(self.format_doc), 
             "question": RunnablePassthrough()}
            | prompt 
            | self.llm 
            | StrOutputParser()
        )
        
        return rag_pipeline
    
    def load_rag_chain(self):
        prompt = ChatPromptTemplate.from_messages([
            ("system", rag_chain_prompt),
            ("human", "{question}")
        ])
        rag_chain = (
        {
            "context":  self.retriever| RunnableLambda(self.format_docs),
            "question": RunnablePassthrough(),
        }
        | prompt
        | self.llm
        | StrOutputParser()
    )
        return rag_chain
        

