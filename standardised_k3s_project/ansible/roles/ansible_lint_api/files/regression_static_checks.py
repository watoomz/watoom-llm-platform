#!/usr/bin/env python3
import tempfile
from pathlib import Path

import server


def run_static(files):
    with tempfile.TemporaryDirectory(prefix="ansible-lint-api-regression-") as tmp:
        root = Path(tmp)
        server.write_files(root, files)
        return server.static_ansible_checks(root)["findings"]


def assert_finding(findings, rule, task):
    if not any(item["rule"] == rule and item["task"] == task for item in findings):
        raise AssertionError(f"missing {rule} finding for task {task!r}: {findings!r}")


def assert_no_finding(findings, rule, task):
    if any(item["rule"] == rule and item["task"] == task for item in findings):
        raise AssertionError(f"unexpected {rule} finding for task {task!r}: {findings!r}")


def assert_finding_message_contains(findings, rule, task, text):
    if not any(item["rule"] == rule and item["task"] == task and text in item["message"] for item in findings):
        raise AssertionError(f"missing {rule} finding for task {task!r} containing {text!r}: {findings!r}")


def test_fqcn_regressions():
    findings = run_static(
        {
            "roles/regression/tasks/main.yml": """---
- name: Bare assert regression
  assert:
    that:
      - true

- name: Bare shell regression
  shell: echo hello
  changed_when: false
  failed_when: false

- name: Bare template regression
  template:
    src: x.j2
    dest: /tmp/x

- name: Bare set_fact regression
  set_fact:
    x: 1

- name: Bare service regression
  service:
    name: sshd
    state: started

- name: Bare debug regression
  debug:
    msg: hello

- name: FQCN command with register regression
  ansible.builtin.command: uptime
  register: uptime_result
  changed_when: false
  failed_when: false
""",
            "roles/regression/templates/x.j2": "hello\n",
        }
    )
    for task in (
        "Bare assert regression",
        "Bare shell regression",
        "Bare template regression",
        "Bare set_fact regression",
        "Bare service regression",
        "Bare debug regression",
    ):
        assert_finding(findings, "fqcn-module-name", task)
    assert_no_finding(findings, "fqcn-module-name", "FQCN command with register regression")


def test_command_shell_outcome_guards_are_global():
    findings = run_static(
        {
            "roles/regression/tasks/main.yml": """---
- name: Missing both on command
  ansible.builtin.command: uptime

- name: Missing failed_when on shell
  ansible.builtin.shell: echo hello
  changed_when: false

- name: Missing changed_when on shell
  ansible.builtin.shell: echo hello
  failed_when: false

- name: Complete shell guards
  ansible.builtin.shell: echo hello
  changed_when: false
  failed_when: false
"""
        }
    )
    for task in (
        "Missing both on command",
        "Missing failed_when on shell",
        "Missing changed_when on shell",
    ):
        assert_finding(findings, "command-shell-outcome-guards", task)
    assert_no_finding(findings, "command-shell-outcome-guards", "Complete shell guards")


def test_shell_pipeline_in_readonly_check_roles():
    findings = run_static(
        {
            "roles/process_health_check/defaults/main.yml": """---
process_health_check_min_zombies: 0
""",
            "roles/process_health_check/tasks/main.yml": """---
- name: Count zombie processes with shell pipeline
  ansible.builtin.shell:
    cmd: ps -eo stat= | grep -c Z
  register: zombie_process_count
  changed_when: false
  failed_when: false

- name: Read uptime using command instead of facts
  ansible.builtin.command:
    argv:
      - uptime
      - -p
  register: native_uptime
  changed_when: false
  failed_when: native_uptime.rc != 0

- name: Read SELinux using command instead of facts
  ansible.builtin.command:
    argv:
      - getenforce
  register: native_selinux
  changed_when: false
  failed_when: native_selinux.rc != 0

- name: Read firewalld using command instead of service facts
  ansible.builtin.command:
    argv:
      - systemctl
      - is-active
      - firewalld
  register: native_firewalld
  changed_when: false
  failed_when: native_firewalld.rc not in [0, 3]

- name: Read packages using rpm instead of package facts
  ansible.builtin.command:
    argv:
      - rpm
      - -qa
  register: native_packages
  changed_when: false
  failed_when: native_packages.rc != 0

- name: Read filesystems using df instead of facts
  ansible.builtin.command:
    argv:
      - df
      - -P
  register: native_filesystems
  changed_when: false
  failed_when: native_filesystems.rc != 0

- name: Read network using ip instead of facts
  ansible.builtin.command:
    argv:
      - ip
      - addr
      - show
  register: native_network
  changed_when: false
  failed_when: native_network.rc != 0

- name: Collect process states with command
  ansible.builtin.command:
    argv:
      - ps
      - -eo
      - stat=
  register: process_states
  changed_when: false
  failed_when: process_states.rc != 0

- name: Assert zombie threshold
  ansible.builtin.assert:
    that:
      - zombie_process_count.stdout | int <= process_health_check_min_zombies
""",
            "roles/service_audit/meta/main.yml": """---
galaxy_info:
  galaxy_tags:
    - audit
""",
            "roles/service_audit/tasks/main.yml": """---
- name: Count inactive services with awk
  ansible.builtin.shell:
    cmd: systemctl list-units --type=service --state=failed | awk 'END { print NR }'
  register: failed_service_count
  changed_when: false
  failed_when: false
""",
            "roles/package_probe/tasks/main.yml": """---
- name: Non-readonly role may use guarded pipeline
  ansible.builtin.shell:
    cmd: rpm -qa | grep -c '^kernel'
  register: kernel_package_count
  changed_when: false
  failed_when: false
""",
        }
    )
    assert_finding(findings, "shell-pipeline-in-readonly-check", "Count zombie processes with shell pipeline")
    assert_finding(findings, "shell-pipeline-in-readonly-check", "Count inactive services with awk")
    assert_no_finding(findings, "shell-pipeline-in-readonly-check", "Non-readonly role may use guarded pipeline")
    for task in (
        "Read uptime using command instead of facts",
        "Read SELinux using command instead of facts",
        "Read firewalld using command instead of service facts",
        "Read packages using rpm instead of package facts",
        "Read filesystems using df instead of facts",
        "Read network using ip instead of facts",
    ):
        assert_finding(findings, "facts-first-known-data", task)

    assert_no_finding(
        findings,
        "facts-first-known-data",
        "Collect process states with command",
    )


