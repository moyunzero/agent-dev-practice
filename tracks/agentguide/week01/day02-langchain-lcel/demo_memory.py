"""Day2：理解 Memory —— LLM 默认无状态，记忆要靠「把历史消息再送进去」。"""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    ollama_base_url: str = "http://localhost:11434/v1" 
    ollama_model: str = "qwen3:0.6b"


settings = Settings()
model = ChatOpenAI(
    base_url=settings.ollama_base_url,
    api_key="ollama",
    model=settings.ollama_model,
    temperature=0,
)

# 用不常见的名字，避免小模型在无历史时「蒙对小明」
NAME = "光盾七十九号"

print("=== 1) 无 Memory：每次 invoke 彼此独立 ===")
r1 = model.invoke([HumanMessage(f"我叫{NAME}，请记住。只用一句话确认。")])
print("第1轮:", r1.content)
r2 = model.invoke([HumanMessage("我叫什么名字？只用一句话回答，只输出名字本身。")])
print("第2轮(无历史):", r2.content)

print("\n=== 2) 有 Memory：把历史消息一起送给模型 ===")
history = [
    SystemMessage("你是简洁助手，根据对话历史回答。只用一句话。"),
    HumanMessage(f"我叫{NAME}，请记住。"),
]
r3 = model.invoke(history)
history.append(AIMessage(content=r3.content))
history.append(HumanMessage("我叫什么名字？"))
r4 = model.invoke(history)
print("第2轮(有历史):", r4.content)
