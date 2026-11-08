from core.insights.service import extract_suggestions
from core.scheduler import PeriodicJob

JOBS = [
    PeriodicJob(
        key="core.insights.extract",
        owner="core",
        handler=extract_suggestions,
        interval_seconds=600,
        timeout_seconds=300,
    ),
]
