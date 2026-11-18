# Writable image project mount

Production OpenCode now has a dedicated writable hostPath mount for `/data/ai/projects/images` at the same container path. The containing `/data/ai` mount remains read-only. The application image, model selection, security identity, existing directory permissions and other mounts were preserved.

Authoritative configuration: `watoom_code_image_projects_root` in the application role defaults; the `image-projects` volume and app mount in `templates/resources.json.j2`; missing-root provisioning in `tasks/project_layout.yml`. Provisioning rejects symlinks and preserves existing directory contents and permissions. Newly created roots use the established shared project group and container file label.

Applied only the pod-template mount addition under the existing durable native admission guard, with exact deployment identity checks and rollback protection. Kubernetes omits an explicit false `readOnly` field; verification normalizes only that documented serialization difference. No image rebuild was required.

Validation: authoritative JSON rendering and task YAML parse; healthy production rollout; a neutral temporary nested checkpoint-style file was created, read, and removed as app UID 1001; `/data/ai` remains a read-only filesystem; existing root ownership/mode remained unchanged; native admission guard released and active sessions zero. No existing job was resumed and no image generation was submitted.

Evidence: `/data/ai/helper-scripts/reports/image-project-mount-20261021`.
