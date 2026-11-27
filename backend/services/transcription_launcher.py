import logging
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor

logger = logging.getLogger("transcription_launcher")


def create_task_entry(
    *,
    tasks,
    save_task,
    source_name,
    batch_id=None,
    folder_id=None,
    task_cls=None,
):
    if task_cls is None:
        from backend.app import Task as task_cls
    task_id = str(uuid.uuid4())
    task = task_cls(
        id=task_id,
        status="queued",
        message="任務已加入隊列",
        start_time=time.time(),
        source_name=source_name,
        batch_id=batch_id,
        folder_id=folder_id,
    )
    tasks[task_id] = task
    save_task(task)
    return task


def submit_transcription(
    *,
    executor: ThreadPoolExecutor,
    target,
    task_id: str,
    file_path,
    request,
) -> Future:
    """Submit a transcription job to the shared thread-pool executor."""
    future = executor.submit(target, task_id, file_path, request)
    logger.info(
        "Task %s submitted (pool active ≈ %d)",
        task_id,
        len(executor._threads),
    )
    return future
