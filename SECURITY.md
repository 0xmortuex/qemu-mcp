# Security Policy

## Trust model

qemu-mcp gives whatever MCP client is driving it the same level of access
as running `qemu-system-*`/`qemu-img` yourself on this machine. It is
**not** a sandbox around QEMU, and it does not attempt to restrict or
sanitize what a calling agent can do with the VMs it manages:

- `qemu_qmp` runs *any* QMP command against a booted VM verbatim,
  including commands with host filesystem access (`memsave`, `pmemsave`,
  `migrate` to a local file, etc.) or that can affect the host (`quit`,
  `device_add` with host-backed devices).
- `qemu_boot`'s `extra_args` is passed to the `qemu-system-*` command line
  verbatim — anything QEMU itself accepts there, qemu-mcp accepts too, with
  no allow-list or validation beyond the conflict checks that stop it from
  colliding with flags qemu-mcp already sets itself.
- `qemu_boot`'s `hostfwd` opens a listening port on the host and forwards
  it into the guest's user-mode network, reachable from anywhere that can
  reach the host on that port.
- `qemu_disk_create`/`qemu_boot`'s `disk`/`iso`/`kernel`/`initrd` params
  read and write files on the host filesystem at whatever path the caller
  supplies, with the permissions of the process running qemu-mcp.

In short: **treat an MCP client that can call qemu-mcp's tools as trusted
to the same degree as a client you'd hand a local shell to.** qemu-mcp
assumes the agent on the other end is not adversarial. If you're wiring
qemu-mcp up to an agent (or exposing it to one) you don't fully trust,
put a sandbox or a capability boundary in front of qemu-mcp itself —
nothing inside this project does that for you.

This is the same trust boundary nearly every osdev/testing tool that
drives QEMU directly already has (`virsh`, hand-rolled boot-test scripts,
etc.) — qemu-mcp doesn't add risk beyond "an agent can now do what a
local script could already do," but it doesn't remove any either.

## Supported versions

qemu-mcp is pre-1.0 (`0.x`). Only the latest released version on PyPI
receives fixes; there are no older release lines maintained in parallel.

## Reporting a vulnerability

If you find a security issue that's specific to qemu-mcp itself (as
opposed to the trust model above, which is a deliberate design choice, not
a bug) — for example, a way to escape the pre-flight validation that lets
`extra_args`/`hostfwd`/a file path reach QEMU in a way this document
doesn't already describe, or a bug that grants more access than the
trust model above implies — please report it privately via
[GitHub Security Advisories](https://github.com/0xmortuex/qemu-mcp/security/advisories/new)
rather than opening a public issue.

Please include:
- The affected version (or commit).
- Steps to reproduce, or a minimal `qemu_boot`/tool-call sequence that
  demonstrates the issue.
- What you'd expect qemu-mcp to do instead.

There's no bug bounty program; this is a small open-source project
maintained on a best-effort basis.
