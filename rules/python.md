# Python rules

- Target Python 3.11+ and use built-in generic types such as `list[str]`.
- Add type hints to public functions, methods, and module boundaries.
- Prefer small, cohesive modules and explicit control flow over clever code.
- Use immutable values where practical; avoid hidden mutation and global state.
- Catch only expected, specific exceptions and preserve causes with `raise ... from error`.
- Keep I/O, framework concerns, and business logic separate.
- Test observable behavior, including edge cases and failure paths.
- Prefer an adequate dependency already used by the project. Keep genuinely
  trivial logic in the standard library, but use a mature library when it
  safely owns substantial protocol, correctness, or edge-case complexity.
- Before adding a dependency, verify that its supported Python versions,
  maintenance status, license, and security posture fit the intended use when
  those factors are material. Do not add overlapping packages without a clear
  subsystem boundary.
- Declare and install dependencies through the repository's Docker workflow;
  do not rely on packages installed interactively in a long-lived container.
