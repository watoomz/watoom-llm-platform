# Kali package-management rules
- Package installation is administrative, not investigative, and must be allowed by the selected host profile.
- Managed Kali image package changes belong in IaC/image rebuild workflow; do not apt-install ad hoc because a tool is missing.
