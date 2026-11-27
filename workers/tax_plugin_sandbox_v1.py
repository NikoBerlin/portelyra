#!/usr/bin/env python3
"""Fail-closed Linux sandbox entry for one allowlisted Tax Model Plugin."""
from __future__ import annotations
import argparse,ctypes,errno,os
from pathlib import Path
import import_plugin_sandbox_v1 as base

def restrict(runtime_root:Path,entry:Path,source:Path,output:Path,temporary:Path,r_library:Path):
 libc=ctypes.CDLL(None,use_errno=True)
 abi=base._syscall(libc,base._LANDLOCK_CREATE_RULESET,0,0,base._LANDLOCK_CREATE_RULESET_VERSION)
 if abi<3:raise OSError(errno.ENOSYS,'Landlock ABI too old')
 handled=base._handled_fs_rights(abi);buffer,size=base._ruleset_buffer(abi,handled)
 fd=base._syscall(libc,base._LANDLOCK_CREATE_RULESET,ctypes.byref(buffer),size,0)
 read_dir=base._FS_EXECUTE|base._FS_READ_FILE|base._FS_READ_DIR;read_file=base._FS_READ_FILE;write_dir=handled;device=base._FS_READ_FILE|base._FS_WRITE_FILE
 if abi>=5:device|=base._FS_IOCTL_DEV
 try:
  for path in (Path('/usr'),Path('/etc/R'),runtime_root,r_library):
   if path.exists():base._add_landlock_path_rule(libc,fd,path,read_dir)
  for path in (Path('/etc/ld.so.cache'),Path('/etc/localtime'),Path('/dev/urandom'),Path('/dev/random')):
   if path.exists():base._add_landlock_path_rule(libc,fd,path,read_file)
  if Path('/dev/null').exists():base._add_landlock_path_rule(libc,fd,Path('/dev/null'),device)
  base._add_landlock_path_rule(libc,fd,entry,read_file);base._add_landlock_path_rule(libc,fd,source,read_file);base._add_landlock_path_rule(libc,fd,output,write_dir);base._add_landlock_path_rule(libc,fd,temporary,write_dir)
  if libc.prctl(base._PR_SET_NO_NEW_PRIVS,1,0,0,0)!=0:raise OSError(ctypes.get_errno(),os.strerror(ctypes.get_errno()))
  base._syscall(libc,base._LANDLOCK_RESTRICT_SELF,fd,0)
 finally:os.close(fd)

def main():
 parser=argparse.ArgumentParser(add_help=False)
 for name in ('rscript','r-library','entry','source','output','temporary'):parser.add_argument(f'--{name}',required=True)
 parser.add_argument('--timeout-seconds',required=True,type=int);a=parser.parse_args()
 try:
  rscript=Path(a.rscript).resolve(strict=True);library=Path(a.r_library).resolve(strict=True);entry=Path(a.entry).resolve(strict=True);source=Path(a.source).resolve(strict=True);output=Path(a.output).resolve(strict=True);temporary=Path(a.temporary).resolve(strict=True)
  if not output.is_dir() or not temporary.is_dir() or not library.is_dir():raise OSError(errno.EINVAL,'invalid sandbox path')
  base._resource_limits(a.timeout_seconds);restrict(base._runtime_root(rscript),entry,source,output,temporary,library);base._deny_socket_creation()
  os.execve(rscript,[str(rscript),'--vanilla',str(entry),str(source),str(output)],os.environ)
 except Exception:return base.ISOLATION_UNAVAILABLE_EXIT
 return base.EXECUTION_FAILED_EXIT
if __name__=='__main__':raise SystemExit(main())