def test_undefined_template_variables():
    findings = run_static(
        {
            "roles/web/defaults/main.yml": """---
defined_in_defaults: hello
""",
            "roles/web/vars/main.yml": """---
defined_in_vars: world
""",
            "roles/web/tasks/main.yml": """---
- name: Capture registered value
  ansible.builtin.command: uptime
  register: uptime_result
  changed_when: false
  failed_when: false

- name: Render config
  ansible.builtin.template:
    src: app.conf.j2
    dest: /tmp/app.conf
  vars:
    defined_on_template_task: task-value
""",
            "site.yml": """---
- name: Include role with vars
  hosts: localhost
  gather_facts: false
  roles:
    - role: web
      vars:
        defined_on_role_include: include-value
""",
            "roles/web/templates/app.conf.j2": """{{ defined_in_defaults }}
{{ defined_in_vars }}
{{ defined_on_template_task }}
{{ defined_on_role_include }}
{{ uptime_result.stdout }}
{{ inventory_hostname }}
{{ missing_template_var }}
""",
        }
    )
    assert_finding(findings, "undefined-template-variable", "template variables")
    missing_messages = [item["message"] for item in findings if item["rule"] == "undefined-template-variable"]
    if not any("'missing_template_var'" in message for message in missing_messages):
        raise AssertionError(f"missing undefined-template-variable for missing_template_var: {findings!r}")
    for defined_name in (
        "defined_in_defaults",
        "defined_in_vars",
        "defined_on_template_task",
        "defined_on_role_include",
        "uptime_result",
        "inventory_hostname",
    ):
        if any(f"'{defined_name}'" in message for message in missing_messages):
            raise AssertionError(f"unexpected undefined-template-variable for {defined_name}: {findings!r}")
    for non_task_key in ("defined_in_defaults", "defined_in_vars", "hosts", "gather_facts", "roles"):
        if any(f"'{non_task_key}'" in item["message"] for item in findings if item["rule"] == "fqcn-module-name"):
            raise AssertionError(f"non-task key {non_task_key} was treated as a module: {findings!r}")


def test_inline_jinja_variables():
    findings = run_static(
        {
            "roles/inline_var_check/defaults/main.yml": """---
expected_process_count: 1
""",
            "roles/inline_var_check/tasks/main.yml": """---
- name: Capture hostname
  ansible.builtin.command:
    argv:
      - hostname
  register: hostname_result
  changed_when: false
  failed_when: hostname_result.rc != 0

- name: Define derived host label
  ansible.builtin.set_fact:
    host_label: "{{ hostname_result.stdout }}"

- name: Report registered inline result
  ansible.builtin.debug:
    msg: "Host: {{ hostname_result.stdout }} / {{ host_label }} / {{ item.name }}"
  loop:
    - name: test

- name: Assert valid inline result
  ansible.builtin.assert:
    that:
      - hostname_result.stdout | length > 0
      - host_label | length > 0
      - expected_process_count | int >= 0

- name: Report missing inline result
  ansible.builtin.debug:
    msg: "CPU load: {{ cpu_load_result.stdout_lines[0] }}"

- name: Assert missing inline result
  ansible.builtin.assert:
    that:
      - cpu_load_result.stdout | int >= expected_process_count
""",
        }
    )
    assert_finding_message_contains(findings, "undefined-template-variable", "Report missing inline result", "cpu_load_result")
    assert_finding_message_contains(findings, "undefined-template-variable", "Assert missing inline result", "cpu_load_result")
    for task in ("Report registered inline result", "Assert valid inline result"):
        assert_no_finding(findings, "undefined-template-variable", task)



