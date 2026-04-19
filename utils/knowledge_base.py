import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import glob

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ArticleMetadata:
    id: str
    title: str
    category: str
    tags: List[str]
    author: str
    created_at: str
    updated_at: str
    summary: str
    difficulty: str
    reading_time: str
    file_path: Optional[str] = None


class KnowledgeBaseLoader:
    def __init__(self, base_path: str = "./knowledge"):
        self.base_path = Path(base_path)
        self.articles_path = self.base_path / "articles"
        self._index: Optional[Dict[str, Any]] = None

    def load_index(self) -> Dict[str, Any]:
        index_path = self.base_path / "index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                self._index = json.load(f)
        else:
            self._index = {"version": "1.0.0", "articles": []}
        return self._index

    def get_articles_by_category(self, category: str) -> List[ArticleMetadata]:
        articles = []
        category_path = self.articles_path / category

        if not category_path.exists():
            logger.warning(f"Category path does not exist: {category_path}")
            return articles

        json_files = glob.glob(str(category_path / "*.json"))
        for json_file in json_files:
            metadata = self._load_article_metadata(json_file)
            if metadata:
                metadata.file_path = str(category_path / f"{metadata.id}.md")
                articles.append(metadata)

        return articles

    def _load_article_metadata(self, json_path: str) -> Optional[ArticleMetadata]:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            return ArticleMetadata(
                id=data.get("id", ""),
                title=data.get("title", ""),
                category=data.get("category", ""),
                tags=data.get("tags", []),
                author=data.get("author", ""),
                created_at=data.get("created_at", ""),
                updated_at=data.get("updated_at", ""),
                summary=data.get("summary", ""),
                difficulty=data.get("difficulty", ""),
                reading_time=data.get("reading_time", "")
            )
        except Exception as e:
            logger.error(f"Failed to load metadata from {json_path}: {e}")
            return None

    def load_article_content(self, metadata: ArticleMetadata) -> Optional[str]:
        if not metadata.file_path:
            return None

        try:
            with open(metadata.file_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            logger.error(f"Failed to load article content: {e}")
            return None

    def get_all_articles(self) -> List[ArticleMetadata]:
        all_articles = []
        for category in ["frontend", "backend", "mobile", "devops", "architecture"]:
            articles = self.get_articles_by_category(category)
            all_articles.extend(articles)
        return all_articles

    def search_by_tag(self, tag: str) -> List[ArticleMetadata]:
        results = []
        for article in self.get_all_articles():
            if tag.lower() in [t.lower() for t in article.tags]:
                results.append(article)
        return results


class TrainingDataGenerator:
    def __init__(self, kb_loader: KnowledgeBaseLoader):
        self.kb_loader = kb_loader

    def generate_instruction_response(
        self,
        metadata: ArticleMetadata,
        content: str,
        num_questions: int = 3
    ) -> List[Dict[str, Any]]:
        questions = self._get_questions_for_category(metadata.category, metadata.title)

        results = []
        for i, question in enumerate(questions[:num_questions]):
            results.append({
                "instruction": question,
                "input": "",
                "output": content
            })

        return results

    def _get_questions_for_category(self, category: str, title: str) -> List[str]:
        question_templates = {
            "frontend": [
                f"请详细介绍一下 {title} 的核心概念和实际应用场景？",
                f"如何使用 {title} 优化前端应用性能？",
                f"{title} 在大型项目中的最佳实践是什么？",
                f"对比分析 {title} 与其他类似技术的优劣势？",
                f"深入讲解 {title} 的底层原理和实现机制？"
            ],
            "backend": [
                f"请介绍一下 {title} 的核心特性和适用场景？",
                f"如何使用 {title} 构建高性能后端服务？",
                f"{title} 在微服务架构中如何应用？",
                f"讲解 {title} 的内存管理和性能优化技巧？",
                f"{title} 的错误处理和容错机制设计？"
            ],
            "mobile": [
                f"请详细讲解 {title} 的实现原理和方案选型？",
                f"如何使用 {title} 优化移动端用户体验？",
                f"{title} 在跨平台开发中的应用？",
                f"移动端 {title} 的性能优化和监控？",
                f"{title} 的安全性和权限管理？"
            ],
            "devops": [
                f"请介绍一下 {title} 的核心概念和架构设计？",
                f"如何使用 {title} 实现自动化部署和运维？",
                f"{title} 在生产环境中的最佳实践？",
                f"讲解 {title} 的监控告警和故障排查？",
                f"{title} 的安全加固和资源优化？"
            ],
            "architecture": [
                f"请详细分析 {title} 的系统架构设计？",
                f"如何使用 {title} 实现高可用和可扩展性？",
                f"{title} 的数据一致性和事务管理？",
                f"讲解 {title} 的容量规划和性能调优？",
                f"{title} 的容灾备份和恢复策略？"
            ]
        }

        return question_templates.get(category, [
            f"请介绍一下 {title}？",
            f"{title} 有哪些应用场景？",
            f"如何使用 {title}？"
        ])

    def generate_from_knowledge_base(
        self,
        output_path: str,
        min_questions_per_article: int = 3
    ) -> int:
        articles = self.kb_loader.get_all_articles()
        logger.info(f"Found {len(articles)} articles in knowledge base")

        all_training_data = []

        for metadata in articles:
            content = self.kb_loader.load_article_content(metadata)
            if not content:
                logger.warning(f"Skipping article {metadata.id}: content not found")
                continue

            training_items = self.generate_instruction_response(
                metadata,
                content,
                num_questions=min_questions_per_article
            )
            all_training_data.extend(training_items)
            logger.info(f"Generated {len(training_items)} items from {metadata.id}")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(all_training_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Generated {len(all_training_data)} training samples -> {output_path}")
        return len(all_training_data)