# ✅ app/agent/llm_setup.py
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os

load_dotenv()

llm = ChatOpenAI(
    model="gpt-4o-mini", 
    temperature=0.0,
    api_key=os.getenv("OPENAI_API_KEY")
)