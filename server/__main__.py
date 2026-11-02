from .recovery_startup import recovery_startup

# Acquire the recovery transfer before importing http: that module constructs
# runtime state at import time, and main() performs database migrations.
with recovery_startup():
    from .http import main
    main()