def test_inline_ansible_date_time_requires_prior_setup():
    findings = run_static(
        {
            "roles/datetime_check/tasks/main.yml": """---
- name: Report missing timestamp
  ansible.builtin.debug:
    msg: "Missing timestamp: {{ ansible_date_time.iso8601 }}"

- name: Gather setup facts
  ansible.builtin.setup:

- name: Report setup timestamp
  ansible.builtin.set_fact:
    report_timestamp: "{{ ansible_date_time.iso8601 }}"
""",
        }
    )
    assert_no_finding(findings, "undefined-template-variable", "Report setup timestamp")

    missing = [
        finding
        for finding in findings
        if finding["rule"] == "undefined-template-variable"
        and finding["task"] == "Report missing timestamp"
        and "ansible_date_time" in finding["message"]
    ]
    if not missing:
        raise AssertionError(f"missing undefined-template-variable for ansible_date_time before setup: {findings!r}")



def test_ansible_aware_jinja_filter_validation():
    import policy_engine

    filters, error = policy_engine.ansible_filter_registry()
    if error:
        raise AssertionError(f"ansible filter discovery failed unexpectedly: {error}")

    cases = [
        ("standard_length", "{{ values | length }}", "pass", None),
        ("strftime_short", "{{ '%Y-%m-%d' | strftime }}", "pass" if "strftime" in filters else "skip", None),
        ("strftime_fqcn", "{{ '%Y-%m-%d' | ansible.builtin.strftime }}", "pass" if "ansible.builtin.strftime" in filters else "skip", None),
        ("to_datetime_short", "{{ value | to_datetime }}", "pass" if "to_datetime" in filters else "skip", None),
        ("to_datetime_fqcn", "{{ value | ansible.builtin.to_datetime }}", "pass" if "ansible.builtin.to_datetime" in filters else "skip", None),
        ("ansible_utils_to_datetime", "{{ value | ansible.utils.to_datetime }}", "pass" if "ansible.utils.to_datetime" in filters else "error", "unknown-ansible-filter"),
        ("fake_filter", "{{ value | watoom.fake_filter }}", "error", "unknown-ansible-filter"),
        ("malformed_jinja", "{{ foo | default( }}", "error", "inline-jinja-parse"),
    ]

    files = {
        "roles/filter_check/defaults/main.yml": """---
values:
  - one
value: "2026-09-11 12:00:00"
foo: fallback
""",
        "roles/filter_check/tasks/main.yml": "---\n",
    }
    for name, expr, expected, _rule in cases:
        if expected == "skip":
            continue
        files["roles/filter_check/tasks/main.yml"] += f"""
- name: {name}
  ansible.builtin.debug:
    msg: "{expr}"
"""

    findings = run_static(files)
    for name, _expr, expected, rule in cases:
        if expected == "skip":
            continue
        if expected == "pass":
            for finding in findings:
                if finding["task"] == name and finding["rule"] in ("unknown-ansible-filter", "inline-jinja-parse", "undefined-template-variable"):
                    raise AssertionError(f"expected {name} to pass Jinja validation, got {finding!r}")
        else:
            assert_finding(findings, rule, name)



def test_ansible_aware_jinja_test_validation():
    import policy_engine

    tests, error = policy_engine.ansible_test_registry()
    if error:
        raise AssertionError(f"ansible test discovery failed unexpectedly: {error}")

    cases = [
        ("standard_defined", "{{ value is defined }}", "pass", None),
        ("succeeded_short", "{{ result is succeeded }}", "pass" if "succeeded" in tests else "error", "unknown-ansible-test"),
        ("failed_short", "{{ result is failed }}", "pass" if "failed" in tests else "error", "unknown-ansible-test"),
        ("succeeded_fqcn", "{{ result is ansible.builtin.succeeded }}", "pass" if "ansible.builtin.succeeded" in tests else "error", "unknown-ansible-test"),
        ("failed_fqcn", "{{ result is ansible.builtin.failed }}", "pass" if "ansible.builtin.failed" in tests else "error", "unknown-ansible-test"),
        ("fake_test", "{{ result is watoom.fake_test }}", "error", "unknown-ansible-test"),
    ]

    files = {
        "roles/test_check/defaults/main.yml": """---
value: present
result:
  failed: false
""",
        "roles/test_check/tasks/main.yml": "---\n",
    }

    for name, expr, _expected, _rule in cases:
        files["roles/test_check/tasks/main.yml"] += f"""
- name: {name}
  ansible.builtin.debug:
    msg: "{expr}"
"""

    findings = run_static(files)

    for name, _expr, expected, rule in cases:
        if expected == "pass":
            for item in findings:
                if (
                    item["task"] == name
                    and item["rule"] in (
                        "unknown-ansible-test",
                        "inline-jinja-parse",
                        "undefined-template-variable",
                    )
                ):
                    raise AssertionError(
                        f"expected {name} to pass Jinja test validation, got {item!r}"
                    )
        else:
            assert_finding(findings, rule, name)

