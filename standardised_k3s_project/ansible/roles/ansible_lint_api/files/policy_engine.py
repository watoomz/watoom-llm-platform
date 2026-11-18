#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml
from jinja2 import Environment, TemplateAssertionError, TemplateSyntaxError, meta

SENSITIVE_NAME_RE = re.compile(
    r"\b(?:password|passwd|passphrase|secret|token|api[_-]?key|private[_-]?key|"
    r"client[_-]?secret|authorization|bearer|credential)\b", re.I
)
LITERAL_SECRET_KEY_RE = re.compile(
    r"^(?:password|passwd|passphrase|secret|token|api[_-]?key|private[_-]?key|"
    r"client[_-]?secret|authorization|bearer[_-]?token)$", re.I
)
JINJA_RE = re.compile(r"{{|{%")
VAULT_RE = re.compile(r"^\$ANSIBLE_VAULT;", re.I)
URL_AUTH_RE = re.compile(r"^https?://[^/\s:@]+:[^/@\s]+@", re.I)
SENSITIVE_PATH_RE = re.compile(
    r"(?:/etc/(?:shadow|sudoers|ssh/)|\.ssh/|\bprivate\b|\bsecret\b|\bcredential\b|\btoken\b|\bkey\b)", re.I
)


READONLY_INTENT_WORDS = {
    "check", "health", "audit", "validate", "validation", "verify",
    "readonly", "read_only", "compliance",
}

READONLY_COMMAND_ALLOWLIST = (
    re.compile(r"^ps\s+-eo\s+stat=?$", re.I),
)

FACTS_FIRST_PATTERNS = (
    (re.compile(r"(?:^|[/\s])uptime(?:\s|$)", re.I), "uptime information", "ansible.builtin.setup / ansible_facts.uptime_seconds"),
    (re.compile(r"(?:^|[/\s])uname\s+-r(?:\s|$)", re.I), "kernel version", "ansible.builtin.setup / ansible_facts.kernel"),
    (re.compile(r"(?:^|[/\s])free(?:\s|$)", re.I), "memory/swap usage information", "ansible.builtin.setup / ansible_facts.memory_mb and gathered swap facts, with percentages calculated in Jinja/set_fact"),
    (re.compile(r"(?:^|[/\s])getenforce(?:\s|$)", re.I), "SELinux state", "ansible.builtin.setup / ansible_facts.selinux"),
    (re.compile(r"\bsystemctl\b[^\n]*(?:is-active|is-enabled|status|show)\b[^\n]*\bfirewalld(?:\.service)?\b", re.I), "firewalld service state", "ansible.builtin.service_facts / ansible_facts.services"),
    (re.compile(r"\brpm\b[^\n]*(?:-qa\b|--query\s+--all\b)", re.I), "installed package information", "ansible.builtin.package_facts / ansible_facts.packages"),
    (re.compile(r"(?:^|[/\s])df(?:\s|$)", re.I), "filesystem usage information", "ansible.builtin.setup / ansible_facts.mounts, or ansible.builtin.mount_facts when supported"),
    (re.compile(r"(?:^|[/\s])ip\s+(?:addr|address|link|route)\b", re.I), "network interface/address/route information", "ansible.builtin.setup / gathered network facts"),
    (re.compile(r"(?:^|[/\s])hostname(?:\s|$)", re.I), "hostname information", "ansible.builtin.setup / ansible_facts.hostname or ansible_facts.fqdn"),
    (re.compile(r"(?:^|[/\s])(?:nproc|lscpu)(?:\s|$)", re.I), "processor information", "ansible.builtin.setup / gathered processor facts"),
)

MUTATING_COMMAND_PATTERNS = (
    (re.compile(r"\bsystemctl\s+(?:start|stop|restart|reload|enable|disable|mask|unmask)\b", re.I),
     "ansible.builtin.systemd_service/service"),
    (re.compile(r"\b(?:dnf|yum)\s+(?:install|remove|erase|update|upgrade)\b", re.I),
     "ansible.builtin.dnf/package"),
    (re.compile(r"\b(?:useradd|usermod|userdel)\b", re.I), "ansible.builtin.user"),
    (re.compile(r"\b(?:groupadd|groupmod|groupdel)\b", re.I), "ansible.builtin.group"),
    (re.compile(r"\b(?:mkdir|chmod|chown|touch)\b", re.I), "ansible.builtin.file"),
    (re.compile(r"\b(?:curl|wget)\b", re.I), "ansible.builtin.get_url/uri"),
    (re.compile(r"\bsysctl\s+-w\b", re.I), "ansible.posix.sysctl"),
    (re.compile(r"\b(?:mount|umount)\b", re.I), "ansible.posix.mount"),
    (re.compile(r"\bsed\s+-i\b|\btee\s+-a?\b|>>", re.I),
     "lineinfile/blockinfile/replace/template/copy"),
    (re.compile(r"\b(?:tar|unzip)\b", re.I), "ansible.builtin.unarchive"),
)

CONTROLLER_LOCALHOSTS = {"localhost", "127.0.0.1", "::1"}


SHELL_MARKERS = ("|", "&&", "||", ">", "<", ";", "$(", "`")
READONLY_WORDS = (
    "status", "show", "list", "get", "check", "query", "grep",
    "cat", "find", "rpm -q", "systemctl is-",
)
SHELL_PIPELINE_TOOLS = ("grep", "awk", "sed", "wc", "sort", "tail", "cut")
TASK_KEYWORDS = {
    "action", "args", "async", "become", "become_exe", "become_flags",
    "become_method", "become_user", "changed_when", "check_mode",
    "collections", "connection", "debugger", "delay", "delegate_facts",
    "delegate_to", "diff", "environment", "failed_when", "ignore_errors",
    "ignore_unreachable", "loop", "loop_control", "name", "no_log",
    "notify", "poll", "register", "remote_user", "retries", "run_once",
    "tags", "throttle", "timeout", "until", "vars", "when", "with_dict",
    "with_fileglob", "with_first_found", "with_items", "with_sequence",
    "with_subelements", "with_together",
}
STRUCTURAL_TASK_KEYS = (
    "block", "rescue", "always", "tasks", "pre_tasks", "post_tasks", "handlers"
)
IMPLICIT_JINJA_FIELDS = {"changed_when", "failed_when", "that", "until", "when"}
COMMON_ANSIBLE_FACT_KEYS = {
    "all_ipv4_addresses", "all_ipv6_addresses", "architecture", "bios_date",
    "bios_vendor", "bios_version", "board_asset_tag", "board_name",
    "board_serial", "board_vendor", "board_version", "chassis_asset_tag",
    "chassis_serial", "chassis_vendor", "chassis_version", "cmdline",
    "date_time", "default_ipv4", "default_ipv6", "devices", "distribution",
    "distribution_file_parsed", "distribution_file_path",
    "distribution_file_variety", "distribution_major_version",
    "distribution_release", "distribution_version", "dns", "domain",
    "effective_group_id", "effective_user_id", "env", "fibre_channel_wwn",
    "fips", "fqdn", "hostname", "interfaces", "is_chroot", "iscsi_iqn",
    "kernel", "kernel_version", "lo", "lsb", "machine", "machine_id",
    "memfree_mb", "memory_mb", "memtotal_mb", "mounts", "nodename",
    "os_family", "packages", "pkg_mgr", "processor", "processor_cores",
    "processor_count", "processor_nproc", "processor_threads_per_core",
    "processor_vcpus", "product_name", "product_serial", "product_uuid",
    "product_version", "python", "python_version", "real_group_id",
    "real_user_id", "selinux", "selinux_python_present", "service_mgr",
    "services", "system", "system_capabilities",
    "system_capabilities_enforced", "system_vendor", "uptime_seconds",
    "user_dir", "user_gecos", "user_gid", "user_id", "user_shell",
    "user_uid", "userspace_architecture", "userspace_bits",
    "virtualization_role", "virtualization_tech_guest",
    "virtualization_tech_host", "virtualization_type",
}
ANSIBLE_RUNTIME_VARS = {
    "ansible_check_mode", "ansible_config_file", "ansible_diff_mode",
    "ansible_facts", "ansible_parent_role_names", "ansible_parent_role_paths",
    "ansible_play_hosts", "ansible_play_hosts_all", "ansible_role_name",
    "ansible_version", "environment", "group_names", "groups", "hostvars",
    "inventory_hostname", "inventory_hostname_short", "lookup", "omit",
    "play_hosts", "q", "query", "role_path", "vars",
}

