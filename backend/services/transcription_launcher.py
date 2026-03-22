import threading
import time
import uuid


class Task:
    pass


def create_task_entry(*, tasks, save_task, source_name):
    task_id = str(uuid.uuid4())
    task = Task(
        id=task_id,
        status="queued",
        message="任務已加入隊列",
        start_time=time.time(),
        source_name=source_name,
    )
    tasks[task_id] = task
    save_task(task)
    return task


def start_transcription_thread(*, target, task_id, file_path, request):
    thread = threading.Thread(target=target, args=(task_id, file_path, request))
    thread.daemon = True
    thread.start()
    return thread
