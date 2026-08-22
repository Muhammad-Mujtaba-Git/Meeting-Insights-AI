from typing import Annotated
from pydantic import BaseModel, Field

class ProcessRequest(BaseModel):
   
    source: Annotated[str, Field(..., description="The URL or local path of the audio/video file.")]

class QueryRequest(BaseModel):
    question: Annotated[str, Field(..., description="The user's question for the RAG engine.")]