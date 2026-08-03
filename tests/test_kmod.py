# SPDX-License-Identifier: LGPL-2.1-or-later

import contextlib
import subprocess
from collections.abc import Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Optional, cast

import pytest

import mkosi
from mkosi import kmod, run_depmod
from mkosi.context import Context
from mkosi.util import PathString


class FakeConfig:
    overlay = False
    image = "main"


class FakeContext:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.config = FakeConfig()
        self.sandbox_options: list[list[PathString]] = []
        self.sandbox_value = contextlib.nullcontext(["tools-tree"])

    def rootoptions(self, dst: PathString = "/buildroot", *, readonly: bool = False) -> list[str]:
        return ["--ro-bind" if readonly else "--bind", str(self.root), str(dst)]

    def sandbox(
        self,
        *,
        network: bool = False,
        devices: bool = False,
        scripts: Optional[Path] = None,
        options: Sequence[PathString] = (),
    ) -> AbstractContextManager[list[PathString]]:
        self.sandbox_options += [list(options)]
        return self.sandbox_value


def test_run_depmod_uses_tools_tree_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    modulesd = tmp_path / "usr/lib/modules/1.2.3"
    modulesd.mkdir(parents=True)
    (modulesd / "example.ko").touch()

    context = FakeContext(tmp_path)
    calls: list[tuple[list[PathString], Any]] = []

    def fake_run(
        cmdline: Sequence[PathString],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((list(cmdline), kwargs["sandbox"]))
        return subprocess.CompletedProcess(list(cmdline), 0)

    monkeypatch.setattr(mkosi, "run", fake_run)

    # Cache mode skips unrelated module-filter preprocessing while still
    # executing depmod for every valid kernel module directory.
    run_depmod(cast(Context, context), cache=True)

    assert context.sandbox_options == [["--bind", str(tmp_path), "/buildroot"]]
    assert calls == [
        (["depmod", "--basedir", "/buildroot", "--all", "1.2.3"], context.sandbox_value)
    ]


def test_globs_match_module() -> None:
    assert kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["ahci"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz.2", ["ahci"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["ata"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["drivers"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["/drivers"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["/drivers"])
    assert not kmod.globs_match_module("drivers/ata/ahci-2.ko.xz", ["ahci"])
    assert not kmod.globs_match_module("drivers/ata/ahci2.ko.zst", ["ahci"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["ata/*"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["/ata/*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["drivers/*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["/drivers/*"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko", ["ahci/*"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko", ["bahci*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.zst", ["ahci*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["ahc*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["ah*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["ata/"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["drivers/"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["drivers/ata/"])

    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["-ahci", "*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko", ["-ahci", "*", "ahciahci"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["-ahci", "*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.zst", ["-ahci", "*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.gz", ["-ahci", "*"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.gz", ["-ahci", "drivers/"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.gz", ["-ahci", "ata/"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.gz", ["-ahci", "ata/ata/"])
    assert kmod.globs_match_module("drivers/ata/ahci.ko.gz", ["-ahci", "drivers/ata/"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko", ["*", "-ahci"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko", ["ahci", "-*"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.zst", ["-*"])
    assert not kmod.globs_match_module("drivers/ata/ahci.ko.xz", ["-*"])

    # absolute glob behavior unchanged when paths are relative to /lib/module/<kver>
    assert kmod.globs_match_module("kernel/drivers/ata/ahci.ko", ["drivers/*"])
    assert kmod.globs_match_module("kernel/drivers/ata/ahci.ko", ["/drivers/*"])
    assert not kmod.globs_match_module("kernel/drivers/ata/ahci.ko.xz", ["/ata/*"])

    # absolute globs match both relative to kernel/ and module_dir root
    assert kmod.globs_match_module("kernel/drivers/ata/ahci.ko.xz", ["/drivers/ata/ahci"])
    assert kmod.globs_match_module("kernel/drivers/ata/ahci.ko.xz", ["/kernel/drivers/ata/ahci"])


def test_normalize_module_glob() -> None:
    assert kmod.normalize_module_glob("raid[0-9]") == "raid[0-9]"
    assert kmod.normalize_module_glob("raid[0_9]") == "raid[0_9]"
    assert kmod.normalize_module_glob("raid[0_9]a_z") == "raid[0_9]a-z"
    assert kmod.normalize_module_glob("0_9") == "0-9"
    assert kmod.normalize_module_glob("[0_9") == "[0_9"
    assert kmod.normalize_module_glob("0_9]") == "0-9]"
    assert kmod.normalize_module_glob("raid[0_9]a_z[a_c]") == "raid[0_9]a-z[a_c]"