def test_ansible_facts_reference_keys():
    findings = run_static(
        {
            "roles/facts_check/tasks/main.yml": """---
- name: Assert common fact references
  ansible.builtin.assert:
    that:
      - ansible_facts.hostname is defined
      - ansible_facts['distribution'] is defined
      - ansible_facts.memtotal_mb | int >= 0
      - ansible_facts.services is mapping
      - ansible_facts['packages'] is mapping

- name: Report fabricated fact
  ansible.builtin.debug:
    msg: "Firewall state: {{ ansible_facts['firewall'].state }}"

- name: Assert fabricated fact
  ansible.builtin.assert:
    that:
      - ansible_facts['zombie_count'] | int == 0
""",
        }
    )
    assert_no_finding(findings, "service-facts-reference", "Assert common fact references")
    assert_finding_message_contains(findings, "service-facts-reference", "Report fabricated fact", "firewall")
    assert_finding_message_contains(findings, "service-facts-reference", "Assert fabricated fact", "zombie_count")


def test_fact_provider_requirements():
    findings = run_static(
        {
            "roles/process_health_check/tasks/main.yml": """---
- name: Gather ordinary setup facts
  ansible.builtin.setup:

- name: Incorrect services reference without service facts
  ansible.builtin.set_fact:
    service_state: "{{ ansible_facts.services }}"

- name: Incorrect packages reference without package facts
  ansible.builtin.set_fact:
    package_state: "{{ ansible_facts.packages }}"
"""
        }
    )

    assert_finding(
        findings,
        "fact-provider-not-collected",
        "Incorrect services reference without service facts",
    )

    assert_finding(
        findings,
        "fact-provider-not-collected",
        "Incorrect packages reference without package facts",
    )

    findings = run_static(
        {
            "roles/process_health_check/tasks/main.yml": """---
- name: Gather setup facts
  ansible.builtin.setup:

- name: Gather service facts
  ansible.builtin.service_facts:

- name: Gather package facts
  ansible.builtin.package_facts:

- name: Valid services reference
  ansible.builtin.set_fact:
    service_state: "{{ ansible_facts.services }}"

- name: Valid packages reference
  ansible.builtin.set_fact:
    package_state: "{{ ansible_facts.packages }}"

- name: Valid setup facts
  ansible.builtin.set_fact:
    regular_facts:
      uptime: "{{ ansible_facts.uptime_seconds }}"
      selinux: "{{ ansible_facts.selinux }}"
      mounts: "{{ ansible_facts.mounts }}"
      interfaces: "{{ ansible_facts.interfaces }}"
"""
        }
    )

    assert_no_finding(
        findings,
        "fact-provider-not-collected",
        "Valid services reference",
    )

    assert_no_finding(
        findings,
        "fact-provider-not-collected",
        "Valid packages reference",
    )

    assert_no_finding(
        findings,
        "fact-provider-not-collected",
        "Valid setup facts",
    )


def test_host_fact_collection_scope():
    findings = run_static(
        {
            "roles/process_health_check/tasks/main.yml": """---
- name: Bad delegated setup
  ansible.builtin.setup:
  delegate_to: localhost
  run_once: true

- name: Bad run-once package facts
  ansible.builtin.package_facts:
  run_once: true

- name: Bad delegated service facts
  ansible.builtin.service_facts:
  delegate_to: 127.0.0.1

- name: Good setup facts
  ansible.builtin.setup:

- name: Good package facts
  ansible.builtin.package_facts:

- name: Good service facts
  ansible.builtin.service_facts:

- name: Controller API call is allowed
  ansible.builtin.uri:
    url: https://example.invalid/api
    method: GET
  delegate_to: localhost
  run_once: true
"""
        }
    )

    for task in (
        "Bad delegated setup",
        "Bad run-once package facts",
        "Bad delegated service facts",
    ):
        assert_finding(
            findings,
            "host-facts-must-run-on-target",
            task,
        )

    for task in (
        "Good setup facts",
        "Good package facts",
        "Good service facts",
        "Controller API call is allowed",
    ):
        assert_no_finding(
            findings,
            "host-facts-must-run-on-target",
            task,
        )


