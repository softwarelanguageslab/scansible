from __future__ import annotations

MAGIC_VAR_NAMES = frozenset(
    {
        # https://docs.ansible.com/ansible/latest/reference_appendices/special_variables.html#special-variables
        # and ansible/vars/manager.py#_get_magic_variables
        "ansible_check_mode",
        "ansible_config_file",
        "ansible_dependent_role_names",
        "ansible_diff_mode",
        "ansible_forks",
        "ansible_inventory_sources",
        "ansible_limit",
        "ansible_play_batch",
        "ansible_play_hosts",
        "ansible_play_hosts_all",
        "ansible_play_role_names",
        "ansible_playbook_python",
        "ansible_role_names",
        "ansible_role_name",
        "ansible_collection_name",
        "ansible_run_tags",
        "ansible_search_path",
        "ansible_skip_tags",
        "ansible_verbosity",
        "ansible_version",
        "groups",
        "hostvars",
        "omit",
        "play_hosts",
        "ansible_play_name",
        "playbook_dir",
        "role_name",
        "role_names",
        "role_path",
        # ansible/vars/manager.py#_get_magic_variables
        "role_uuid",
        # ansible/vars/manager.py#get_vars
        "environment",
        "vars",
        "ansible_delegated_vars",
        "_ansible_loop_cache",
        # There are only "magic" vars in the looped task itself, but don't exist
        # outside loops. In tasks inside a looped include, these are include
        # params, not magic vars. Regardless, we'll approximate them as magic
        # vars, because they probably shouldn't be set by the user anyway, and
        # even as include params, they still have very high precedence.
        "ansible_loop",
        "ansible_loop_var",
        "ansible_index_var",
        # Similarly, these are actually role include params, not magic vars,
        # but include params have the highest precedence anyway.
        "ansible_parent_role_names",
        "ansible_parent_role_paths",
        # These are in fact host vars, so much lower precedence than magic vars.
        # "group_names",
        # "inventory_hostname",
        # "inventory_hostname_short",
        # "inventory_dir",
        # "inventory_file",
    }
)

# Known host fact names that don't start with "ansible_"
UNQUALIFIED_HOST_FACT_NAMES = frozenset(
    {
        # See above, mentioned as magic vars, but are in fact host vars
        "group_names",
        "inventory_hostname",
        "inventory_hostname_short",
        "inventory_dir",
        "inventory_file",
    }
)
