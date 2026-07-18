import os
from typing import List, Optional, Dict, Any, Callable

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()

from langchain_google_genai import ChatGoogleGenerativeAI

# client = genai.Client(api_key=os.getenv("APIKEY"))
os.environ["GOOGLE_API_KEY"] = os.getenv("APIKEY")

def create_chat_model() -> ChatOpenAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("MODEL"),
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=3,
    )
    # return ChatOpenAI(
    #     model=os.getenv("MODEL"),
    #     base_url=os.getenv("BASEURL"),
    #     api_key=os.getenv("APIKEY"),
    #     temperature=0,
    #     top_p=0,
    #     max_retries=3,
    # )




if __name__ == "__main__":
    chat_model = create_chat_model()
    print(chat_model.invoke("你好").content)
