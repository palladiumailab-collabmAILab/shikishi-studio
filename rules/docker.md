# Docker runtime and portability rules

- Run Python, dependency installation, tests, linting, type checks, migrations,
  and the application inside Docker unless the user explicitly overrides this
  project policy. Host tools may orchestrate Git, Docker, and filesystem work.
- A narrowly scoped host-side Python comparison may diagnose a Docker/runtime
  failure, but it is not acceptance evidence for the application.
- Keep Python version, dependencies, development tools, and canonical commands
  reproducible from repository-controlled Docker and dependency files. Do not
  rely on undeclared packages or a developer's machine state.
- Never embed secrets in images, build arguments, layers, or committed Compose
  configuration.
- Store durable application data outside ephemeral container layers. Make cache
  and temporary data distinguishable from state that must survive recreation.
- Express required GPU, platform, network, and volume capabilities explicitly,
  and fail clearly when a required capability is unavailable.
- Verify the Docker path affected by a change. Rebuild or retest only unrelated
  infrastructure when it materially increases confidence.
