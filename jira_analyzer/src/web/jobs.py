"""Фоновые задания для web-интерфейса: состояние в памяти процесса.

Прогресс — из логов и от fetch-фаз: обработчик перехватывает INFO-записи
ТОЛЬКО своего потока (параллельные задания не смешивают логи), fetch докладывает
(фаза, сколько скачано, total, финальный статус) — фронтенд опрашивает
/api/job/{id} и рисует полосы по фазам из job.phases.
«Стоп» (request_stop) останавливает выгрузку целиком; «крестики»
(request_skip) отменяют отдельную фазу (история/комментарии) — fetch
завершает её на ближайшей границе и идёт дальше.
"""
from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

from src.core.pipeline import PipelineOptions, run_fetch, run_pipeline
from src.fetch.run import FetchStopped

# Готовые задания держим в памяти ограниченно: самые свежие.
MAX_FINISHED_JOBS = 50

PHASE_LABELS = {
    "issues": "задачи",
    "changelog": "история изменений",
    "doload": "догрузка полных историй",
    "comments": "комментарии",
}


class _JobLogHandler(logging.Handler):
    def __init__(self, sink: deque, thread_name: str):
        super().__init__(logging.INFO)
        self.sink = sink
        self.thread_name = thread_name

    def emit(self, record: logging.LogRecord) -> None:
        if record.threadName != self.thread_name:
            return  # чужие задания пишут в свои буферы, а не в этот
        try:
            self.sink.append(f"{datetime.now():%H:%M:%S} {record.getMessage()}")
        except Exception:
            pass


@dataclass
class Job:
    id: str
    opts: PipelineOptions
    status: str = "running"  # running | done | error | stopped
    started: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))
    error: str | None = None
    result: dict = field(default_factory=dict)
    log: deque = field(default_factory=lambda: deque(maxlen=500))
    stop_event: threading.Event = field(default_factory=threading.Event)
    # {"phase", "done", "total"} — обновляет fetch через колбэк opts.progress
    progress: dict | None = None
    # состояние фаз для полос web: {phase: {label, done, total, status}} —
    # status: running | done | cancelled; заполняет тот же колбэк
    phases: dict = field(default_factory=dict)
    # отменённые в процессе фазы («крестики»): changelog | comments
    skip_phases: set = field(default_factory=set)


JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def start_job(opts: PipelineOptions) -> str:
    _prune_jobs()
    job = Job(id=uuid.uuid4().hex[:12], opts=opts)
    thread_name = f"job-{job.id}"
    opts.progress = _progress_setter(job)      # fetch докладывает прогресс в задание
    opts.stop_event = job.stop_event           # «Стоп» из web: fetch проверяет между страницами/пачками
    opts.phase_cancelled = lambda ph: ph in job.skip_phases   # «крестики» фаз

    def target() -> None:
        root = logging.getLogger()
        handler = _JobLogHandler(job.log, thread_name)
        root.addHandler(handler)
        try:
            job.result = run_fetch(opts) if opts.fetch_only else run_pipeline(opts)
            job.log.append("=== ЗАВЕРШЕНО ===")
            job.status = "done"
        except FetchStopped as exc:
            job.error = str(exc)
            job.log.append(f"=== ОСТАНОВЛЕНО: {exc} ===")
            job.status = "stopped"
        except Exception as exc:  # показываем ошибку пользователю, не роняем сервер
            job.error = str(exc)
            job.log.append(f"=== ОШИБКА: {exc} ===")
            job.status = "error"
        finally:
            root.removeHandler(handler)

    threading.Thread(target=target, daemon=True, name=thread_name).start()
    with _LOCK:
        JOBS[job.id] = job
    return job.id


def _prune_jobs() -> None:
    """Не дать JOBS расти бесконечно: готовые задания храним последние N."""
    with _LOCK:
        finished = [j for j in JOBS.values() if j.status != "running"]
        excess = len(finished) - MAX_FINISHED_JOBS
        for job in finished[:max(0, excess)]:   # dict хранит порядок вставки
            JOBS.pop(job.id, None)


def get_job(job_id: str) -> Job | None:
    return JOBS.get(job_id)


def request_stop(job_id: str) -> bool:
    """Кнопка «Стоп»: True, если задание выгрузки и оно ещё идёт."""
    job = JOBS.get(job_id)
    if job is None or job.status != "running" or not job.opts.fetch_only:
        return False
    job.stop_event.set()
    return True


# фазы, которые можно отменить крестиком в процессе (задачи — только «Стоп»)
SKIPPABLE = ("changelog", "comments")


def request_skip(job_id: str, phase: str) -> bool:
    """Крестик у полосы фазы: fetch завершит фазу на ближайшей границе,
    остальные продолжатся. True, если команда принята."""
    if phase not in SKIPPABLE:
        return False
    job = JOBS.get(job_id)
    if job is None or job.status != "running" or not job.opts.fetch_only:
        return False
    with _LOCK:
        job.skip_phases.add(phase)
    return True


def _progress_setter(job: Job):
    def set_progress(phase: str, done: int, total: int | None,
                     status: str | None = None) -> None:
        with _LOCK:
            ph = job.phases.get(phase)
            if ph is None:
                ph = {"label": PHASE_LABELS.get(phase, phase),
                      "done": 0, "total": None, "status": "running"}
                job.phases[phase] = ph
            ph["done"] = done
            ph["total"] = total
            if status:
                ph["status"] = status
            job.progress = {"phase": ph["label"], "done": done, "total": total}
    return set_progress


def snapshot(job: Job) -> dict:
    opts = job.opts
    with _LOCK:
        phases = {p: dict(v) for p, v in job.phases.items()}
        skipped = set(job.skip_phases)
    return {
        "id": job.id,
        "status": job.status,
        "started": job.started,
        "error": job.error,
        "log": list(job.log),
        "progress": job.progress,
        # полосы фаз для web + какие крестики ещё доступны
        "phases": phases,
        "skippable": [p for p in SKIPPABLE if p not in skipped],
        "stoppable": job.status == "running" and opts.fetch_only,
        "fetch_only": opts.fetch_only,
        "report_ready": job.status == "done" and bool(job.result.get("report_dir")),
        "project": opts.project,
    }
