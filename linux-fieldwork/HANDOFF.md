# Linux Fieldwork handoff — ToolsTree depmod boundary

Updated: 2026-08-02
State: ACTIVE CANDIDATE
Branch: `linux-fieldwork/tools-tree-depmod-path`
Base: fork `main` at `33d17b2b92b87b27842767df14c362e13023f735`

## Finding

Open upstream issue `systemd/mkosi#4319` reports that a Rocky ToolsTree containing `/usr/sbin/depmod` fails when the invoking host PATH omits `/usr/sbin`. Adding `/usr/sbin` to the host PATH makes the build work.

Current source separates most ToolsTree commands correctly: `Context.sandbox()` delegates to `Config.sandbox()`, which mounts the ToolsTree and `sandbox_cmd()` installs a tools-root-aware PATH. `run_depmod()` is the exception. It invokes:

```python
run(["depmod", "--all", modulesd.name], sandbox=chroot_cmd(root=context.rootoptions))
```

That bypasses `Context.sandbox()` and therefore bypasses the configured ToolsTree for this operation.

## Candidate contract

- executable and dynamic libraries come from the configured ToolsTree;
- kernel module input and generated metadata belong to the target image;
- the invoking host PATH must not decide whether `depmod` exists.

Candidate invocation:

```python
run(
    ["depmod", "--basedir", "/buildroot", "--all", modulesd.name],
    sandbox=context.sandbox(options=context.rootoptions()),
)
```

## Branch contents

- `tests/test_kmod.py` contains a focused regression requiring the ToolsTree sandbox and `/buildroot` basedir command.
- `linux-fieldwork/0001-depmod-use-tools-tree-sandbox.patch` is an apply-ready source patch against source blob `9e35c53db3da7065d20bc4b208a69a2d8bd4e29c`.

## Evidence

### Current/candidate boundary model

```text
current [] ['depmod', '--all', '1.2.3'] chroot
candidate [['--bind', '<tmp>', '/buildroot']] ['depmod', '--basedir', '/buildroot', '--all', '1.2.3'] True
```

The current model never calls the ToolsTree sandbox. The candidate binds the target at `/buildroot`, selects the expected command, and passes the exact sandbox returned by the context.

### Patch packaging

`patch --dry-run -p1` against a source fixture containing the exact current call: PASS.

### Real depmod basedir behavior

With an isolated target root containing `usr/lib/modules/1.2.3` and the standard `/lib -> usr/lib` symlink:

```text
depmod --basedir <root> --all 1.2.3
rc=0
```

The command created `modules.dep`, `modules.dep.bin`, `modules.alias`, `modules.symbols`, and related metadata under the isolated target root.

### Overlap

Search for pull requests matching issue 4319, depmod, and ToolsTree returned no candidate.

## Expected test state

The new test is intentionally red against current source because `run_depmod()` still uses `chroot_cmd()`. It becomes green after applying the retained source patch.

The execution container cannot resolve `github.com`, so a full repository checkout and pytest run were unavailable. This is an environment retrieval limitation, not product evidence.

## Next technical step

Apply `linux-fieldwork/0001-depmod-use-tools-tree-sandbox.patch` to this branch through a full checkout or patch-capable Git interface, then run:

```text
python3 -m pytest tests/test_kmod.py
python3 -m ruff check mkosi/__init__.py tests/test_kmod.py
python3 -m mypy mkosi/__init__.py tests/test_kmod.py
```

After the unit gate, reproduce with a ToolsTree containing only `/usr/sbin/depmod` while the host PATH omits `/usr/sbin`.

## External-contact state

`false; none occurred`. No upstream issue, pull request, comment, review, discussion, or email was created.
