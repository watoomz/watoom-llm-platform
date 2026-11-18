# SQL rules
- Use the existing schema/migration mechanism and preserve transaction/migration ordering.
- Parameterize application queries where supported.
- Do not use destructive production-data operations as verification.
- Keep schema changes bounded and reversible where supported.
