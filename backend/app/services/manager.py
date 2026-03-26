from app.models import TaskState, TaskStatus


def build_plan(goal: str) -> list[str]:
    return [
        "Understand the requested outcome in plain language",
        "Create or update code in a safe feature branch",
        "Run tests and basic validation",
        "Prepare a beginner-friendly review summary",
    ]


def advance_task(task: TaskState) -> TaskState:
    if task.status == TaskStatus.PLANNING:
        task.status = TaskStatus.WORKING
        task.manager_notes = "Manager assigned coding and test subtasks."
        return task

    if task.status == TaskStatus.WORKING:
        task.status = TaskStatus.NEEDS_REVIEW
        task.changed_files = [
            "src/example_feature.ts",
            "tests/example_feature.test.ts",
        ]
        task.tests_status = "passing"
        task.manager_notes = "Code complete. Waiting for final manager review."
        return task

    if task.status == TaskStatus.NEEDS_REVIEW:
        task.status = TaskStatus.READY
        task.manager_notes = (
            "Ready to merge. Changes are isolated, tests pass, and summary is prepared."
        )
        return task

    return task
