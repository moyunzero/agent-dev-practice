"""Day2 第 1 课：Models + Prompts + Output Parser + LCEL（最小可跑）。"""

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3:0.6b"


settings = Settings()

# --- Models：对接大模型的统一入口 ---
model = ChatOpenAI(
    base_url=settings.ollama_base_url,
    api_key="ollama",
    model=settings.ollama_model,
    temperature=0,
)

# --- Prompts：把「可变槽位」填进固定话术 ---
prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是严格的老师。如果问题关于 LangChain，必须提到「用 | 连接组件」；只用一句话。"),
        ("human", "{question}"),
    ]
)

# --- Output Parser：把模型返回的消息对象收成纯字符串 ---
parser = StrOutputParser()

# --- Chains / LCEL：用 | 把组件串成流水线 ---
chain = prompt | model | parser

if __name__ == "__main__":
    # 问清楚「LangChain 里的」，避免小模型联想到金融杠杆
    question = "在 LangChain 里，LCEL 是什么？用一句话解释。"
    print("Q:", question)
    print("A:", chain.invoke({"question": question}))
