# Security rules

- Define the trust boundary for every new input, network endpoint, and external
  service. If the deployment scope changes, revisit the threat model rather
  than inheriting assumptions from local development.
- Store credentials in environment variables, OS credential storage, or the
  external platform's secret manager. Never place secrets in source, notebooks,
  datasets, command output, screenshots, logs, or generated metadata.
- Keep private datasets and model artifacts private by default. Publishing,
  sharing, or changing access controls requires explicit user authorization.
- Validate untrusted file content, paths, sizes, counts, and decoded data before
  expensive processing. Reject path traversal and avoid interpreting user data
  as code, shell syntax, formulas, HTML, or templates.
- Pass subprocess arguments as structured values where possible. Do not build
  shell commands from untrusted strings.
- Bind development services to loopback unless LAN or public access is an
  explicit requirement. Public exposure requires authentication, transport
  security, resource limits, and audit considerations.
- Minimize data sent to external services. Document what leaves the machine,
  where it is stored, and how generated artifacts are retrieved or deleted.
- Redact tokens, cookies, signed URLs, personal paths, and private dataset
  contents from persistent logs and completion reports.
- Treat downloaded code, model files, archives, and serialized objects as
  untrusted. Pin or record dependencies and avoid unsafe deserialization.
- Security controls that matter to the stated trust boundary must have focused
  automated tests or an explicit operational check.