def test_fact_provider_order():
    findings = run_static(
        {
            "roles/process_health_check/tasks/main.yml": """---
- name: Gather normal host facts
  ansible.builtin.setup:

- name: Bad service facts consumer
  ansible.builtin.set_fact:
    firewalld_state: "{{ ansible_facts.services['firewalld.service'].state }}"

- name: Gather service facts too late
  ansible.builtin.service_facts:

- name: Gather package facts first
  ansible.builtin.package_facts:

- name: Good package facts consumer
  ansible.builtin.set_fact:
    installed_packages: "{{ ansible_facts.packages }}"
"""
        }
    )

    assert_finding(
        findings,
        "fact-provider-must-precede-use",
        "Bad service facts consumer",
    )

    assert_no_finding(
        findings,
        "fact-provider-must-precede-use",
        "Good package facts consumer",
    )

    findings = run_static(
        {
            "roles/process_health_check/tasks/main.yml": """---
- name: Gather service facts first
  ansible.builtin.service_facts:

- name: Good service facts consumer
  ansible.builtin.set_fact:
    firewalld_state: "{{ ansible_facts.services['firewalld.service'].state }}"

- name: Gather package facts first
  ansible.builtin.package_facts:

- name: Good package facts consumer
  ansible.builtin.set_fact:
    installed_packages: "{{ ansible_facts.packages }}"
"""
        }
    )

    assert_no_finding(
        findings,
        "fact-provider-must-precede-use",
        "Good service facts consumer",
    )

    assert_no_finding(
        findings,
        "fact-provider-must-precede-use",
        "Good package facts consumer",
    )




def test_readonly_command_deny_by_default_api_rules():
    findings = run_static(
        {
            "roles/rhel_health_check/tasks/main.yml": """---
- name: Gather system facts
  ansible.builtin.setup:
    gather_subset:
      - all
    fact_path: /tmp/facts

- name: Collect package facts
  ansible.builtin.package_facts:

- name: Collect service facts
  ansible.builtin.service_facts:

- name: Get uptime
  ansible.builtin.command: uptime -p
  changed_when: false
  register: uptime_result

- name: Get kernel version
  ansible.builtin.command: uname -r
  changed_when: false
  register: kernel_result

- name: Get memory usage
  ansible.builtin.command: free -m | awk 'NR==2{printf "%.2f", $3/$2 * 100}'
  changed_when: false
  register: memory_usage_result

- name: Get swap usage
  ansible.builtin.command: free -m | awk 'NR==3{printf "%.2f", $3/$2 * 100}'
  changed_when: false
  register: swap_usage_result

- name: Get filesystem usage
  ansible.builtin.command: df -h | tail -n +2 | awk '{print $5}' | sed 's/%//g' | sort -n | tail -1
  changed_when: false
  register: filesystem_usage_result

- name: Get zombie processes count
  ansible.builtin.command:
    argv:
      - ps
      - -eo
      - stat=
  register: process_states
  changed_when: false
  failed_when: process_states.rc != 0

- name: Unknown read-only tool
  ansible.builtin.command:
    argv:
      - some-new-health-tool
      - --status
  register: result
  changed_when: false
  failed_when: result.rc != 0

- name: Shell read test
  ansible.builtin.shell:
    cmd: printf hello
  register: shell_result
  changed_when: false
  failed_when: shell_result.rc != 0
""",
            "roles/app_config/tasks/main.yml": """---
- name: Non-readonly guarded command remains out of scope
  ansible.builtin.command:
    argv:
      - some-new-health-tool
      - --status
  register: result
  changed_when: false
  failed_when: result.rc != 0
""",
        }
    )
    assert_finding(findings, "readonly-setup-fact-path", "Gather system facts")
    for task in (
        "Get uptime",
        "Get kernel version",
        "Get memory usage",
        "Get swap usage",
        "Get filesystem usage",
    ):
        assert_finding(findings, "facts-first-known-data", task)
    for task in ("Get memory usage", "Get swap usage", "Get filesystem usage"):
        assert_finding(findings, "command-shell-metacharacters", task)
    assert_finding(findings, "readonly-command-not-allowlisted", "Unknown read-only tool")
    assert_finding(findings, "readonly-shell-not-permitted", "Shell read test")
    assert_no_finding(findings, "readonly-command-not-allowlisted", "Get zombie processes count")
    assert_no_finding(findings, "readonly-command-not-allowlisted", "Non-readonly guarded command remains out of scope")


