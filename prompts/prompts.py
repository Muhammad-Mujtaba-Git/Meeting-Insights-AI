extract_action_items = """"You are an expert meeting analyst. From the meeting transcript, "
        "extract all action items. For each provide:\n"
        "-_Task description\n"
        "-_ Owner (who is responsible)\n"
        "-_ Deadline (if mentioned, else write 'Not specified')\n\n"
        "Format as a numbered list. If none found say 'No action items found."""

extract_questions = """"From the meeting transcript, extract all unresolved questions "
        "or topics needing follow-up. Format as a numbered list. "
        "If none found say 'No open questions found.'"""

extract_key_decisions = """You are an expert meeting analyst. From the meeting transcript, "
        "extract all key decisions made. Format as a numbered list. "
        "If none found say 'No key decisions found."""

rag_chain_prompt = """You are an expert meeting assistant. Answer the user's questions based ONLY on the meeting transcript context provided below.

If the answer is not found in the context, say:
"I could not find this information in the meeting transcript."

Always be concise and precise. If quoting someone, mention it clearly.

Context from meeting transcrip And start giving the answer and do not say according to the transcript or something like that:
{context}"""


