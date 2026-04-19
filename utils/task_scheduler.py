from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Dict
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import Manager, Event
import multiprocessing as mp
from functools import wraps
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class TaskResult:
    task_id: str
    success: bool
    result: Any
    error: Optional[str] = None

    def __repr__(self):
        status = "✓" if self.success else "✗"
        return f"TaskResult({self.task_id}, {status})"


class TaskObserver:
    def on_task_started(self, task: "Task"):
        pass

    def on_task_completed(self, result: TaskResult):
        pass

    def on_all_tasks_completed(self, results: List[TaskResult]):
        pass


class LoggingObserver(TaskObserver):
    def on_task_started(self, task: "Task"):
        logger.info(f"Task started: {task.task_id}")

    def on_task_completed(self, result: TaskResult):
        if result.success:
            logger.info(f"Task completed: {result}")
        else:
            logger.error(f"Task failed: {result}")

    def on_all_tasks_completed(self, results: List[TaskResult]):
        success_count = sum(1 for r in results if r.success)
        logger.info(f"All tasks completed: {success_count}/{len(results)} succeeded")


@dataclass
class Task:
    task_id: str
    func: Callable
    args: tuple
    kwargs: dict


class ParallelProcessor:
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers

    def process(self, tasks: List[Task]) -> List[TaskResult]:
        results = []
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(t.func, *t.args, **t.kwargs): t for t in tasks}
            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    results.append(TaskResult(task.task_id, True, result))
                except Exception as e:
                    results.append(TaskResult(task.task_id, False, None, str(e)))
        return results


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
        self._shutdown_event = Event()
        TaskScheduler._initialized = True
        logger.info(f"TaskScheduler initialized with {self.max_workers} workers")

    def add_observer(self, observer: TaskObserver):
        if not isinstance(observer, TaskObserver):
            raise TypeError("observer must implement TaskObserver interface")
        self.observers.append(observer)

    def notify_task_started(self, task: Task):
        for observer in self.observers:
            observer.on_task_started(task)

    def notify_task_completed(self, result: TaskResult):
        for observer in self.observers:
            observer.on_task_completed(result)

    def notify_all_completed(self, results: List[TaskResult]):
        for observer in self.observers:
            observer.on_all_tasks_completed(results)

    def execute_single(self, task: Task) -> TaskResult:
        self.notify_task_started(task)
        try:
            result = task.func(*task.args, **task.kwargs)
            task_result = TaskResult(task.task_id, True, result)
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            task_result = TaskResult(task.task_id, False, None, str(e))

        self.notify_task_completed(task_result)
        return task_result

    def execute_parallel(self, tasks: List[Task]) -> List[TaskResult]:
        processor = ParallelProcessor(max_workers=self.max_workers)
        results = processor.process(tasks)
        self.notify_all_completed(results)
        return results

    def shutdown(self):
        self._shutdown_event.set()
        TaskScheduler._initialized = False
        TaskScheduler._instance = None