def test_readonly_command_deny_by_default_policy_rules():
    import policy_engine
    with tempfile.TemporaryDirectory(prefix="ansible-lint-api-readonly-policy-") as tmp:
        root = Path(tmp)
        server.write_files(
            root,
            {
                "roles/rhel_health_check/tasks/main.yml": """---
- name: Gather system facts
  ansible.builtin.setup:
    gather_subset:
      - all
    fact_path: /tmp/facts

- name: Get uptime
  ansible.builtin.command: uptime -p
  changed_when: false
  failed_when: uptime_result.rc != 0
  register: uptime_result

- name: Unknown read-only tool
  ansible.builtin.command:
    argv:
      - some-new-health-tool
      - --status
  register: result
  changed_when: false
  failed_when: result.rc != 0

- name: Shell read test
  ansible.builtin.shell:
    cmd: printf hello
  register: shell_result
  changed_when: false
  failed_when: shell_result.rc != 0

- name: Collect process states
  ansible.builtin.command:
    argv:
      - ps
      - -eo
      - stat=
  register: process_states
  changed_when: false
  failed_when: process_states.rc != 0
""",
                "roles/app_config/tasks/main.yml": """---
- name: Non-readonly guarded command remains out of scope
  ansible.builtin.command:
    argv:
      - some-new-health-tool
      - --status
  register: result
  changed_when: false
  failed_when: result.rc != 0
""",
            },
        )
        findings = policy_engine.evaluate(root)["findings"]

    assert_finding(findings, "readonly-setup-fact-path", "Gather system facts")
    assert_finding(findings, "facts-first-known-data", "Get uptime")
    assert_finding(findings, "readonly-command-not-allowlisted", "Unknown read-only tool")
    assert_finding(findings, "readonly-shell-not-permitted", "Shell read test")
    assert_no_finding(findings, "readonly-command-not-allowlisted", "Collect process states")
    assert_no_finding(findings, "readonly-command-not-allowlisted", "Non-readonly guarded command remains out of scope")


def test_policy_engine_facts_first_known_data():
    import policy_engine
    with tempfile.TemporaryDirectory(prefix="ansible-lint-api-policy-regression-") as tmp:
        root = Path(tmp)
        server.write_files(
            root,
            {
                "roles/process_health_check/tasks/main.yml": """---
- name: Read uptime using command instead of facts
  ansible.builtin.command:
    argv:
      - uptime
      - -p
  register: native_uptime
  changed_when: false
  failed_when: native_uptime.rc != 0

- name: Collect process states with command
  ansible.builtin.command:
    argv:
      - ps
      - -eo
      - stat=
  register: process_states
  changed_when: false
  failed_when: process_states.rc != 0
""",
                "roles/package_probe/tasks/main.yml": """---
- name: Non-readonly role may inspect rpm directly
  ansible.builtin.command:
    argv:
      - rpm
      - -qa
  register: packages
  changed_when: false
  failed_when: packages.rc != 0
""",
            },
        )
        findings = policy_engine.evaluate(root)["findings"]

    assert_finding(findings, "facts-first-known-data", "Read uptime using command instead of facts")
    assert_no_finding(findings, "facts-first-known-data", "Collect process states with command")
    assert_no_finding(findings, "facts-first-known-data", "Non-readonly role may inspect rpm directly")


def test_module_resolution_canonicalizes_action_and_legacy_aliases():
    findings = run_static(
        {
            "roles/legacy_health_check/tasks/main.yml": """---
- name: Legacy shell read test
  ansible.legacy.shell:
    cmd: printf hello
  register: legacy_shell_result
  changed_when: false
  failed_when: legacy_shell_result.rc != 0

- name: Action shell read test
  action: shell printf hello
  register: action_shell_result
  changed_when: false
  failed_when: action_shell_result.rc != 0

- name: Legacy command allowlisted process state
  ansible.legacy.command:
    argv:
      - ps
      - -eo
      - stat=
  register: process_states
  changed_when: false
  failed_when: process_states.rc != 0
""",
        }
    )
    assert_finding(findings, "readonly-shell-not-permitted", "Legacy shell read test")
    assert_finding(findings, "readonly-shell-not-permitted", "Action shell read test")
    assert_no_finding(findings, "readonly-command-not-allowlisted", "Legacy command allowlisted process state")
    assert_no_finding(findings, "readonly-shell-not-permitted", "Legacy command allowlisted process state")


def test_home_named_paths_are_validated_without_skipping_tooling_dirs():
    findings = run_static(
        {
            "roles/user_provisioning/tasks/home_setup.yml": """---
- name: Bare debug in home-named task file
  debug:
    msg: "Provision /home/appuser"
""",
            "roles/user_provisioning/.git/tasks/ignored.yml": """---
- name: Bare shell in ignored git metadata
  shell: echo ignored
  changed_when: false
  failed_when: false
""",
        }
    )
    assert_finding(findings, "fqcn-module-name", "Bare debug in home-named task file")
    assert_no_finding(findings, "fqcn-module-name", "Bare shell in ignored git metadata")
    assert_no_finding(findings, "readonly-shell-not-permitted", "Bare shell in ignored git metadata")


def test_direct_restart_allowed_in_handlers_file():
    import policy_engine
    handler_task = {"name": "Restart svc", "ansible.builtin.systemd": {"name": "x", "state": "restarted"}}
    findings = []
    policy_engine.check_task("handlers/main.yml", handler_task, findings, is_handler_file=True)
    assert not any(f["rule"] == "direct-restart-outside-handler" for f in findings)

    ordinary_task_findings = []
    policy_engine.check_task("tasks/main.yml", handler_task, ordinary_task_findings, is_handler_file=False)
    assert any(f["rule"] == "direct-restart-outside-handler" for f in ordinary_task_findings)


