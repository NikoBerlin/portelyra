#!/usr/bin/env python3
"""Fail-closed Linux sandbox for one allowlisted Import Plugin process."""

from __future__ import annotations

import argparse
import ctypes
import errno
import os
from pathlib import Path
import platform
import resource
import sys


ISOLATION_UNAVAILABLE_EXIT = 78
EXECUTION_FAILED_EXIT = 79

_LANDLOCK_CREATE_RULESET = 444
_LANDLOCK_ADD_RULE = 445
_LANDLOCK_RESTRICT_SELF = 446
_LANDLOCK_CREATE_RULESET_VERSION = 1
_LANDLOCK_RULE_PATH_BENEATH = 1

_FS_EXECUTE = 1 << 0
_FS_WRITE_FILE = 1 << 1
_FS_READ_FILE = 1 << 2
_FS_READ_DIR = 1 << 3
_FS_REMOVE_DIR = 1 << 4
_FS_REMOVE_FILE = 1 << 5
_FS_MAKE_CHAR = 1 << 6
_FS_MAKE_DIR = 1 << 7
_FS_MAKE_REG = 1 << 8
_FS_MAKE_SOCK = 1 << 9
_FS_MAKE_FIFO = 1 << 10
_FS_MAKE_BLOCK = 1 << 11
_FS_MAKE_SYM = 1 << 12
_FS_REFER = 1 << 13
_FS_TRUNCATE = 1 << 14
_FS_IOCTL_DEV = 1 << 15

_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2
_BPF_LD_W_ABS = 0x20
_BPF_JMP_JEQ_K = 0x15
_BPF_RET_K = 0x06
_SECCOMP_RET_KILL_PROCESS = 0x80000000
_SECCOMP_RET_ERRNO = 0x00050000
_SECCOMP_RET_ALLOW = 0x7FFF0000


class _LandlockPathBeneath(ctypes.Structure):
    _fields_ = [("allowed_access", ctypes.c_uint64), ("parent_fd", ctypes.c_int32)]


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("filter", ctypes.POINTER(_SockFilter))]


def _syscall(libc: ctypes.CDLL, number: int, *arguments: object) -> int:
    result = int(libc.syscall(number, *arguments))
    if result < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return result


def _handled_fs_rights(abi: int) -> int:
    rights = (1 << 13) - 1
    if abi >= 2:
        rights |= _FS_REFER
    if abi >= 3:
        rights |= _FS_TRUNCATE
    if abi >= 5:
        rights |= _FS_IOCTL_DEV
    return rights


def _ruleset_buffer(abi: int, handled_fs: int) -> tuple[ctypes.Array[ctypes.c_char], int]:
    size = 24 if abi >= 6 else 16 if abi >= 4 else 8
    buffer = ctypes.create_string_buffer(size)
    ctypes.c_uint64.from_buffer(buffer, 0).value = handled_fs
    return buffer, size


def _add_landlock_path_rule(
    libc: ctypes.CDLL,
    ruleset_fd: int,
    path: Path,
    allowed_access: int,
) -> None:
    resolved = path.resolve(strict=True)
    descriptor = os.open(resolved, getattr(os, "O_PATH", os.O_RDONLY) | os.O_CLOEXEC)
    try:
        attribute = _LandlockPathBeneath(allowed_access=allowed_access, parent_fd=descriptor)
        _syscall(
            libc,
            _LANDLOCK_ADD_RULE,
            ruleset_fd,
            _LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(attribute),
            0,
        )
    finally:
        os.close(descriptor)


def _runtime_root(executable: Path) -> Path:
    resolved = executable.resolve(strict=True)
    if not resolved.is_file():
        raise OSError(errno.EINVAL, "invalid runtime executable")
    parent = resolved.parent
    root = parent.parent if parent.name.lower() in {"bin", "scripts"} else parent
    if root == Path("/") or not root.is_dir():
        raise OSError(errno.EINVAL, "invalid runtime root")
    return root


