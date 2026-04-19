from utils import (
    OllamaModel,
    OllamaConfig,
    PipelineConfig,
    load_config,
    get_logger,
)
from utils.console_ui import ChatConsole
from utils.chat_memory import ConversationManager, KnowledgeStorage


logger = get_logger(__name__)


def run_interactive_chat(config: PipelineConfig):
    chat_ui = ChatConsole()
    chat_ui.print_welcome()

    conversation_manager = ConversationManager()
    knowledge_storage = KnowledgeStorage()

    ollama_config = OllamaConfig(
        model_name=config.model.model_name,
        base_url=config.model.base_url,
        temperature=config.model.temperature,
        top_p=config.model.top_p,
        num_predict=config.model.num_predict
    )

    try:
        model = OllamaModel(config=ollama_config, verify_connection=True)
    except Exception as e:
        chat_ui.print_error(f"无法连接到 Ollama: {e}")
        return

    try:
        while True:
            try:
                user_input = input("[cyan]└─>[/cyan] ").strip()

                if user_input.lower() in ["quit", "exit", "q"]:
                    chat_ui.print_info("正在结束会话...")
                    break

                if user_input.lower() in ["clear", "cl"]:
                    chat_ui.clear_screen()
                    chat_ui.print_welcome()
                    continue

                if not user_input:
                    continue

                chat_ui.print_user_message(user_input)

                collected_response = []
                try:
                    for chunk in model.stream_chat(instruction=user_input):
                        print(chunk, end="", flush=True)
                        collected_response.append(chunk)

                    print()

                    if not collected_response:
                        chat_ui.print_error("未收到任何响应")
                    else:
                        assistant_response = "".join(collected_response)
                        chat_ui.print_ai_response(assistant_response)
                        conversation_manager.add_message("user", user_input)
                        conversation_manager.add_message("assistant", assistant_response)

                except Exception as e:
                    chat_ui.print_error(f"生成响应时出错: {e}")

            except KeyboardInterrupt:
                print("\n")
                chat_ui.print_info("用户中断，正在结束会话...")
                break

    finally:
        if conversation_manager.active_conversation and conversation_manager.get_message_count() > 0:
            conversation_manager.save_conversation()
            chat_ui.print_info("对话已保存")

            messages = conversation_manager.get_messages()
            if len(messages) >= 2:
                user_message = None
                assistant_message = None
                for msg in reversed(messages):
                    if msg.role == "assistant" and not assistant_message:
                        assistant_message = msg.content
                    elif msg.role == "user" and not user_message:
                        user_message = msg.content
                    if user_message and assistant_message:
                        break

                if user_message and assistant_message:
                    if knowledge_storage.should_store_knowledge(user_message, assistant_message):
                        chat_ui.print_info("正在分析对话内容，提取知识...")
                        article_path = knowledge_storage.store_knowledge(user_message, assistant_message)
                        if article_path:
                            chat_ui.print_success(f"知识已存储到: {article_path}")

        model.close()
        chat_ui.print_success("会话已结束")


def main(config_path: str = None):
    config = load_config(config_path)
    run_interactive_chat(config)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tech Blog AI Assistant")
    parser.add_argument("--config", "-c", type=str, help="Path to config.json file")
    parser.add_argument("--train", "-t", action="store_true", help="Run LoRA training")
    parser.add_argument("--train-config", type=str, help="Path to LoRA training config JSON")
    args = parser.parse_args()

    if args.train:
        from scripts.lora_train import LoRATrainer, LoRATrainingConfig, load_lora_config_from_json

        training_config = LoRATrainingConfig()
        if args.train_config:
            training_config = load_lora_config_from_json(args.train_config)

        trainer = LoRATrainer(training_config)
        trainer.train()
    else:
        main(args.config)