def test_policy_engine_live_adapter_includes_security_and_original_rules():
    findings = run_static(
        {
            "roles/integration_check/tasks/main.yml": """---
- name: Bare debug must still be rejected
  debug:
    msg: hello

- name: Disabled TLS must be rejected
  ansible.builtin.uri:
    url: https://example.invalid/api
    validate_certs: false
"""
        }
    )

    assert_finding(
        findings,
        "fqcn-module-name",
        "Bare debug must still be rejected",
    )
    assert_finding(
        findings,
        "tls-validation-disabled",
        "Disabled TLS must be rejected",
    )


def test_failed_when_false_repair_gate_is_in_live_adapter():
    findings = run_static(
        {
            "roles/repair_gate/tasks/main.yml": """---
- name: Suppressed command failure
  ansible.builtin.command:
    argv:
      - /usr/bin/printf
      - hello
  changed_when: false
  failed_when: false
"""
        }
    )

    assert_finding(
        findings,
        "unconditional-failure-suppression",
        "Suppressed command failure",
    )



def test_repair_prompt_constraints_and_history():
    sample_files = {
        "roles/repair_gate/tasks/main.yml": """---
- name: Suppressed command failure
  ansible.builtin.command:
    argv:
      - /usr/bin/printf
      - hello
  changed_when: false
  failed_when: false
"""
    }

    initial_validation = {
        "ok": False,
        "yaml": {"ok": True, "files": []},
        "static_checks": {
            "ok": False,
            "findings": [
                {
                    "file": "roles/repair_gate/tasks/main.yml",
                    "task": "Suppressed command failure",
                    "severity": "error",
                    "rule": "unconditional-failure-suppression",
                    "message": "Task unconditionally suppresses failure with failed_when: false.",
                }
            ],
        },
        "syntax_checks": [],
        "ansible_lint": {"ok": True, "stdout": "", "stderr": ""},
    }

    constraints = server.validation_repair_constraints(initial_validation)
    if not any(
        item.get("rule") == "unconditional-failure-suppression"
        for item in constraints
    ):
        raise AssertionError(f"missing cumulative suppression constraint: {constraints!r}")

    prompt = server.build_repair_prompt(
        "Keep command failure deterministic.",
        sample_files,
        initial_validation,
        constraints,
    )

    required_prompt_text = (
        "Never use failed_when: false",
        "health/status thresholds from execution failures",
        "Do not use a later ansible.builtin.assert task as a substitute",
        "Do not reintroduce a previously fixed failure",
        "unconditional-failure-suppression",
        "Use fully qualified collection names",
    )

    for fragment in required_prompt_text:
        if fragment not in prompt:
            raise AssertionError(
                f"repair prompt missing required invariant {fragment!r}"
            )

    original_validate = server.validate_files
    original_call = server.call_repair_model
    calls = []

    validations = [
        initial_validation,
        {
            "ok": False,
            "yaml": {"ok": True, "files": []},
            "static_checks": {
                "ok": False,
                "findings": [
                    {
                        "file": "roles/repair_gate/tasks/main.yml",
                        "task": "Verify command success",
                        "severity": "error",
                        "rule": "undefined-template-variable",
                        "message": "Inline task Jinja references 'cmd', but it is not defined.",
                    }
                ],
            },
            "syntax_checks": [],
            "ansible_lint": {"ok": True, "stdout": "", "stderr": ""},
        },
        {
            "ok": False,
            "yaml": {"ok": True, "files": []},
            "static_checks": {
                "ok": False,
                "findings": [
                    {
                        "file": "roles/repair_gate/tasks/main.yml",
                        "task": "Verify command success",
                        "severity": "error",
                        "rule": "command-shell-outcome-guards",
                        "message": "command task is missing failed_when.",
                    },
                    {
                        "file": "roles/repair_gate/tasks/main.yml",
                        "task": "Check command output",
                        "severity": "error",
                        "rule": "fqcn-module-name",
                        "message": "Task uses bare module/action name 'assert'.",
                    },
                ],
            },
            "syntax_checks": [],
            "ansible_lint": {"ok": True, "stdout": "", "stderr": ""},
        },
        {
            "ok": True,
            "yaml": {"ok": True, "files": []},
            "static_checks": {"ok": True, "findings": []},
            "syntax_checks": [],
            "ansible_lint": {"ok": True, "stdout": "", "stderr": ""},
        },
    ]

    candidates = [
        {
            "roles/repair_gate/tasks/main.yml": "candidate-one\n",
        },
        {
            "roles/repair_gate/tasks/main.yml": "candidate-two\n",
        },
        {
            "roles/repair_gate/tasks/main.yml": "candidate-three\n",
        },
    ]

    def fake_validate(_files):
        index = len(calls)
        if index >= len(validations):
            index = len(validations) - 1
        return validations[index]

    def fake_call(goal, files, validation, cumulative_constraints):
        calls.append(
            {
                "goal": goal,
                "files": dict(files),
                "validation": validation,
                "constraints": [dict(item) for item in cumulative_constraints],
            }
        )
        return dict(candidates[len(calls) - 1])

    try:
        server.validate_files = fake_validate
        server.call_repair_model = fake_call

        result = server.repair_payload(
            {
                "goal": "test cumulative constraints",
                "max_iterations": 3,
                "files": sample_files,
            }
        )
    finally:
        server.validate_files = original_validate
        server.call_repair_model = original_call

    if result.get("ok") is not True:
        raise AssertionError(f"synthetic repair loop did not converge: {result!r}")

    if result.get("iterations") != 3:
        raise AssertionError(f"unexpected synthetic iteration count: {result!r}")

    if len(calls) != 3:
        raise AssertionError(f"expected 3 repair calls, got {len(calls)}")

    expected_rules_by_call = [
        {"unconditional-failure-suppression"},
        {
            "unconditional-failure-suppression",
            "undefined-template-variable",
        },
        {
            "unconditional-failure-suppression",
            "undefined-template-variable",
            "command-shell-outcome-guards",
            "fqcn-module-name",
        },
    ]

    for index, expected_rules in enumerate(expected_rules_by_call):
        actual_rules = {
            item.get("rule")
            for item in calls[index]["constraints"]
        }
        if not expected_rules.issubset(actual_rules):
            raise AssertionError(
                f"repair call {index} lost cumulative constraints: "
                f"expected {expected_rules!r}, got {actual_rules!r}"
            )

    history = result.get("history") or []
    if len(history) != 4:
        raise AssertionError(f"expected 4 history entries, got {len(history)}")

    expected_snapshots = [
        sample_files,
        candidates[0],
        candidates[1],
        candidates[2],
    ]

    for index, expected_files in enumerate(expected_snapshots):
        actual_files = history[index].get("files")
        if actual_files != expected_files:
            raise AssertionError(
                f"history[{index}] candidate snapshot mismatch: "
                f"expected {expected_files!r}, got {actual_files!r}"
            )