def _restrict_filesystem(
    runtime_root: Path,
    entry: Path,
    source: Path,
    output: Path,
    temporary: Path,
    support_paths: tuple[Path, ...],
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    abi = _syscall(
        libc,
        _LANDLOCK_CREATE_RULESET,
        0,
        0,
        _LANDLOCK_CREATE_RULESET_VERSION,
    )
    if abi < 3:
        raise OSError(errno.ENOSYS, "Landlock ABI too old")
    handled = _handled_fs_rights(abi)
    buffer, size = _ruleset_buffer(abi, handled)
    ruleset_fd = _syscall(
        libc, _LANDLOCK_CREATE_RULESET, ctypes.byref(buffer), size, 0
    )
    read_directory = _FS_EXECUTE | _FS_READ_FILE | _FS_READ_DIR
    read_file = _FS_READ_FILE
    writable_directory = handled
    device_file = _FS_READ_FILE | _FS_WRITE_FILE
    if abi >= 5:
        device_file |= _FS_IOCTL_DEV
    try:
        for path in (Path("/usr"), Path("/etc/R"), runtime_root):
            if path.exists():
                _add_landlock_path_rule(libc, ruleset_fd, path, read_directory)
        for path in (
            Path("/etc/ld.so.cache"), Path("/etc/localtime"),
            Path("/dev/urandom"), Path("/dev/random"),
        ):
            if path.exists():
                _add_landlock_path_rule(libc, ruleset_fd, path, read_file)
        if Path("/dev/null").exists():
            _add_landlock_path_rule(libc, ruleset_fd, Path("/dev/null"), device_file)
        _add_landlock_path_rule(libc, ruleset_fd, entry, read_file)
        _add_landlock_path_rule(libc, ruleset_fd, source, read_file)
        for path in support_paths:
            _add_landlock_path_rule(
                libc,
                ruleset_fd,
                path,
                read_directory if path.is_dir() else read_file,
            )
        _add_landlock_path_rule(libc, ruleset_fd, output, writable_directory)
        _add_landlock_path_rule(libc, ruleset_fd, temporary, writable_directory)
        if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            code = ctypes.get_errno()
            raise OSError(code, os.strerror(code))
        _syscall(libc, _LANDLOCK_RESTRICT_SELF, ruleset_fd, 0)
    finally:
        os.close(ruleset_fd)


def _network_syscalls() -> tuple[int, int, int]:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return 0xC000003E, 41, 53
    if machine in {"aarch64", "arm64"}:
        return 0xC00000B7, 198, 199
    raise OSError(errno.ENOSYS, "unsupported seccomp architecture")


def _deny_socket_creation() -> None:
    architecture, socket_call, socketpair_call = _network_syscalls()
    blocked = [socket_call, socketpair_call]
    if architecture == 0xC000003E:
        blocked.extend([0x40000000 | socket_call, 0x40000000 | socketpair_call])
    instructions = [
        _SockFilter(_BPF_LD_W_ABS, 0, 0, 4),
        _SockFilter(_BPF_JMP_JEQ_K, 1, 0, architecture),
        _SockFilter(_BPF_RET_K, 0, 0, _SECCOMP_RET_KILL_PROCESS),
        _SockFilter(_BPF_LD_W_ABS, 0, 0, 0),
    ]
    for syscall_number in blocked:
        instructions.extend([
            _SockFilter(_BPF_JMP_JEQ_K, 0, 1, syscall_number),
            _SockFilter(_BPF_RET_K, 0, 0, _SECCOMP_RET_ERRNO | errno.EPERM),
        ])
    instructions.append(_SockFilter(_BPF_RET_K, 0, 0, _SECCOMP_RET_ALLOW))
    array_type = _SockFilter * len(instructions)
    filters = array_type(*instructions)
    program = _SockFprog(length=len(filters), filter=filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    if libc.prctl(_PR_SET_SECCOMP, _SECCOMP_MODE_FILTER, ctypes.byref(program)) != 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))


def _resource_limits(timeout_seconds: int) -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (timeout_seconds + 1, timeout_seconds + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    memory_limit = 2 * 1024 * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    runtime = parser.add_mutually_exclusive_group(required=True)
    runtime.add_argument("--rscript")
    runtime.add_argument("--python")
    parser.add_argument("--entry", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--temporary", required=True)
    parser.add_argument("--support", action="append", default=[])
    parser.add_argument("--timeout-seconds", required=True, type=int)
    arguments = parser.parse_args()
    try:
        executable = Path(
            arguments.rscript if arguments.rscript is not None else arguments.python
        ).resolve(strict=True)
        entry = Path(arguments.entry).resolve(strict=True)
        source = Path(arguments.source).resolve(strict=True)
        output = Path(arguments.output).resolve(strict=True)
        temporary = Path(arguments.temporary).resolve(strict=True)
        support_paths = tuple(Path(path).resolve(strict=True) for path in arguments.support)
        if not output.is_dir() or not temporary.is_dir():
            raise OSError(errno.EINVAL, "invalid sandbox directory")
        _resource_limits(arguments.timeout_seconds)
        _restrict_filesystem(
            _runtime_root(executable), entry, source, output, temporary, support_paths
        )
        _deny_socket_creation()
        if arguments.rscript is not None:
            argv = [str(executable), "--vanilla", str(entry), str(source), str(output)]
        else:
            argv = [str(executable), "-I", "-B", str(entry), str(source), str(output)]
        os.execve(executable, argv, os.environ)
    except Exception:
        return ISOLATION_UNAVAILABLE_EXIT
    return EXECUTION_FAILED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
