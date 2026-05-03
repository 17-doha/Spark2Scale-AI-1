from app.core.llm import get_llm
from pydantic import BaseModel

class Plan(BaseModel):
    x: int

try:
    llm = get_llm(provider='modal')
    print("LLM initialized")
    out = llm.with_structured_output(Plan)
    print("with_structured_output succeeded:", out)
except Exception as e:
    print("Error:", repr(e))
