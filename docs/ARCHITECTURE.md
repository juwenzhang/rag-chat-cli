# 架构设计文档

## 🎯 设计目标

1. **高性能** - 支持多进程并行处理大数据集
2. **可扩展** - 模块化设计，易于扩展新功能
3. **可维护** - 清晰的结构和命名，易于理解
4. **解耦合** - 低依赖，高内聚

## 🏗️ 整体架构

```
┌─────────────────────────────────────────────────────┐
│                     main.py                          │
│                  (应用入口层)                         │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│                   Utils 模块                         │
│  ┌─────────────────┐    ┌─────────────────────────┐ │
│  │ TaskScheduler   │    │   DataLoaderFactory     │ │
│  │ (任务调度层)      │    │   (数据加载层)           │ │
│  └────────┬────────┘    └───────────┬─────────────┘ │
│           │                          │               │
│           ▼                          ▼               │
│  ┌─────────────────┐    ┌─────────────────────────┐ │
│  │ ProcessPool     │    │  JSONDataLoader         │ │
│  │ Executor        │    │  CSVDataLoader          │ │
│  └─────────────────┘    └─────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

## 📦 模块设计

### 1. TaskScheduler (任务调度器)

**职责**: 管理系统中的并发任务执行

**核心组件**:
- `Task` - 任务单元，包含执行函数、参数、优先级
- `TaskResult` - 任务结果，包含成功状态、返回值、错误信息
- `TaskObserver` - 观察者接口，用于监控任务状态
- `ProcessPoolExecutor` - 多进程执行器

**特性**:
- 单例模式，确保全局唯一调度器
- 观察者模式，支持任务状态监控
- 支持批量任务执行和优先级排序

### 2. DataLoaderFactory (数据加载器工厂)

**职责**: 统一管理不同格式数据的加载

**核心组件**:
- `BaseDataLoader` - 抽象基类，定义加载器接口
- `JSONDataLoader` - JSON 格式加载器
- `CSVDataLoader` - CSV 格式加载器
- `DataLoaderConfig` - 配置数据类

**特性**:
- 工厂模式，根据文件类型创建对应加载器
- 支持多进程并行加载 (`num_proc`)
- 支持批量加载 (`batch_size`)

### 3. DataLoaderManager (数据加载管理器)

**职责**: 管理多个数据加载器

**功能**:
- 注册多个加载器
- 批量加载数据集
- 并行加载支持

### 4. DatasetSplitter (数据集分割器)

**职责**: 数据集分割工具

**功能**:
- 训练/测试集分割
- 分层分割
- K-Fold 交叉验证分割

## 🔄 数据流

```
数据文件 (JSON/CSV)
       │
       ▼
DataLoaderFactory.create()
       │
       ▼
JSONDataLoader / CSVDataLoader
       │
       ▼
load_dataset (多进程加载)
       │
       ▼
   Dataset 对象
       │
       ▼
训练流程 / 评估流程
```

## 🎨 设计模式应用

| 模块 | 设计模式 | 作用 |
|------|---------|------|
| TaskScheduler | 单例模式 | 确保全局唯一调度器实例 |
| TaskScheduler | 观察者模式 | 解耦任务状态监控 |
| DataLoaderFactory | 工厂模式 | 统一创建不同类型加载器 |
| BaseDataLoader | 抽象工厂 | 定义加载器统一接口 |
| Task | 策略模式 | 支持不同任务执行策略 |
| with_multiprocessing | 装饰器模式 | 便捷的多进程封装 |

## ⚙️ 配置管理

### DataLoaderConfig

```python
@dataclass
class DataLoaderConfig:
    file_path: str      # 文件路径
    file_type: str      # 文件类型 (json/csv)
    num_proc: int       # 并行进程数
    batch_size: int     # 批大小
    shuffle: bool       # 是否打乱
    seed: int          # 随机种子
```

### TaskSchedulerConfig

```python
class TaskScheduler:
    def __init__(self, max_workers=None):
        self.max_workers = max_workers or cpu_count()
```

## 🚀 性能优化

1. **多进程并行** - 使用 `ProcessPoolExecutor` 充分利用多核 CPU
2. **批量处理** - 支持批量加载和批量任务提交
3. **观察者解耦** - 避免任务执行和状态监控的耦合
4. **工厂模式** - 统一管理，减少重复代码

## 🔮 未来扩展

1. **支持更多数据格式** - Parquet, Arrow, TFRecord
2. **任务队列** - 支持任务队列和延迟执行
3. **分布式支持** - Ray/Dask 分布式任务调度
4. **缓存机制** - 数据集缓存和增量加载