def finding(rel: str, task: str, severity: str, rule: str, message: str, category: str) -> dict[str, Any]:
    return {
        "file": rel,
        "task": task,
        "severity": severity,
        "rule": rule,
        "message": message,
        "category": category,
    }


def task_name(item: dict[str, Any]) -> str:
    value = item.get("name")
    return str(value) if value is not None else "unnamed task"


def canonical_module_name(module_name: Any) -> str | None:
    if not isinstance(module_name, str):
        return None
    name = module_name.strip()
    if not name:
        return None
    if " " in name:
        name = name.split(None, 1)[0]
    if name.startswith("ansible.legacy."):
        return "ansible.builtin." + name.rsplit(".", 1)[-1]
    if "." not in name:
        return "ansible.builtin." + name
    return name


def module_short_name(module_name: Any) -> str | None:
    canonical = canonical_module_name(module_name)
    if not canonical:
        return None
    return canonical.rsplit(".", 1)[-1]


def module_value(item: dict[str, Any], *names: str) -> Any:
    wanted = {canonical_module_name(name) for name in names}
    for key in item:
        if canonical_module_name(key) in wanted:
            return item[key]
    action_module = module_from_action(item.get("action"))
    if action_module in wanted:
        action_value = item.get("action")
        if isinstance(action_value, dict):
            short_name = module_short_name(action_module)
            return action_value.get(action_module) or action_value.get(short_name) or action_value
        return action_value
    return None


def uses_module(item: dict[str, Any], *names: str) -> bool:
    wanted = {canonical_module_name(name) for name in names}
    return any(module_name in wanted for module_name in task_module_keys(item))


def command_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return ""
    if isinstance(value.get("cmd"), str):
        return value["cmd"]
    if isinstance(value.get("argv"), list):
        return " ".join(str(x) for x in value["argv"])
    return ""


def _noop_plugin(value: Any = None, *args: Any, **kwargs: Any) -> Any:
    return value


_PLUGIN_REGISTRIES: dict[str, frozenset[str]] = {}
_PLUGIN_REGISTRY_ERRORS: dict[str, str] = {}


