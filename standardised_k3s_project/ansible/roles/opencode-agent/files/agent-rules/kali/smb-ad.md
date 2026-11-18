# Kali SMB / AD rules
- Resolve explicit host/domain authorization before enumeration and separate anonymous/read-only from credentialed/mutating actions.
- Never reuse/discover credentials outside scope; select installed tools/arguments from local references.
- Mutating directory/account actions require explicit authorization.
