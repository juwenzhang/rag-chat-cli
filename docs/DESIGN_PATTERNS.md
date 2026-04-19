# 设计模式文档

本文档详细说明了项目中使用的设计模式及其实现方式。

## 📋 目录

1. [单例模式 (Singleton)](#1-单例模式-singleton)
2. [工厂模式 (Factory)](#2-工厂模式-factory)
3. [观察者模式 (Observer)](#3-观察者模式-observer)
4. [策略模式 (Strategy)](#4-策略模式-strategy)
5. [装饰器模式 (Decorator)](#5-装饰器模式-decorator)

---

## 1. 单例模式 (Singleton)

### 意图

确保一个类只有一个实例，并提供一个全局访问点。

### 应用场景

`TaskScheduler` 使用单例模式确保全局只有一个任务调度器实例，避免多实例竞争资源。

### 实现

```python
class TaskScheduler:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, max_workers: Optional[int] = None):
        if TaskScheduler._initialized:
            return
        self.max_workers = max_workers or mp.cpu_count()
        self.observers: List[TaskObserver] = []
        TaskScheduler._initialized = True
```

### 类图

```
┌─────────────────────────┐
│    TaskScheduler        │
├─────────────────────────┤
│ - _instance: TaskScheduler │
│ - _initialized: bool   │
├─────────────────────────┤
│ + __new__()             │
│ + __init__()            │
│ + add_observer()        │
│ + execute_single()       │
│ + execute_batch()       │
└─────────────────────────┘
```

---

## 2. 工厂模式 (Factory)

### 意图

定义一个创建对象的接口，让子类决定实例化哪一个类。

### 应用场景

`DataLoaderFactory` 根据文件类型创建对应的数据加载器。

### 实现

```python
class DataLoaderFactory:
    _loaders = {
        "json": JSONDataLoader,
        "csv": CSVDataLoader,
    }

    @classmethod
    def create(cls, config: DataLoaderConfig) -> BaseDataLoader:
        file_type = config.file_type.lower()
        if file_type not in cls._loaders:
            raise ValueError(f"Unsupported file type '{file_type}'")
        loader_class = cls._loaders[file_type]
        return loader_class(config)
```

### 使用示例

```python
config = DataLoaderConfig(file_path="./data/train.json", file_type="json")
loader = DataLoaderFactory.create(config)
dataset = loader.load()
```

### 类图

```
┌──────────────────────────────┐
│    DataLoaderFactory         │
├──────────────────────────────┤
│ + _loaders: Dict            │
├──────────────────────────────┤
│ + create(config)             │
│ + register(type, class)       │
│ + get_supported_types()      │
└──────────────────────────────┘
            │
            │ creates
            ▼
┌──────────────────────────────┐
│     BaseDataLoader           │
│        <<abstract>>           │
├──────────────────────────────┤
│ + load()                     │
│ + load_batch()               │
└──────────┬───────────────────┘
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌─────────┐ ┌─────────┐
│   JSON  │ │   CSV   │
│  Loader │ │  Loader │
└─────────┘ └─────────┘
```

---

## 3. 观察者模式 (Observer)

### 意图

定义对象间的一种一对多依赖关系，当一个对象状态改变时，所有依赖它的对象都会收到通知。

### 应用场景

`TaskScheduler` 使用观察者模式通知任务状态变化，实现日志记录、进度追踪等功能。

### 实现

```python
class TaskObserver(ABC):
    @abstractmethod
    def on_task_started(self, task: Task):
        pass

    @abstractmethod
    def on_task_completed(self, result: TaskResult):
        pass

    @abstractmethod
    def on_all_tasks_completed(self, results: List[TaskResult]):
        pass

class LoggingObserver(TaskObserver):
    def on_task_started(self, task: Task):
        logger.info(f"Task started: {task.task_id}")

    def on_task_completed(self, result: TaskResult):
        if result.success:
            logger.info(f"Task completed: {result}")
        else:
            logger.error(f"Task failed: {result}")

    def on_all_tasks_completed(self, results: List[TaskResult]):
        success_count = sum(1 for r in results if r.success)
        logger.info(f"All tasks completed: {success_count}/{len(results)} succeeded")
```

### 使用示例

```python
scheduler = TaskScheduler()
scheduler.add_observer(LoggingObserver())
scheduler.add_observer(CustomObserver())  # 可添加自定义观察者
```

### 类图

```
┌─────────────────────┐
│  <<interface>>       │
│   TaskObserver       │
├─────────────────────┤
│ + on_task_started()  │
│ + on_task_completed()│
│ + on_all_completed() │
└──────────┬──────────┘
           │
           │ implements
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌──────────┐
│ Logging │ │ Custom   │
│Observer │ │ Observer │
└─────────┘ └──────────┘
     ▲
     │ notifies
     │
┌────┴────────────┐
│  TaskScheduler  │
├────────────────┤
│ + execute_*()   │
│ + add_observer()│
└────────────────┘
```

---

## 4. 策略模式 (Strategy)

### 意图

定义一系列算法，把它们一个个封装起来，并且使它们可相互替换。

### 应用场景

`Task` 类支持不同的执行策略，`BaseDataLoader` 子类实现不同的数据加载策略。

### 实现 (Task)

```python
class Task:
    def __init__(
        self,
        task_id: str,
        func: Callable,
        args: tuple = (),
        kwargs: Dict = {},
        priority: int = 0
    ):
        self.task_id = task_id
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.priority = priority

    def execute(self) -> TaskResult:
        try:
            result = self.func(*self.args, **self.kwargs)
            return TaskResult(self.task_id, True, result)
        except Exception as e:
            return TaskResult(self.task_id, False, None, str(e))
```

### 实现 (DataLoader)

```python
class BaseDataLoader(ABC):
    @abstractmethod
    def load(self) -> Dataset:
        pass

class JSONDataLoader(BaseDataLoader):
    def load(self) -> Dataset:
        return hf_load_dataset("json", data_files=self.config.file_path)

class CSVDataLoader(BaseDataLoader):
    def load(self) -> Dataset:
        return hf_load_dataset("csv", data_files=self.config.file_path)
```

### 类图

```
┌─────────────────────────────┐
│          Task               │
├─────────────────────────────┤
│ - task_id                   │
│ - func: Callable            │
│ - args, kwargs              │
├─────────────────────────────┤
│ + execute(): TaskResult     │
└─────────────────────────────┘

┌─────────────────────────────┐
│       BaseDataLoader        │
│         <<abstract>>         │
├─────────────────────────────┤
│ + load(): Dataset           │
│ + load_batch()              │
└──────────────┬──────────────┘
               │
        ┌──────┴──────┐
        │             │
        ▼             ▼
  ┌───────────┐ ┌───────────┐
  │   JSON    │ │   CSV     │
  │  Loader   │ │  Loader   │
  └───────────┘ └───────────┘
```

---

## 5. 装饰器模式 (Decorator)

### 意图

动态地给对象添加一些额外的职责。

### 应用场景

`@with_multiprocessing` 装饰器为普通函数添加多进程执行能力。

### 实现

```python
def with_multiprocessing(max_workers: Optional[int] = None):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            scheduler = TaskScheduler(max_workers=max_workers)
            task = Task(
                task_id=func.__name__,
                func=func,
                args=args,
                kwargs=kwargs
            )
            result = scheduler.execute_single(task)
            if not result.success:
                raise RuntimeError(f"Task failed: {result.error}")
            return result.result
        return wrapper
    return decorator
```

### 使用示例

```python
@with_multiprocessing(max_workers=4)
def process_data(data):
    # 复杂的数据处理逻辑
    return transformed_data

# 直接调用，自动多进程执行
result = process_data(large_dataset)
```

### 类图

```
┌──────────────────────────────────┐
│          process_data            │
│            (函数)                │
└──────────────┬───────────────────┘
               │ decorated by
               ▼
┌──────────────────────────────────┐
│     @with_multiprocessing       │
│         (装饰器)                 │
├──────────────────────────────────┤
│ - scheduler: TaskScheduler      │
├──────────────────────────────────┤
│ + wrapper(): TaskResult         │
└──────────────────────────────────┘
```

---

## 📊 设计模式总结

| 模式 | 类/模块 | 好处 |
|------|---------|------|
| 单例模式 | TaskScheduler | 全局唯一实例，避免资源竞争 |
| 工厂模式 | DataLoaderFactory | 解耦创建逻辑，易于扩展新格式 |
| 观察者模式 | TaskObserver | 灵活的事件通知机制 |
| 策略模式 | Task, BaseDataLoader | 算法可替换，支持多样化策略 |
| 装饰器模式 | @with_multiprocessing | 非侵入式功能增强 |

## 🔧 扩展指南

### 添加新的数据加载器

1. 继承 `BaseDataLoader`
2. 实现 `load()` 和 `load_batch()` 方法
3. 使用 `DataLoaderFactory.register()` 注册

```python
class ParquetDataLoader(BaseDataLoader):
    def load(self) -> Dataset:
        return hf_load_dataset("parquet", data_files=self.config.file_path)

DataLoaderFactory.register("parquet", ParquetDataLoader)
```

### 添加新的观察者

1. 继承 `TaskObserver`
2. 实现回调方法

```python
class ProgressObserver(TaskObserver):
    def __init__(self):
        self.progress = 0

    def on_task_started(self, task: Task):
        self.progress += 1
        print(f"Progress: {self.progress} tasks started")
```