def test_conditional_jinja_delimiters():
    findings = run_static(
        {
            "roles/config_role/defaults/main.yml": """---
enabled: true
""",
            "roles/config_role/tasks/main.yml": """---
- name: Bad failed_when delimiters
  ansible.builtin.command:
    argv:
      - /usr/bin/printf
      - hello
  register: bad_result
  changed_when: false
  failed_when: "{{ bad_result.rc != 0 }}"

- name: Good raw failed_when expression
  ansible.builtin.command:
    argv:
      - /usr/bin/printf
      - hello
  register: good_result
  changed_when: false
  failed_when: good_result.rc != 0

- name: Bad when delimiters
  ansible.builtin.debug:
    msg: enabled
  when: "{{ enabled | bool }}"

- name: Good raw when expression
  ansible.builtin.debug:
    msg: enabled
  when: enabled | bool

- name: Bad assert delimiters
  ansible.builtin.assert:
    that:
      - "{{ enabled | bool }}"

- name: Good raw assert expression
  ansible.builtin.assert:
    that:
      - enabled | bool
"""
        }
    )

    assert_finding(
        findings,
        "conditional-jinja-delimiters",
        "Bad failed_when delimiters",
    )
    assert_finding(
        findings,
        "conditional-jinja-delimiters",
        "Bad when delimiters",
    )
    assert_finding(
        findings,
        "conditional-jinja-delimiters",
        "Bad assert delimiters",
    )

    assert_no_finding(
        findings,
        "conditional-jinja-delimiters",
        "Good raw failed_when expression",
    )
    assert_no_finding(
        findings,
        "conditional-jinja-delimiters",
        "Good raw when expression",
    )
    assert_no_finding(
        findings,
        "conditional-jinja-delimiters",
        "Good raw assert expression",
    )

if __name__ == "__main__":
    test_fqcn_regressions()
    test_command_shell_outcome_guards_are_global()
    test_shell_pipeline_in_readonly_check_roles()
    test_undefined_template_variables()
    test_inline_jinja_variables()
    test_inline_ansible_date_time_requires_prior_setup()
    test_ansible_aware_jinja_filter_validation()
    test_ansible_aware_jinja_test_validation()
    test_ansible_facts_reference_keys()
    test_fact_provider_requirements()
    test_host_fact_collection_scope()
    test_fact_provider_order()
    test_readonly_command_deny_by_default_api_rules()
    test_readonly_command_deny_by_default_policy_rules()
    test_policy_engine_facts_first_known_data()
    test_module_resolution_canonicalizes_action_and_legacy_aliases()
    test_home_named_paths_are_validated_without_skipping_tooling_dirs()
    test_direct_restart_allowed_in_handlers_file()
    test_policy_engine_live_adapter_includes_security_and_original_rules()
    test_failed_when_false_repair_gate_is_in_live_adapter()
    test_repair_prompt_constraints_and_history()
    test_conditional_jinja_delimiters()
    print("static check regressions passed")
