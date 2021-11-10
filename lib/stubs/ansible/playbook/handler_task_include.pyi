from ansible.playbook.handler import Handler as Handler
from ansible.playbook.task_include import TaskInclude as TaskInclude

class HandlerTaskInclude(Handler, TaskInclude):
    ...
