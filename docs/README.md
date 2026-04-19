# Test Code 项目文档

## 📁 项目结构

```
test_code/
├── main.py                 # 主程序入口
├── utils/
│   ├── __init__.py        # 模块导出
│   ├── task_scheduler.py  # 多进程任务调度器
│   └── data_loader.py     # 数据加载器（工厂模式）
├── data/
│   └── train.json         # 训练数据（50条宫廷对话）
└── docs/
    ├── README.md          # 项目文档
    ├── ARCHITECTURE.md    # 架构设计文档
    ├── API.md             # API 接口文档
    └── DESIGN_PATTERNS.md # 设计模式文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install datasets transformers pandas
```

### 2. 运行主程序

```bash
python main.py
```

## 📝 数据格式

训练数据采用 JSON 格式，包含以下字段：

```json
{
  "instruction": "对话指令/问题",
  "input": "输入内容（可选）",
  "output": "回复内容"
}
```

### 示例数据

```json
{
  "instruction": "小姐，别的秀女都在求中选，唯有咱们小姐想被撂牌子，菩萨一定记得真真儿的——",
  "input": "",
  "output": "嘘——都说许愿说破是不灵的。"
}
```

## 🔧 核心模块

### Utils 模块

- **TaskScheduler** - 多进程任务调度器
- **DataLoaderFactory** - 数据加载器工厂

详细文档请参考 [ARCHITECTURE.md](ARCHITECTURE.md)

## 📊 设计模式

本项目使用了多种设计模式：

- 单例模式 (Singleton)
- 工厂模式 (Factory)
- 观察者模式 (Observer)
- 策略模式 (Strategy)
- 装饰器模式 (Decorator)

详细说明请参考 [DESIGN_PATTERNS.md](DESIGN_PATTERNS.md)

## 📚 更多文档

- [API 接口文档](API.md)
- [架构设计文档](ARCHITECTURE.md)
- [设计模式文档](DESIGN_PATTERNS.md)
