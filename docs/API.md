# API 接口文档

## Utils 模块

### task_scheduler.py

#### TaskResult

任务执行结果数据类

```python
@dataclass
class TaskResult:
    task_id: str           # 任务ID
    success: bool          # 是否成功
    result: Any           # 执行结果
    error: Optional[str]   # 错误信息
```

**方法**:
- `__repr__()` - 返回可读的任务结果字符串

---

#### Task

任务单元类

```python
class Task:
    def __init__(
        self,
        task_id: str,           # 任务唯一标识
        func: Callable,          # 执行函数
        args: tuple = (),        # 位置参数
        kwargs: Dict = {},       # 关键字参数
        priority: int = 0        # 优先级（数值越大优先级越高）
    )
```

**方法**:
- `execute() -> TaskResult` - 执行任务并返回结果
- `__lt__(other)` - 支持优先级比较

---

#### TaskObserver

任务状态观察者抽象基类

```python
class TaskObserver(ABC):
    def on_task_started(self, task: Task)
    def on_task_completed(self, result: TaskResult)
    def on_all_tasks_completed(self, results: List[TaskResult])
```

**子类**:
- `LoggingObserver` - 日志观察者，将任务状态记录到日志

---

#### TaskScheduler

多进程任务调度器（单例模式）

```python
class TaskScheduler:
    def __init__(self, max_workers: Optional[int] = None)
```

**方法**:

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add_observer` | observer: TaskObserver | None | 添加观察者 |
| `remove_observer` | observer: TaskObserver | None | 移除观察者 |
| `execute_single` | task: Task | TaskResult | 执行单个任务 |
| `execute_batch` | tasks: List[Task], priority_sort: bool = True | List[TaskResult] | 批量执行任务 |
| `execute_map` | func: Callable, iterable: List, task_prefix: str | List[Any] | 并行映射执行 |
| `shutdown` | wait: bool = True | None | 关闭调度器 |

**使用示例**:

```python
scheduler = TaskScheduler(max_workers=4)
scheduler.add_observer(LoggingObserver())

task = Task(task_id="my_task", func=my_function, args=(1, 2), kwargs={"key": "value"})
result = scheduler.execute_single(task)
```

---

#### ParallelProcessor

并行处理器类

```python
class ParallelProcessor:
    def __init__(self, num_workers: Optional[int] = None, chunk_size: int = 1)
```

**方法**:

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `process` | items: List, func: Callable | List[Any] | 并行处理列表 |
| `process_chunked` | items: List, func: Callable | List[Any] | 分块并行处理 |

---

### data_loader.py

#### DataLoaderConfig

数据加载器配置数据类

```python
@dataclass
class DataLoaderConfig:
    file_path: str           # 文件路径
    file_type: str = "json"  # 文件类型
    num_proc: int = 4        # 并行进程数
    batch_size: int = 1000   # 批大小
    shuffle: bool = False    # 是否打乱
    seed: Optional[int] = None  # 随机种子
```

---

#### BaseDataLoader

数据加载器抽象基类

```python
class BaseDataLoader(ABC):
    def __init__(self, config: DataLoaderConfig)

    @abstractmethod
    def load(self) -> Dataset

    @abstractmethod
    def load_batch(self, batch_size: Optional[int] = None)
```

---

#### JSONDataLoader

JSON 格式数据加载器

```python
class JSONDataLoader(BaseDataLoader):
    def __init__(self, config: DataLoaderConfig)

    def load(self) -> Dataset
    def load_batch(self, batch_size: Optional[int] = None) -> Iterator[Dataset]
```

**使用示例**:

```python
config = DataLoaderConfig(file_path="./data/train.json", file_type="json", num_proc=4)
loader = JSONDataLoader(config)
dataset = loader.load()
```

---

#### CSVDataLoader

CSV 格式数据加载器

```python
class CSVDataLoader(BaseDataLoader):
    def __init__(self, config: DataLoaderConfig)

    def load(self) -> Dataset
    def load_batch(self, batch_size: Optional[int] = None) -> Iterator[Dataset]
```

---

#### DataLoaderFactory

数据加载器工厂类

```python
class DataLoaderFactory:
    @classmethod
    def create(cls, config: DataLoaderConfig) -> BaseDataLoader

    @classmethod
    def register(cls, file_type: str, loader_class: type)

    @classmethod
    def get_supported_types(cls) -> List[str]
```

**使用示例**:

```python
config = DataLoaderConfig(file_path="./data/train.json", file_type="json", num_proc=4)
loader = DataLoaderFactory.create(config)
dataset = loader.load()

# 查看支持的类型
print(DataLoaderFactory.get_supported_types())  # ['json', 'csv']
```

---

#### DataLoaderManager

数据加载管理器

```python
class DataLoaderManager:
    def __init__(self)

    def register_loader(self, name: str, loader: BaseDataLoader)
    def get_loader(self, name: str) -> BaseDataLoader
    def load_all(self) -> Dict[str, Dataset]
    def load_parallel(self, num_workers: Optional[int] = None) -> Dict[str, Dataset]
```

---

#### DatasetSplitter

数据集分割工具

```python
class DatasetSplitter:
    @staticmethod
    def train_test_split(
        dataset: Dataset,
        test_size: float = 0.2,
        seed: Optional[int] = None
    ) -> tuple

    @staticmethod
    def stratified_split(
        dataset: Dataset,
        stratify_column: str,
        test_size: float = 0.2,
        seed: Optional[int] = None
    ) -> tuple

    @staticmethod
    def k_fold_split(
        dataset: Dataset,
        k: int = 5,
        seed: Optional[int] = None
    ) -> List[Dataset]
```

**使用示例**:

```python
train_ds, test_ds = DatasetSplitter.train_test_split(dataset, test_size=0.2)
folds = DatasetSplitter.k_fold_split(dataset, k=5)
```
