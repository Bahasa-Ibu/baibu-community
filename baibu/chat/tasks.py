from celery import shared_task

from . import services


@shared_task(ignore_result=True)
def execute_run(run_id: str) -> str:
    run = services.execute(run_id)
    return run.status if run else "skipped"


@shared_task(ignore_result=True)
def sweep_runs() -> dict:
    return services.sweep_runs()
