#!/usr/bin/env python3
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import KnowledgeBaseLoader, TrainingDataGenerator, get_logger

logger = get_logger(__name__)


def main():
    logger.info("Starting training data generation from knowledge base...")

    with open("./config.json", "r", encoding="utf-8") as f:
        config = json.load(f)

    kb_path = config.get("knowledge_base", {}).get("base_path", "./knowledge")
    logger.info(f"Knowledge base path: {kb_path}")

    kb_loader = KnowledgeBaseLoader(base_path=kb_path)

    articles = kb_loader.get_all_articles()
    logger.info(f"Found {len(articles)} articles in knowledge base")

    for article in articles:
        logger.info(f"  - [{article.category}] {article.title} ({article.difficulty})")

    kb_index = kb_loader.load_index()
    logger.info(f"Knowledge base index: v{kb_index.get('version', 'unknown')}")

    generator = TrainingDataGenerator(kb_loader)

    output_path = config.get("data", {}).get("file_path", "./data/train.json")
    num_samples = generator.generate_from_knowledge_base(
        output_path=output_path,
        min_questions_per_article=3
    )

    logger.info(f"Training data generation completed: {num_samples} samples generated")
    logger.info(f"Output file: {output_path}")


if __name__ == "__main__":
    main()