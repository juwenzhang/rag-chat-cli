# Ollama Chat

An interactive chat tool powered by Ollama with knowledge base and conversation memory support.

## Features

- **Interactive Chat**: Real-time chat interface with Ollama models
- **Conversation Memory**: Persistent conversation history and context management
- **Knowledge Base**: Integrated knowledge storage and retrieval
- **LoRA Training**: Support for fine-tuning models with LoRA technique
- **Training Data Generation**: Built-in tool for generating training datasets

## Requirements

- Python >= 3.10
- Ollama server running locally

## Installation

```bash
uv sync
```

## Configuration

Edit `config.json` to configure the model and other settings:

```json
{
  "model": {
    "model_name": "qwen2.5:1.5b",
    "base_url": "http://localhost:11434",
    "temperature": 0.7,
    "top_p": 0.9,
    "num_predict": 256
  }
}
```

## Usage

Start the interactive chat:

```bash
ollama-chat --config config.json --model qwen2.5:1.5b --base-url http://localhost:11434
```

### Chat Commands

- `quit` / `exit` / `q` - Exit the chat
- `clear` / `cl` - Clear the screen

## Project Structure

```
├── main.py              # Entry point
├── config.json          # Configuration file
├── configs/             # Training configs
├── data/                # Data directory
├── scripts/             # Training scripts
├── utils/               # Utility modules
└── docs/                # Documentation
```

## License

MIT
