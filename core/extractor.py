from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


from prompts.prompts import (
    extract_action_items as ACTION_ITEMS_PROMPT,
    extract_key_decisions as KEY_DECISIONS_PROMPT,
    extract_questions as QUESTIONS_PROMPT
)

class TranscriptPointsExtract:
    """Service class for extracting structured insights from meeting transcripts."""

    def __init__(self, model: str = "llama3.1:8b", temperature: float = 0.3):
        """
        Initializes the LLM.
        """
        self.llm = ChatOllama(model=model, temperature=temperature)

    def _build_chain(self, system_prompt: str):
        """
        Helper method to build a standard LCEL chain.
        """
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{text}")
        ])
        # Chain: Prompt -> LLM -> String Output Parser
        return prompt | self.llm | StrOutputParser()

    def extract_action_items(self, transcript: str) -> str:
        """Extracts action items and tasks from the transcript."""
        chain = self._build_chain(ACTION_ITEMS_PROMPT)
        return chain.invoke({"text": transcript})

    def extract_questions(self, transcript: str) -> str:
        """Extracts questions asked during the meeting."""
        chain = self._build_chain(QUESTIONS_PROMPT)
        return chain.invoke({"text": transcript})

    def extract_key_decisions(self, transcript: str) -> str:
        """Extracts key decisions made during the meeting."""
        chain = self._build_chain(KEY_DECISIONS_PROMPT)
        return chain.invoke({"text": transcript})