def _ansible_plugin_registry(
    plugin_type: str,
) -> tuple[frozenset[str] | None, str | None]:
    if plugin_type in _PLUGIN_REGISTRIES:
        return _PLUGIN_REGISTRIES[plugin_type], None
    if plugin_type in _PLUGIN_REGISTRY_ERRORS:
        return None, _PLUGIN_REGISTRY_ERRORS[plugin_type]

    ansible_doc = shutil.which("ansible-doc")
    if not ansible_doc:
        error = "ansible-doc is not installed or not on PATH"
        _PLUGIN_REGISTRY_ERRORS[plugin_type] = error
        return None, error

    try:
        # The production systemd unit intentionally makes /root read-only.
        # Ansible's default controller-local tmp is under ANSIBLE_HOME
        # (~/.ansible/tmp), so give this introspection subprocess its own
        # private writable controller-local temp directory instead of weakening
        # the service sandbox.
        with tempfile.TemporaryDirectory(
            prefix=f"watoom-ansible-doc-{plugin_type}-"
        ) as local_tmp:
            env = os.environ.copy()
            env["ANSIBLE_LOCAL_TEMP"] = local_tmp
            proc = subprocess.run(
                [ansible_doc, "-t", plugin_type, "-l"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
                env=env,
            )
    except Exception as exc:
        error = f"ansible-doc {plugin_type} discovery failed: {exc}"
        _PLUGIN_REGISTRY_ERRORS[plugin_type] = error
        return None, error

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        error = (
            f"ansible-doc {plugin_type} discovery failed with exit "
            f"{proc.returncode}: {detail}"
        )
        _PLUGIN_REGISTRY_ERRORS[plugin_type] = error
        return None, error

    plugins: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        name = line.split()[0]
        if not re.match(
            r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$",
            name,
        ):
            continue
        plugins.add(name)
        if name.startswith("ansible.builtin."):
            plugins.add(name.rsplit(".", 1)[-1])

    registry = frozenset(plugins)
    _PLUGIN_REGISTRIES[plugin_type] = registry
    return registry, None


def ansible_filter_registry() -> tuple[frozenset[str] | None, str | None]:
    return _ansible_plugin_registry("filter")


def ansible_test_registry() -> tuple[frozenset[str] | None, str | None]:
    return _ansible_plugin_registry("test")


def install_ansible_filter_placeholders(jinja_env: Environment) -> str | None:
    # Core Ansible filters used by this repository must remain parseable even if
    # ansible-doc plugin discovery is temporarily unavailable. Discovery errors are
    # still reported separately and are not silently ignored.
    for name in ("to_json", "from_json", "to_yaml", "from_yaml", "bool", "combine"):
        jinja_env.filters.setdefault(name, _noop_plugin)

    filters, error = ansible_filter_registry()
    if error:
        return error
    assert filters is not None
    for name in filters:
        jinja_env.filters.setdefault(name, _noop_plugin)
    return None


def install_ansible_test_placeholders(jinja_env: Environment) -> str | None:
    tests, error = ansible_test_registry()
    if error:
        return error
    assert tests is not None
    for name in tests:
        jinja_env.tests.setdefault(name, _noop_plugin)
    return None


def unknown_filter_name(exc: BaseException) -> str | None:
    match = re.search(r"No filter named ['\"]([^'\"]+)['\"]", str(exc))
    return match.group(1) if match else None


def unknown_test_name(exc: BaseException) -> str | None:
    match = re.search(r"No test named ['\"]([^'\"]+)['\"]", str(exc))
    return match.group(1) if match else None


def module_from_action(action: Any) -> str | None:
    if isinstance(action, str):
        return canonical_module_name(action)
    if isinstance(action, dict):
        if isinstance(action.get("module"), str):
            return canonical_module_name(action["module"])
        for key in action:
            if not isinstance(key, str):
                continue
            if key in TASK_KEYWORDS or key in STRUCTURAL_TASK_KEYS:
                continue
            return canonical_module_name(key)
    return None


def raw_task_module_keys(item: dict[str, Any]) -> list[str]:
    modules: list[str] = []
    for key in item:
        if not isinstance(key, str):
            continue
        if key in TASK_KEYWORDS or key in STRUCTURAL_TASK_KEYS:
            continue
        if key.startswith("with_"):
            continue
        modules.append(key)
    action_module = module_from_action(item.get("action"))
    if action_module:
        modules.append(action_module)
    return modules


def task_module_keys(item: dict[str, Any]) -> list[str]:
    modules: list[str] = []
    for key in raw_task_module_keys(item):
        canonical = canonical_module_name(key)
        if canonical:
            modules.append(canonical)
    return modules


def is_bare_module(module_name: str) -> bool:
    if not isinstance(module_name, str) or not module_name:
        return False
    if "{% raw %}{{{% endraw %}" in module_name or "{% raw %}}}{% endraw %}" in module_name:
        return False
    return "." not in module_name


def has_condition(item: dict[str, Any], key: str) -> bool:
    return key in item and item.get(key) is not None


def has_text_processing_pipeline(raw: str) -> bool:
    if "|" not in raw:
        return False
    tools = "|".join(re.escape(tool) for tool in SHELL_PIPELINE_TOOLS)
    return re.search(rf"\|\s*(?:{tools})\b", raw) is not None


def dict_keys(value: Any) -> set[str]:
    if not isinstance(value, dict):
        return set()
    return {key for key in value if isinstance(key, str)}


def role_aliases(role_name: Any) -> set[str]:
    if not isinstance(role_name, str) or not role_name.strip():
        return set()
    normalized = role_name.strip()
    return {
        normalized,
        normalized.split("/")[-1],
        normalized.split(".")[-1],
    }


@dataclass
class EvaluationContext:
    root: Path
    role_include_vars: dict[str, set[str]] = field(default_factory=dict)
    role_template_vars: dict[Path, dict[str, set[str]]] = field(default_factory=dict)
    role_registered_vars: dict[Path, set[str]] = field(default_factory=dict)
    role_set_fact_vars: dict[Path, set[str]] = field(default_factory=dict)

def readonly_command_is_allowlisted(raw: str) -> bool:
    normalized = " ".join(str(raw).strip().split())
    return any(pattern.fullmatch(normalized) for pattern in READONLY_COMMAND_ALLOWLIST)


def add_facts_first_finding(findings: list[dict[str, Any]], rel: str, item: dict[str, Any], raw: str, module_name: str) -> bool:
    for pattern, description, preferred in FACTS_FIRST_PATTERNS:
        if pattern.search(raw):
            add(findings, rel, item, "error", "facts-first-known-data",
                f"Read-only {description} is being collected with ansible.builtin.{module_name}, but a native Ansible fact/info source is available. Use {preferred}. command/shell is not permitted for this datum in a read-only/check-intent role.",
                "correctness")
            return True
    return False



def walk_items(data: Any) -> Iterable[dict[str, Any]]:
    docs = data if isinstance(data, list) else [data]
    for item in docs:
        if isinstance(item, list):
            yield from walk_items(item)
            continue
        if not isinstance(item, dict):
            continue
        yield item
        for key in ("block", "rescue", "always"):
            child = item.get(key)
            if isinstance(child, list):
                yield from walk_items(child)



def role_root_for_path(path: Path) -> Path | None:
    if path.parent.name in ("tasks", "handlers", "templates", "defaults", "vars", "meta"):
        return path.parent.parent

    parts = path.parts
    if "roles" in parts:
        idx = parts.index("roles")
        if idx + 1 < len(parts):
            return Path(*parts[: idx + 2])

    if "templates" in parts:
        idx = parts.index("templates")
        if idx > 0:
            return Path(*parts[:idx])

    return None


def split_intent_tokens(value: str) -> set[str]:
    return {token for token in re.split(r"[^a-z0-9_]+", value.lower()) if token}


def has_readonly_intent(role_root: Path | None) -> bool:
    if role_root is None:
        return False

    role_name = role_root.name.lower()
    tokens = split_intent_tokens(role_name)
    if any(word in role_name or word in tokens for word in READONLY_INTENT_WORDS):
        return True

    for filename in ("main.yml", "main.yaml"):
        meta = role_root / "meta" / filename
        if not meta.exists():
            continue
        try:
            data = yaml.safe_load(meta.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        tags: list[str] = []
        galaxy_info = data.get("galaxy_info")
        if isinstance(galaxy_info, dict) and isinstance(galaxy_info.get("galaxy_tags"), list):
            tags.extend(str(tag).lower() for tag in galaxy_info["galaxy_tags"])
        if isinstance(data.get("tags"), list):
            tags.extend(str(tag).lower() for tag in data["tags"])
        if any(tag in READONLY_INTENT_WORDS for tag in tags):
            return True

    return False


def is_ansible_task_context(path: Path, data: Any) -> bool:
    """Return True only for YAML that can actually contain Ansible tasks.

    Whole-repository checks still inspect every YAML document for generic policy
    issues such as literal secrets. Task/module/Jinja task rules are restricted to
    role task/handler files and real playbooks so Kubernetes/Compose/config YAML is
    never interpreted as an Ansible task.
    """
    if path.parent.name in ("tasks", "handlers") and "roles" in path.parts:
        return True
    if "playbooks" in path.parts:
        return (
            isinstance(data, list)
            and any(
                isinstance(item, dict)
                and ("hosts" in item or "import_playbook" in item)
                for item in data
            )
        )
    return False


def walk_tasks(path: Path, data: Any) -> Iterable[dict[str, Any]]:
    if path.parent.name in ("defaults", "vars", "meta", "templates"):
        return
    is_playbook = (
        isinstance(data, list)
        and any(isinstance(x, dict) and ("hosts" in x or "import_playbook" in x) for x in data)
    )
    if is_playbook:
        for play in data:
            if not isinstance(play, dict):
                continue
            for key in ("pre_tasks", "tasks", "post_tasks", "handlers"):
                child = play.get(key)
                if isinstance(child, list):
                    yield from walk_items(child)
        return
    yield from walk_items(data)


def iter_key_values(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_s = str(key)
            dotted = f"{prefix}.{key_s}" if prefix else key_s
            yield dotted, child
            yield from iter_key_values(child, dotted)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            dotted = f"{prefix}[{i}]"
            yield dotted, child
            yield from iter_key_values(child, dotted)


def literal_secret(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v or JINJA_RE.search(v) or VAULT_RE.search(v):
        return False
    if v.lower() in {"omit", "none", "null", "changeme", "example", "example-only"}:
        return False
    return True


def sensitive_reference(value: Any) -> bool:
    try:
        raw = json.dumps(value)
    except Exception:
        raw = str(value)
    return bool(SENSITIVE_NAME_RE.search(raw))


def add(findings: list[dict[str, Any]], rel: str, item: dict[str, Any], severity: str,
        rule: str, message: str, category: str) -> None:
    findings.append(finding(rel, task_name(item), severity, rule, message, category))



def add_role_include_vars(ctx: EvaluationContext, role_name: Any, vars_dict: Any) -> None:
    names = dict_keys(vars_dict)
    if not names:
        return
    for alias in role_aliases(role_name):
        ctx.role_include_vars.setdefault(alias, set()).update(names)


def add_role_template_vars(
    ctx: EvaluationContext,
    role_root: Path,
    src: Any,
    vars_dict: Any,
) -> None:
    names = dict_keys(vars_dict)
    if not names or not src:
        return
    src_s = str(src).replace("\\", "/")
    bucket = ctx.role_template_vars.setdefault(role_root, {})
    bucket.setdefault(src_s, set()).update(names)
    bucket.setdefault(Path(src_s).name, set()).update(names)


def add_role_registered_var(
    ctx: EvaluationContext,
    role_root: Path,
    item: dict[str, Any],
) -> None:
    register_name = item.get("register")
    if isinstance(register_name, str) and register_name.strip():
        ctx.role_registered_vars.setdefault(role_root, set()).add(register_name.strip())


def add_role_set_fact_vars(
    ctx: EvaluationContext,
    role_root: Path,
    item: dict[str, Any],
) -> None:
    if not uses_module(item, "set_fact"):
        return
    value = module_value(item, "set_fact")
    names = dict_keys(value) - {"cacheable"}
    if names:
        ctx.role_set_fact_vars.setdefault(role_root, set()).update(names)


def collect_explicit_vars(
    ctx: EvaluationContext,
    path: Path,
    data: Any,
) -> None:
    role_root = role_root_for_path(path)
    for item in walk_items(data):
        roles_value = item.get("roles")
        for role_entry in roles_value if isinstance(roles_value, list) else []:
            if isinstance(role_entry, str) or not isinstance(role_entry, dict):
                continue
            role_name = role_entry.get("role") or role_entry.get("name")
            explicit_vars = dict_keys(role_entry.get("vars"))
            for key, value in role_entry.items():
                if (
                    key not in TASK_KEYWORDS
                    and key not in ("role", "name", "vars")
                    and isinstance(value, (str, int, float, bool, list, dict))
                ):
                    explicit_vars.add(key)
            add_role_include_vars(
                ctx,
                role_name,
                {name: True for name in explicit_vars},
            )

        for include_key in (
            "include_role",
            "import_role",
            "ansible.builtin.include_role",
            "ansible.builtin.import_role",
        ):
            include_value = item.get(include_key)
            if isinstance(include_value, dict):
                add_role_include_vars(
                    ctx,
                    include_value.get("name"),
                    item.get("vars"),
                )

        if role_root is None:
            continue

        add_role_registered_var(ctx, role_root, item)
        add_role_set_fact_vars(ctx, role_root, item)

        template_value = module_value(item, "template")
        if isinstance(template_value, dict):
            add_role_template_vars(
                ctx,
                role_root,
                template_value.get("src"),
                item.get("vars"),
            )


def role_vars(ctx: EvaluationContext, role_root: Path) -> set[str]:
    names: set[str] = set()
    for var_dir in ("defaults", "vars"):
        for filename in ("main.yml", "main.yaml"):
            path = role_root / var_dir / filename
            if not path.exists():
                continue
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            names.update(dict_keys(data))

    role_name = role_root.name
    names.update(ctx.role_include_vars.get(role_name, set()))
    names.update(ctx.role_include_vars.get(role_name.split(".")[-1], set()))
    names.update(ctx.role_registered_vars.get(role_root, set()))
    names.update(ctx.role_set_fact_vars.get(role_root, set()))
    names.update(ANSIBLE_RUNTIME_VARS)
    return names


def template_vars_for_path(
    ctx: EvaluationContext,
    role_root: Path,
    template_path: Path,
) -> set[str]:
    bucket = ctx.role_template_vars.get(role_root, {})
    try:
        rel = template_path.relative_to(role_root / "templates").as_posix()
    except ValueError:
        rel = template_path.name
    return set(bucket.get(rel, set())) | set(bucket.get(template_path.name, set()))


def local_task_vars(item: dict[str, Any]) -> set[str]:
    names = dict_keys(item.get("vars"))
    if any(
        key in item
        for key in (
            "loop",
            "with_dict",
            "with_fileglob",
            "with_first_found",
            "with_items",
            "with_sequence",
            "with_subelements",
            "with_together",
        )
    ):
        names.add("item")
    loop_control = item.get("loop_control")
    if isinstance(loop_control, dict) and isinstance(loop_control.get("loop_var"), str):
        names.add(loop_control["loop_var"])
    return names


def ansible_fact_keys(raw: str) -> set[str]:
    keys: set[str] = set()
    for match in re.finditer(
        r"ansible_facts\s*(?:\[\s*['\"]([A-Za-z0-9_]+)['\"]\s*\]|\.([A-Za-z_][A-Za-z0-9_]*))",
        raw,
    ):
        keys.add(match.group(1) or match.group(2))
    return keys


def add_ansible_fact_findings(
    findings: list[dict[str, Any]],
    raw: str,
    rel: str,
    task: str,
) -> None:
    for fact_key in sorted(ansible_fact_keys(raw)):
        if fact_key in COMMON_ANSIBLE_FACT_KEYS:
            continue
        findings.append(
            finding(
                rel,
                task,
                "error",
                "service-facts-reference",
                (
                    f"Reference to ansible_facts['{fact_key}'] is not a known common "
                    "Ansible fact key. Use documented fact structures such as "
                    "ansible_facts.services or ansible_facts.packages, or "
                    "register/set_fact a role variable instead of inventing "
                    "ansible_facts keys."
                ),
                "correctness",
            )
        )


def jinja_vars(
    jinja_env: Environment,
    raw: str,
    *,
    parse_as_expression: bool = False,
) -> set[str]:
    source = raw
    if parse_as_expression and "{{" not in raw and "{%" not in raw:
        source = "{{ " + raw + " }}"
    ast = jinja_env.parse(source)
    return meta.find_undeclared_variables(ast)


def add_inline_jinja_findings(
    findings: list[dict[str, Any]],
    jinja_env: Environment,
    value: Any,
    rel: str,
    task: str,
    defined_vars: set[str],
    parent_key: str | None = None,
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            add_inline_jinja_findings(
                findings,
                jinja_env,
                child,
                rel,
                task,
                defined_vars,
                key if isinstance(key, str) else parent_key,
            )
        return

    if isinstance(value, list):
        for child in value:
            add_inline_jinja_findings(
                findings,
                jinja_env,
                child,
                rel,
                task,
                defined_vars,
                parent_key,
            )
        return

    if not isinstance(value, str):
        return

    has_explicit_jinja = "{{" in value or "{%" in value
    parse_as_expression = parent_key in IMPLICIT_JINJA_FIELDS
    if not has_explicit_jinja and not parse_as_expression:
        return

    try:
        used_vars = jinja_vars(
            jinja_env,
            value,
            parse_as_expression=parse_as_expression,
        )
    except TemplateAssertionError as exc:
        filter_name = unknown_filter_name(exc)
        test_name = unknown_test_name(exc)
        if filter_name:
            findings.append(
                finding(
                    rel,
                    task,
                    "error",
                    "unknown-ansible-filter",
                    (
                        f"Jinja expression references filter '{filter_name}', but "
                        "that filter plugin cannot be resolved in the validation "
                        "environment. Use a valid installed filter FQCN or short "
                        "name confirmed by ansible-doc -t filter."
                    ),
                    "jinja",
                )
            )
        elif test_name:
            findings.append(
                finding(
                    rel,
                    task,
                    "error",
                    "unknown-ansible-test",
                    (
                        f"Jinja expression references test '{test_name}', but "
                        "that test plugin cannot be resolved in the validation "
                        "environment. Use a valid installed test FQCN or short "
                        "name confirmed by ansible-doc -t test."
                    ),
                    "jinja",
                )
            )
        else:
            findings.append(
                finding(
                    rel,
                    task,
                    "error",
                    "inline-jinja-parse",
                    f"Could not parse inline Jinja expression: {exc}",
                    "jinja",
                )
            )
        return
    except TemplateSyntaxError as exc:
        findings.append(
            finding(
                rel,
                task,
                "error",
                "inline-jinja-parse",
                f"Could not parse inline Jinja expression: {exc}",
                "jinja",
            )
        )
        return
    except Exception as exc:
        findings.append(
            finding(
                rel,
                task,
                "error",
                "inline-jinja-parse",
                f"Could not parse inline Jinja expression: {exc}",
                "jinja",
            )
        )
        return

    for var_name in sorted(var for var in used_vars if var not in defined_vars):
        findings.append(
            finding(
                rel,
                task,
                "error",
                "undefined-template-variable",
                (
                    f"Inline task Jinja references '{var_name}', but it is not "
                    "defined in role defaults/main.yml, vars/main.yml, role "
                    "include/import vars, registered vars, set_fact vars, loop "
                    "vars, task vars, or Ansible runtime vars."
                ),
                "correctness",
            )
        )

    add_ansible_fact_findings(findings, value, rel, task)


def setup_runtime_vars_for_task(
    items: list[dict[str, Any]],
    index: int,
) -> set[str]:
    for prior in items[:index]:
        if not uses_module(prior, "setup"):
            continue
        if prior.get("delegate_to") is not None or prior.get("run_once") is True:
            continue
        return {"ansible_date_time"}
    return set()


def role_fact_provider_state(
    parsed_yaml_files: list[tuple[Path, str, Any]],
) -> dict[str, dict[str, bool]]:
    providers: dict[str, dict[str, bool]] = {}

    for path, _rel, data in parsed_yaml_files:
        role_root = role_root_for_path(path)
        if role_root is None:
            continue

        state = providers.setdefault(
            str(role_root),
            {
                "service_facts": False,
                "package_facts": False,
            },
        )

        if not is_ansible_task_context(path, data):
            continue

        for item in walk_tasks(path, data):
            if uses_module(item, "service_facts"):
                state["service_facts"] = True
            if uses_module(item, "package_facts"):
                state["package_facts"] = True

    return providers


def add_fact_provider_findings(
    findings: list[dict[str, Any]],
    raw: str,
    rel: str,
    task: str,
    role_root: Path | None,
    provider_state: dict[str, dict[str, bool]],
) -> None:
    if role_root is None:
        return

    state = provider_state.get(
        str(role_root),
        {
            "service_facts": False,
            "package_facts": False,
        },
    )

    checks = (
        (
            "services",
            "service_facts",
            re.compile(
                r"ansible_facts\s*(?:\[\s*['\"]services['\"]\s*\]|\.services\b)"
            ),
            (
                "ansible_facts.services is referenced but "
                "ansible.builtin.service_facts is not collected in this role. "
                "setup does not provide service facts."
            ),
        ),
        (
            "packages",
            "package_facts",
            re.compile(
                r"ansible_facts\s*(?:\[\s*['\"]packages['\"]\s*\]|\.packages\b)"
            ),
            (
                "ansible_facts.packages is referenced but "
                "ansible.builtin.package_facts is not collected in this role. "
                "setup does not provide package facts."
            ),
        ),
    )

    for _fact_name, provider_key, pattern, message in checks:
        if pattern.search(raw) and not state[provider_key]:
            findings.append(
                finding(
                    rel,
                    task,
                    "error",
                    "fact-provider-not-collected",
                    message,
                    "correctness",
                )
            )


def add_fact_provider_order_findings(
    findings: list[dict[str, Any]],
    path: Path,
    rel: str,
    data: Any,
) -> None:
    role_root = role_root_for_path(path)
    if role_root is None:
        return

    items = list(walk_tasks(path, data))
    provider_positions: dict[str, list[int]] = {
        "services": [],
        "packages": [],
    }

    for index, item in enumerate(items):
        if uses_module(item, "service_facts"):
            provider_positions["services"].append(index)
        if uses_module(item, "package_facts"):
            provider_positions["packages"].append(index)

    checks = (
        (
            "services",
            re.compile(
                r"ansible_facts\s*(?:\[\s*['\"]services['\"]\s*\]|\.services\b)"
            ),
            "ansible.builtin.service_facts",
        ),
        (
            "packages",
            re.compile(
                r"ansible_facts\s*(?:\[\s*['\"]packages['\"]\s*\]|\.packages\b)"
            ),
            "ansible.builtin.package_facts",
        ),
    )

    for index, item in enumerate(items):
        raw = json.dumps(item)
        for fact_name, pattern, provider_module in checks:
            if not pattern.search(raw):
                continue
            positions = provider_positions[fact_name]
            if not positions:
                continue
            if min(positions) > index:
                findings.append(
                    finding(
                        rel,
                        task_name(item),
                        "error",
                        "fact-provider-must-precede-use",
                        (
                            f"ansible_facts.{fact_name} is referenced before "
                            f"{provider_module} executes in this task file. Move "
                            "the fact provider before the first consumer so the "
                            "fact exists when referenced."
                        ),
                        "correctness",
                    )
                )


def add_host_fact_scope_findings(
    findings: list[dict[str, Any]],
    rel: str,
    item: dict[str, Any],
    readonly_intent: bool,
) -> None:
    if not readonly_intent:
        return

    host_fact_modules = (
        "setup",
        "package_facts",
        "service_facts",
        "mount_facts",
    )
    module_name = next(
        (name for name in host_fact_modules if uses_module(item, name)),
        None,
    )
    if module_name is None:
        return

    delegate_to = item.get("delegate_to")
    delegated_local = (
        isinstance(delegate_to, str)
        and delegate_to.strip().lower() in CONTROLLER_LOCALHOSTS
    )
    run_once = item.get("run_once") is True
    if not delegated_local and not run_once:
        return

    problems: list[str] = []
    if delegated_local:
        problems.append(f"delegate_to: {delegate_to}")
    if run_once:
        problems.append("run_once: true")

    add(
        findings,
        rel,
        item,
        "error",
        "host-facts-must-run-on-target",
        (
            f"ansible.builtin.{module_name} collects facts about the host where "
            "the module executes. Host health facts must be collected on each "
            f"managed inventory host; remove {', '.join(problems)}. Delegate only "
            "controller-side/API work, not managed-host fact collection."
        ),
        "execution-scope",
    )

def check_all_yaml_for_literal_secrets(rel: str, data: Any, findings: list[dict[str, Any]]) -> None:
    for dotted, value in iter_key_values(data):
        leaf = dotted.rsplit(".", 1)[-1]
        if "[" in leaf:
            continue
        if LITERAL_SECRET_KEY_RE.match(leaf) and literal_secret(value):
            findings.append(finding(
                rel, "file variables", "error", "literal-secret-value",
                f"Sensitive field '{dotted}' contains a literal value. Use an AAP credential, external secret store, Ansible Vault, or a variable reference.",
                "security",
            ))


def contains_explicit_jinja_delimiters(value: Any) -> bool:
    if isinstance(value, str):
        return "{{" in value or "{%" in value
    if isinstance(value, list):
        return any(contains_explicit_jinja_delimiters(item) for item in value)
    return False


def add_conditional_jinja_delimiter_findings(
    rel: str,
    item: dict[str, Any],
    findings: list[dict[str, Any]],
) -> None:
    conditional_values: list[tuple[str, Any]] = [
        (key, item.get(key))
        for key in ("when", "changed_when", "failed_when", "until")
        if key in item
    ]

    assert_value = module_value(item, "assert")
    if isinstance(assert_value, dict) and "that" in assert_value:
        conditional_values.append(
            ("ansible.builtin.assert.that", assert_value.get("that"))
        )

    for field_name, value in conditional_values:
        if not contains_explicit_jinja_delimiters(value):
            continue
        add(
            findings,
            rel,
            item,
            "error",
            "conditional-jinja-delimiters",
            (
                f"{field_name} is a raw Ansible conditional expression and must "
                "not be wrapped in Jinja template delimiters. Use the expression "
                "directly, for example failed_when: result.rc != 0."
            ),
            "correctness",
        )


def check_task(rel: str, item: dict[str, Any], findings: list[dict[str, Any]], is_handler_file: bool = False, readonly_intent: bool = False) -> None:
    add_conditional_jinja_delimiter_findings(rel, item, findings)
    # Original server.py static rules now owned by the policy engine.
    for module_name in raw_task_module_keys(item):
        if is_bare_module(module_name):
            add(
                findings,
                rel,
                item,
                "error",
                "fqcn-module-name",
                (
                    f"Task uses bare module/action name '{module_name}'. Use the "
                    "fully qualified collection name, for example "
                    f"ansible.builtin.{module_name} for built-in modules."
                ),
                "correctness",
            )

    if uses_module(item, "command", "shell"):
        missing = [
            key
            for key in ("changed_when", "failed_when")
            if not has_condition(item, key)
        ]
        if missing:
            module_name = "shell" if uses_module(item, "shell") else "command"
            add(
                findings,
                rel,
                item,
                "error",
                "command-shell-outcome-guards",
                (
                    f"ansible.builtin.{module_name} task is missing "
                    f"{', '.join(missing)}. Add explicit changed_when and "
                    "failed_when so command outcome semantics are deterministic."
                ),
                "correctness",
            )

    command_value = module_value(item, "command")
    if command_value is not None:
        raw_command = command_text(command_value) or json.dumps(command_value)
        if any(marker in raw_command for marker in SHELL_MARKERS):
            add(
                findings,
                rel,
                item,
                "error",
                "command-shell-metacharacters",
                (
                    "ansible.builtin.command cannot process shell metacharacters. "
                    "For read-only inspection, first replace the pipeline with an "
                    "appropriate Ansible facts/info module or "
                    "ansible.builtin.command with argv followed by Ansible/Jinja "
                    "processing. Do not convert this task to ansible.builtin.shell "
                    "unless shell semantics are genuinely unavoidable."
                ),
                "correctness",
            )
        if (
            any(word in raw_command.lower() for word in READONLY_WORDS)
            and item.get("changed_when") is None
        ):
            add(
                findings,
                rel,
                item,
                "warning",
                "read-only-command-changed-when",
                "Read-only command/status checks should normally include changed_when: false.",
                "idempotency",
            )

    shell_value = module_value(item, "shell")
    if shell_value is not None:
        raw_shell = command_text(shell_value) or json.dumps(shell_value)
        if readonly_intent and has_text_processing_pipeline(raw_shell):
            add(
                findings,
                rel,
                item,
                "error",
                "shell-pipeline-in-readonly-check",
                (
                    "Read-only/check-intent roles must eliminate the shell pipeline "
                    "instead of moving command syntax into ansible.builtin.shell. "
                    "Prefer Ansible facts/modules, ansible.builtin.command with argv, "
                    "or Jinja/set_fact post-processing of simpler command output."
                ),
                "correctness",
            )
        if (
            any(word in raw_shell.lower() for word in READONLY_WORDS)
            and item.get("changed_when") is None
        ):
            add(
                findings,
                rel,
                item,
                "warning",
                "read-only-shell-changed-when",
                "Read-only shell/status checks should normally include changed_when: false.",
                "idempotency",
            )

    add_host_fact_scope_findings(
        findings,
        rel,
        item,
        readonly_intent,
    )

    # Sensitive debug output.
    debug = module_value(item, "debug")
    if debug is not None and sensitive_reference(debug):
        add(findings, rel, item, "error", "sensitive-debug-output",
            "Debug output references a value that appears sensitive. Do not print secrets, credentials, tokens, private keys, Authorization headers, or broad secret-bearing structures.",
            "security")

    # Sensitive command/shell/API operations should suppress argument/result logging.
    if sensitive_reference(item) and not uses_module(item, "debug"):
        if uses_module(item, "command", "shell", "uri", "get_url") and item.get("no_log") is not True:
            add(findings, rel, item, "error", "sensitive-task-missing-no-log",
                "Task appears to consume sensitive data and may expose arguments or responses in AAP job output. Set no_log: true or use a credential-aware module/plugin.",
                "security")

    # Sensitive file content should not appear in --diff output.
    if uses_module(item, "template", "copy", "lineinfile", "blockinfile"):
        if (sensitive_reference(item) or SENSITIVE_PATH_RE.search(json.dumps(item))) and item.get("diff") is not False:
            add(findings, rel, item, "warning", "sensitive-diff-enabled",
                "Task appears to manage sensitive content/path but does not set diff: false; diff output can expose secret material.",
                "security")

    # TLS, URL credentials, plaintext auth.
    for mod in ("uri", "get_url"):
        value = module_value(item, mod)
        if not isinstance(value, dict):
            continue
        if value.get("validate_certs") is False:
            add(findings, rel, item, "error", "tls-validation-disabled",
                f"ansible.builtin.{mod} disables TLS certificate validation. Install/trust the correct CA instead of validate_certs: false.",
                "security")
        url = value.get("url")
        if isinstance(url, str):
            if URL_AUTH_RE.search(url):
                add(findings, rel, item, "error", "credentials-in-url",
                    "URL embeds credentials. Use module authentication parameters backed by AAP credentials/secret variables.",
                    "security")
            if url.lower().startswith("http://") and sensitive_reference(value):
                add(findings, rel, item, "error", "plaintext-auth-transport",
                    "Sensitive authentication material is being sent over plaintext HTTP.",
                    "security")

    # unsafe_writes.
    for mod in ("template", "copy", "file", "lineinfile", "blockinfile", "replace", "get_url"):
        value = module_value(item, mod)
        if isinstance(value, dict) and value.get("unsafe_writes") is True:
            add(findings, rel, item, "error", "unsafe-writes-enabled",
                f"ansible.builtin.{mod} enables unsafe_writes. Require an explicit human-reviewed waiver if atomic writes are genuinely impossible.",
                "security")

    # Download integrity.
    get_url = module_value(item, "get_url")
    if isinstance(get_url, dict) and not get_url.get("checksum"):
        dest = str(get_url.get("dest", ""))
        sev = "error" if re.search(r"\.(?:sh|py|pl|rb|rpm|deb|bin|run|tar|tgz|gz|zip)$", dest, re.I) else "warning"
        add(findings, rel, item, sev, "external-download-no-integrity",
            "External download has no checksum. Pin and verify downloaded content before installation or execution.",
            "supply-chain")

    # AAP: timed pause only.
    pause = module_value(item, "pause")
    if pause is not None:
        timed = isinstance(pause, dict) and (pause.get("seconds") is not None or pause.get("minutes") is not None)
        if not timed:
            add(findings, rel, item, "error", "aap-pause-requires-timeout",
                "Interactive pause is not suitable for AAP. Use a timed pause or redesign the workflow.",
                "aap")

    # AAP localhost semantics / cwd assumptions.
    delegate = item.get("delegate_to")
    delegated_local = isinstance(delegate, str) and delegate.strip().lower() in CONTROLLER_LOCALHOSTS
    if delegated_local:
        raw = json.dumps(item)
        if re.search(r'(?:"|\')\./[^"\']+', raw) and "playbook_dir" not in raw:
            add(findings, rel, item, "error", "aap-cwd-assumption",
                "Controller-side task uses an implicit relative path. AAP localhost is the execution environment; anchor project resources with playbook_dir.",
                "aap")
        if re.search(r'(?:"|\')/(?:opt|usr/local|home|root)/', raw) and "playbook_dir" not in raw:
            add(findings, rel, item, "warning", "controller-host-path-assumption",
                "Delegated localhost task references a host-style absolute path. In AAP, localhost is the execution environment, not the physical controller host.",
                "aap")

    # Runtime include/import from arbitrary controller filesystem.
    for key in (
        "include_tasks", "import_tasks", "include_vars", "import_playbook",
        "ansible.builtin.include_tasks", "ansible.builtin.import_tasks",
        "ansible.builtin.include_vars", "ansible.builtin.import_playbook",
    ):
        value = item.get(key)
        if isinstance(value, str) and value.startswith(("/opt/", "/usr/local/", "/home/", "/root/")):
            add(findings, rel, item, "error", "aap-runtime-external-path",
                f"{key} loads runtime content from '{value}'. Package it in the project/collection/EE instead of relying on arbitrary filesystem paths.",
                "aap")

    setup = module_value(item, "setup")
    if readonly_intent and isinstance(setup, dict) and setup.get("fact_path") is not None:
        add(findings, rel, item, "error", "readonly-setup-fact-path",
            "ansible.builtin.setup fact_path does not save gathered facts to that directory; it tells setup where to read custom local *.fact files on the managed host. Remove fact_path for ordinary read-only health/audit fact collection.",
            "correctness")

    # Prefer native fact/info sources for known read-only data in check/audit roles, then deny unknown commands by default.
    command = module_value(item, "command", "shell")
    if readonly_intent and command is not None:
        raw = command_text(command) or json.dumps(command)
        if uses_module(item, "shell"):
            add_facts_first_finding(findings, rel, item, raw, "shell")
            add(findings, rel, item, "error", "readonly-shell-not-permitted",
                "Read-only/check-intent roles may not use ansible.builtin.shell for data collection. Prefer setup facts, *_facts, *_info, stat, package_facts, service_facts, mount_facts, native modules, or request a centrally reviewed command allowlist entry when no native source exists.",
                "correctness")
        else:
            facts_first_added = add_facts_first_finding(findings, rel, item, raw, "command")
            if not facts_first_added and not readonly_command_is_allowlisted(raw):
                add(findings, rel, item, "error", "readonly-command-not-allowlisted",
                    "Read-only/check-intent roles are deny-by-default for ansible.builtin.command. Prefer setup facts, *_facts, *_info, stat, service_facts, package_facts, mount_facts, or another native read-only module. This command is not in the human-controlled command allowlist. Do not replace it with ansible.builtin.shell.",
                    "correctness")

    # Mutating command/shell semantics.
    if command is not None:
        raw = command_text(command) or json.dumps(command)
        for pattern, preferred in MUTATING_COMMAND_PATTERNS:
            if not pattern.search(raw):
                continue
            if item.get("changed_when") is False:
                add(findings, rel, item, "error", "mutating-command-false-changed",
                    "Known mutating command is forced to changed_when: false, hiding real state changes. Use truthful change detection or a native idempotent module.",
                    "idempotency")
            value_dict = command if isinstance(command, dict) else {}
            args = item.get("args") if isinstance(item.get("args"), dict) else {}
            guarded = any(k in value_dict or k in args for k in ("creates", "removes"))
            if not guarded and item.get("changed_when") in (None, False):
                add(findings, rel, item, "error", "mutating-command-not-idempotent",
                    f"Known mutating command lacks a reliable idempotence guard. Prefer {preferred} or implement deterministic state/change detection.",
                    "idempotency")
            break

    # Failure suppression.
    if item.get("failed_when") is False and uses_module(item, "command", "shell", "uri", "get_url"):
        add(findings, rel, item, "error", "unconditional-failure-suppression",
            "Task unconditionally suppresses failure with failed_when: false. Express the expected return/success conditions explicitly.",
            "correctness")
    if item.get("ignore_unreachable") is True:
        add(findings, rel, item, "warning", "ignore-unreachable-production",
            "ignore_unreachable: true can hide inventory/network failures; use only with an explicit reviewed recovery design.",
            "correctness")
    if isinstance(item.get("failed_when"), list) and len(item["failed_when"]) > 1:
        add(findings, rel, item, "warning", "ambiguous-failed-when-list",
            "failed_when is a YAML list, whose entries are ANDed by Ansible. Use one explicit boolean expression when OR semantics are required.",
            "correctness")

    # Restart/reload should normally be a handler.
    for mod in ("service", "systemd", "systemd_service"):
        value = module_value(item, mod)
        if isinstance(value, dict) and value.get("state") in ("restarted", "reloaded") and not is_handler_file:
            add(findings, rel, item, "warning", "direct-restart-outside-handler",
                "Service restart/reload occurs in an ordinary task. Prefer notify + handler so restart occurs only when configuration changes.",
                "idempotency")

    # Delegated write concurrency.
    if isinstance(delegate, str):
        mutating = any(uses_module(item, m) for m in (
            "copy", "template", "file", "lineinfile", "blockinfile", "replace",
            "service", "systemd", "systemd_service", "uri", "command", "shell",
        ))
        serialized = item.get("run_once") is True or item.get("throttle") == 1
        if mutating and not serialized:
            add(findings, rel, item, "warning", "delegated-write-concurrency",
                "Mutating delegated task may execute concurrently once per inventory host. Serialize it or prove concurrent writes are safe.",
                "execution-scope")

    # run_once + per-host facts.
    if item.get("run_once") is True:
        raw = json.dumps(item)
        host_fact_re = re.compile(
            r"ansible_facts\s*(?:\[\s*['\"](?:services|packages|mounts|interfaces|uptime_seconds|selinux)['\"]\s*\]|"
            r"\.(?:services|packages|mounts|interfaces|uptime_seconds|selinux)\b)"
        )
        if host_fact_re.search(raw):
            add(findings, rel, item, "error", "run-once-host-specific-data",
                "run_once task consumes host-specific facts; one host's data would be treated as representative of other hosts.",
                "execution-scope")


def evaluate(root: Path) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []
    ctx = EvaluationContext(root=root)

    jinja_env = Environment()

    filter_discovery_error = install_ansible_filter_placeholders(jinja_env)
    if filter_discovery_error:
        findings.append(
            finding(
                "validator",
                "ansible filter discovery",
                "error",
                "ansible-filter-discovery-failed",
                filter_discovery_error,
                "validator",
            )
        )

    test_discovery_error = install_ansible_test_placeholders(jinja_env)
    if test_discovery_error:
        findings.append(
            finding(
                "validator",
                "ansible test discovery",
                "error",
                "ansible-test-discovery-failed",
                test_discovery_error,
                "validator",
            )
        )

    parsed_yaml_files: list[tuple[Path, str, Any]] = []

    for path in sorted(root.rglob("*.yml")) + sorted(root.rglob("*.yaml")):
        if any(part in {".git", ".tox", ".venv", "venv"} for part in path.parts):
            continue

        rel = str(path.relative_to(root))
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            documents = list(yaml.safe_load_all(raw))
            data = documents[0] if len(documents) == 1 else documents
        except Exception:
            # YAML parse errors are owned by yaml_check()/the CLI YAML layer.
            continue

        parsed_yaml_files.append((path, rel, data))
        collect_explicit_vars(ctx, path, data)

        if re.search(r"#\s*noqa\b|skip_ansible_lint", raw, re.I):
            findings.append(
                finding(
                    rel,
                    "file policy",
                    "error",
                    "validator-bypass-directive",
                    (
                        "AI-generated content may not suppress validator/ansible-lint "
                        "rules with noqa/skip_ansible_lint."
                    ),
                    "anti-bypass",
                )
            )

        check_all_yaml_for_literal_secrets(rel, data, findings)

        docs = data if isinstance(data, list) else [data]
        for obj in docs:
            if isinstance(obj, dict) and obj.get("vars_prompt"):
                findings.append(
                    finding(
                        rel,
                        str(obj.get("name", "play")),
                        "error",
                        "aap-vars-prompt-unsupported",
                        (
                            "vars_prompt is not suitable for non-interactive AAP "
                            "execution. Use AAP credentials, surveys, or variables."
                        ),
                        "aap",
                    )
                )

    provider_state = role_fact_provider_state(parsed_yaml_files)

    for path, rel, data in parsed_yaml_files:
        if not is_ansible_task_context(path, data):
            continue

        role_root = role_root_for_path(path)
        readonly_intent = has_readonly_intent(role_root)

        add_fact_provider_order_findings(
            findings,
            path,
            rel,
            data,
        )

        task_items = list(walk_tasks(path, data))
        for index, item in enumerate(task_items):
            defined_vars = (
                role_vars(ctx, role_root)
                if role_root is not None
                else set(ANSIBLE_RUNTIME_VARS)
            )
            defined_vars |= local_task_vars(item)
            defined_vars |= setup_runtime_vars_for_task(task_items, index)

            add_inline_jinja_findings(
                findings,
                jinja_env,
                item,
                rel,
                task_name(item),
                defined_vars,
            )

            add_fact_provider_findings(
                findings,
                json.dumps(item),
                rel,
                task_name(item),
                role_root,
                provider_state,
            )

            check_task(
                rel,
                item,
                findings,
                is_handler_file=(
                    "handlers/" in rel
                    or rel.startswith("handlers")
                    or path.parent.name == "handlers"
                ),
                readonly_intent=readonly_intent,
            )

    for template_path in sorted(root.rglob("*.j2")):
        if any(part in {".git", ".tox", ".venv", "venv"} for part in template_path.parts):
            continue

        rel = str(template_path.relative_to(root))
        role_root = role_root_for_path(template_path)
        if role_root is None:
            continue

        try:
            template_text = template_path.read_text(encoding="utf-8")
            ast = jinja_env.parse(template_text)
        except TemplateAssertionError as exc:
            filter_name = unknown_filter_name(exc)
            test_name = unknown_test_name(exc)
            if filter_name:
                findings.append(
                    finding(
                        rel,
                        "template parse",
                        "error",
                        "unknown-ansible-filter",
                        (
                            f"Jinja template references filter '{filter_name}', but "
                            "that filter plugin cannot be resolved in the validation "
                            "environment. Use a valid installed filter FQCN or short "
                            "name confirmed by ansible-doc -t filter."
                        ),
                        "jinja",
                    )
                )
            elif test_name:
                findings.append(
                    finding(
                        rel,
                        "template parse",
                        "error",
                        "unknown-ansible-test",
                        (
                            f"Jinja template references test '{test_name}', but "
                            "that test plugin cannot be resolved in the validation "
                            "environment. Use a valid installed test FQCN or short "
                            "name confirmed by ansible-doc -t test."
                        ),
                        "jinja",
                    )
                )
            else:
                findings.append(
                    finding(
                        rel,
                        "template parse",
                        "error",
                        "template-jinja-parse",
                        f"Could not parse Jinja template: {exc}",
                        "jinja",
                    )
                )
            continue
        except TemplateSyntaxError as exc:
            findings.append(
                finding(
                    rel,
                    "template parse",
                    "error",
                    "template-jinja-parse",
                    f"Could not parse Jinja template: {exc}",
                    "jinja",
                )
            )
            continue
        except Exception as exc:
            findings.append(
                finding(
                    rel,
                    "template parse",
                    "error",
                    "template-jinja-parse",
                    f"Could not parse Jinja template: {exc}",
                    "jinja",
                )
            )
            continue

        try:
            used_vars = meta.find_undeclared_variables(ast)
        except TemplateAssertionError as exc:
            filter_name = unknown_filter_name(exc)
            test_name = unknown_test_name(exc)
            if filter_name:
                findings.append(
                    finding(
                        rel,
                        "template variables",
                        "error",
                        "unknown-ansible-filter",
                        (
                            f"Jinja template references filter '{filter_name}', but "
                            "that filter plugin cannot be resolved in the validation "
                            "environment. Use a valid installed filter FQCN or short "
                            "name confirmed by ansible-doc -t filter."
                        ),
                        "jinja",
                    )
                )
            elif test_name:
                findings.append(
                    finding(
                        rel,
                        "template variables",
                        "error",
                        "unknown-ansible-test",
                        (
                            f"Jinja template references test '{test_name}', but "
                            "that test plugin cannot be resolved in the validation "
                            "environment. Use a valid installed test FQCN or short "
                            "name confirmed by ansible-doc -t test."
                        ),
                        "jinja",
                    )
                )
            else:
                findings.append(
                    finding(
                        rel,
                        "template variables",
                        "error",
                        "template-jinja-parse",
                        f"Could not analyse Jinja template variables: {exc}",
                        "jinja",
                    )
                )
            continue
        defined_vars = role_vars(ctx, role_root)
        defined_vars |= template_vars_for_path(ctx, role_root, template_path)

        for var_name in sorted(var for var in used_vars if var not in defined_vars):
            findings.append(
                finding(
                    rel,
                    "template variables",
                    "error",
                    "undefined-template-variable",
                    (
                        f"Template references '{var_name}', but it is not defined in "
                        "role defaults/main.yml, vars/main.yml, role include/import "
                        "vars, registered vars, or template task vars."
                    ),
                    "correctness",
                )
            )

        add_ansible_fact_findings(
            findings,
            template_text,
            rel,
            "template variables",
        )

    lint_cfg = root / ".ansible-lint"
    if lint_cfg.exists():
        raw = lint_cfg.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\bskip_list\s*:", raw):
            findings.append(
                finding(
                    ".ansible-lint",
                    "file policy",
                    "error",
                    "validator-policy-modification",
                    (
                        ".ansible-lint contains skip_list. Generated repair content "
                        "may not weaken validation policy."
                    ),
                    "anti-bypass",
                )
            )

    ansible_cfg = root / "ansible.cfg"
    if ansible_cfg.exists():
        raw = ansible_cfg.read_text(encoding="utf-8", errors="replace")
        if re.search(r"host_key_checking\s*=\s*false", raw, re.I):
            findings.append(
                finding(
                    "ansible.cfg",
                    "file policy",
                    "error",
                    "security-config-downgrade",
                    (
                        "ansible.cfg disables SSH host-key checking. Use a reviewed "
                        "trust/known-hosts design instead of globally disabling "
                        "verification."
                    ),
                    "anti-bypass",
                )
            )

    return {
        "ok": not any(item["severity"] == "error" for item in findings),
        "findings": findings,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = evaluate(Path(args.root).resolve())
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for x in result["findings"]:
            print(f"{x['severity'].upper():7} {x['rule']:36} {x['file']} :: {x['task']}")
            print(f"        {x['message']}")
        print("PASS" if result["ok"] else "FAIL")
    raise SystemExit(0 if result["ok"] else 1)
