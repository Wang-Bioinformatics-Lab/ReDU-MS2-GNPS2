from celery import Celery
import glob
import sys
import os

celery_instance = Celery('tasks', backend='redis://redu-gnps2-redis', broker='pyamqp://guest@redu-gnps2-rabbitmq//', )

@celery_instance.task(time_limit=60)
def task_computeheartbeat():
    print("UP", file=sys.stderr, flush=True)
    return "Up"


@celery_instance.task(time_limit=3600)
def tasks_generate_metadata():
    print("UP", file=sys.stderr, flush=True)

    cmd = "cd /app/workflows/PublicDataset_ReDU_Metadata_Workflow && \
        nextflow run ./nf_workflow.nf -resume \
        -c ./nextflow.config"
    
    os.system(cmd)
    
    return "Up"


# celery_instance.conf.beat_schedule = {
#     "cleanup": {
#         "task": "tasks.run_task",
#         "schedule": 3600
#     }
# }


celery_instance.conf.task_routes = {
    'tasks.task_computeheartbeat': {'queue': 'worker'},
    'tasks.tasks_generate_metadata': {'queue': 'worker'},
}