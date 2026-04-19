import json
import os
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    message_id: str


@dataclass
class Conversation:
    conversation_id: str
    started_at: str
    ended_at: Optional[str] = None
    messages: List[Message] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = []
        if self.metadata is None:
            self.metadata = {}

    def add_message(self, message: Message):
        self.messages.append(message)

    def end(self):
        self.ended_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversation_id": self.conversation_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "messages": [asdict(msg) for msg in self.messages],
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conversation":
        messages = [Message(**msg) for msg in data.get("messages", [])]
        return cls(
            conversation_id=data["conversation_id"],
            started_at=data["started_at"],
            ended_at=data.get("ended_at"),
            messages=messages,
            metadata=data.get("metadata", {})
        )


class ConversationManager:
    def __init__(self, storage_dir: str = "./conversations"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_conversation: Optional[Conversation] = None
        self.current_conversation_id: Optional[str] = None

    def start_new_conversation(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        conversation_id = f"conv_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        self.active_conversation = Conversation(
            conversation_id=conversation_id,
            started_at=datetime.now().isoformat(),
            metadata=metadata or {}
        )
        self.current_conversation_id = conversation_id
        logger.info(f"Started new conversation: {conversation_id}")
        return conversation_id

    def add_message(self, role: str, content: str):
        if not self.active_conversation:
            self.start_new_conversation()

        message_id = f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        message = Message(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat(),
            message_id=message_id
        )
        self.active_conversation.add_message(message)
        return message_id

    def end_conversation(self):
        if self.active_conversation:
            self.active_conversation.end()
            self.save_conversation()
            logger.info(f"Ended conversation: {self.current_conversation_id}")
            self.current_conversation_id = None
            self.active_conversation = None

    def save_conversation(self):
        if not self.active_conversation:
            return

        save_path = self.storage_dir / f"{self.active_conversation.conversation_id}.json"
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.active_conversation.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info(f"Saved conversation to {save_path}")

    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        load_path = self.storage_dir / f"{conversation_id}.json"
        if not load_path.exists():
            return None

        with open(load_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Conversation.from_dict(data)

    def get_conversation_history(self, max_messages: int = 10) -> str:
        if not self.active_conversation or not self.active_conversation.messages:
            return ""

        recent_messages = self.active_conversation.messages[-max_messages:]
        history = []
        for msg in recent_messages:
            if msg.role == "user":
                history.append(f"用户: {msg.content}")
            else:
                history.append(f"AI: {msg.content}")
        return "\n".join(history)

    def get_message_count(self) -> int:
        if not self.active_conversation or not self.active_conversation.messages:
            return 0
        return len(self.active_conversation.messages)

    def get_messages(self) -> List[Message]:
        if not self.active_conversation or not self.active_conversation.messages:
            return []
        return self.active_conversation.messages


class KnowledgeStorage:
    def __init__(self, storage_dir: str = "./knowledge"):
        self.storage_dir = Path(storage_dir)
        self.articles_dir = self.storage_dir / "articles"
        self.articles_dir.mkdir(parents=True, exist_ok=True)

    def should_store_knowledge(self, user_input: str, assistant_response: str) -> bool:
        score = 0

        # 检查内容长度
        if len(assistant_response) > 500:
            score += 3
        elif len(assistant_response) > 200:
            score += 1

        # 检查技术关键词
        tech_keywords = [
            "技术", "实现", "原理", "架构", "优化", "部署", "配置",
            "最佳实践", "性能", "安全", "架构", "设计模式", "算法",
            "框架", "库", "工具", "API", "接口", "服务", "系统"
        ]
        for keyword in tech_keywords:
            if keyword in assistant_response:
                score += 1

        # 检查是否包含代码
        if "```" in assistant_response:
            score += 2

        # 检查是否包含结构化内容
        if any(marker in assistant_response for marker in ["## ", "### ", "#### ", "- ", "* ", "1."]):
            score += 2

        # 阈值判断
        return score >= 5

    def store_knowledge(self, user_input: str, assistant_response: str) -> str:
        article_id = f"chat_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        category = self._categorize_content(assistant_response)
        article_dir = self.articles_dir / category
        article_dir.mkdir(parents=True, exist_ok=True)

        # 生成文章内容
        content = f"# {user_input}\n\n{assistant_response}"

        # 保存 Markdown 文件
        md_path = article_dir / f"{article_id}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 生成元数据
        metadata = {
            "id": article_id,
            "title": user_input,
            "category": category,
            "tags": self._extract_tags(assistant_response),
            "author": "AI Assistant",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "summary": self._generate_summary(assistant_response),
            "difficulty": "intermediate",
            "reading_time": f"{max(1, len(assistant_response) // 1000)}min"
        }

        # 保存元数据文件
        json_path = article_dir / f"{article_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"Stored knowledge to {md_path}")
        return str(md_path)

    def _categorize_content(self, content: str) -> str:
        categories = {
            "frontend": ["React", "Vue", "TypeScript", "JavaScript", "CSS", "HTML", "frontend"],
            "backend": ["Rust", "Node.js", "NestJS", "Express", "Koa", "backend", "server"],
            "mobile": ["Deeplink", "H5", "Android", "iOS", "Flutter", "mobile"],
            "devops": ["Docker", "Kubernetes", "CI/CD", "DevOps", "deploy", "infra"],
            "architecture": ["架构", "系统", "设计", "架构", "微服务", "分布式"]
        }

        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword.lower() in content.lower():
                    return category

        return "general"

    def _extract_tags(self, content: str) -> List[str]:
        tags = []
        tech_terms = [
            "Rust", "Node.js", "Vue", "React", "NestJS", "Koa", "Next.js", "Vite",
            "Docker", "Kubernetes", "Deeplink", "H5", "TypeScript", "JavaScript",
            "Flutter", "Android", "iOS", "API", "REST", "GraphQL", "微服务"
        ]

        for term in tech_terms:
            if term.lower() in content.lower():
                tags.append(term.lower())

        return list(set(tags))[:5]

    def _generate_summary(self, content: str) -> str:
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and not line.startswith('```'):
                return line[:100] + "..." if len(line) > 100 else line
        return "AI 生成的技术内容"


class ChatMemory:
    def __init__(self):
        self.conversation_manager = ConversationManager()
        self.knowledge_storage = KnowledgeStorage()

    def start_conversation(self, metadata: Optional[Dict[str, Any]] = None):
        return self.conversation_manager.start_new_conversation(metadata)

    def add_user_message(self, content: str):
        return self.conversation_manager.add_message("user", content)

    def add_assistant_message(self, content: str):
        message_id = self.conversation_manager.add_message("assistant", content)
        
        # 检查是否需要存储为知识
        if self.conversation_manager.active_conversation:
            user_messages = [msg for msg in self.conversation_manager.active_conversation.messages if msg.role == "user"]
            if user_messages:
                last_user_message = user_messages[-1]
                if self.knowledge_storage.should_store_knowledge(last_user_message.content, content):
                    self.knowledge_storage.store_knowledge(last_user_message.content, content)
        
        return message_id

    def get_conversation_history(self, max_messages: int = 10) -> str:
        return self.conversation_manager.get_conversation_history(max_messages)

    def end_conversation(self):
        self.conversation_manager.end_conversation()

    def get_active_conversation_id(self) -> Optional[str]:
        return self.conversation_manager.current_conversation_id

    def load_conversation(self, conversation_id: str) -> Optional[Conversation]:
        return self.conversation_manager.load_conversation(conversation_id)