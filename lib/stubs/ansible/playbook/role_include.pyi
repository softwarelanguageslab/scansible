from __future__ import annotations

from ansible.playbook.task_include import TaskInclude

class IncludeRole(TaskInclude):
    allow_duplicates: bool = ...
    public: bool = ...
