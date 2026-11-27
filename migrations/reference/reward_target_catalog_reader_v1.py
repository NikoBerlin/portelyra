"""Owner-local immutable/query-only target catalog reader for Reward UAT."""
from __future__ import annotations
import hashlib,os,re,sqlite3,stat
from pathlib import Path
from migrations.reference.statement_import_owner_uat_v1 import _open_parent_chain
class RewardTargetCatalogReaderError(RuntimeError):pass
def _fail(c):raise RewardTargetCatalogReaderError(c)
def _option(domain,context,identity):return domain+'_'+hashlib.sha256((domain+'\0'+context+'\0'+identity).encode('utf-8')).hexdigest()[:32]
def load_reward_target_catalog_v1(database:Path,context_binding_sha256:str):
 parent=None;fd=None;con=None
 try:
  if not database.is_absolute() or re.fullmatch(r'[0-9a-f]{64}',context_binding_sha256 or '') is None:_fail('reward_target_catalog_input_invalid')
  parent,name=_open_parent_chain(database);before=os.stat(name,dir_fd=parent,follow_symlinks=False)
  if not stat.S_ISREG(before.st_mode) or before.st_uid!=os.geteuid() or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1:_fail('reward_target_catalog_source_invalid')
  fd=os.open(name,os.O_RDONLY|os.O_CLOEXEC|getattr(os,'O_NOFOLLOW',0),dir_fd=parent);opened=os.fstat(fd)
  if (opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns)!=(before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns):_fail('reward_target_catalog_source_changed')
  con=sqlite3.connect(f'file:/proc/self/fd/{fd}?mode=ro&immutable=1',uri=True);con.row_factory=sqlite3.Row;con.execute('PRAGMA query_only=ON')
  if con.execute('PRAGMA query_only').fetchone()[0]!=1 or con.execute('PRAGMA user_version').fetchone()[0]!=202:_fail('reward_target_catalog_schema_invalid')
  portfolios=con.execute("SELECT portfolio_id,display_name,base_currency FROM portfolio WHERE status='active' ORDER BY display_name COLLATE NOCASE,portfolio_id").fetchall();assets=con.execute("SELECT asset_id,display_name,asset_type,price_currency FROM asset WHERE status='active' AND asset_type<>'cash' ORDER BY display_name COLLATE NOCASE,asset_id").fetchall();accounts=con.execute("SELECT account_id,portfolio_id,display_name,account_type,institution_label FROM account WHERE status='active' AND account_type IN ('securities','crypto_wallet','other') ORDER BY display_name COLLATE NOCASE,account_id").fetchall()
  if not portfolios or not assets or not accounts:_fail('reward_target_catalog_empty')
  pkeys={x['portfolio_id']:_option('portfolio',context_binding_sha256,x['portfolio_id']) for x in portfolios};akeys={x['asset_id']:_option('asset',context_binding_sha256,x['asset_id']) for x in assets};asset_options=[]
  for p in portfolios:
   for a in assets:asset_options.append({'asset_type':a['asset_type'],'label':a['display_name'],'option_key':akeys[a['asset_id']],'portfolio_option_key':pkeys[p['portfolio_id']],'price_currency':a['price_currency']})
  account_options=[{'account_purpose':x['account_type'],'institution_label':x['institution_label'],'label':x['display_name'],'option_key':_option('account',context_binding_sha256,x['account_id']),'portfolio_option_key':pkeys[x['portfolio_id']],'supported_asset_option_keys':sorted(akeys.values())} for x in accounts if x['portfolio_id'] in pkeys]
  if not account_options:_fail('reward_target_catalog_empty')
  after=os.fstat(fd)
  if (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)!=(opened.st_dev,opened.st_ino,opened.st_size,opened.st_mtime_ns):_fail('reward_target_catalog_source_changed')
  return {'account_options':account_options,'asset_options':asset_options,'portfolio_options':[{'base_currency':x['base_currency'],'label':x['display_name'],'option_key':pkeys[x['portfolio_id']]} for x in portfolios],'private_canonical_ids_exposed':False,'query_only':True}
 except RewardTargetCatalogReaderError:raise
 except Exception as e:raise RewardTargetCatalogReaderError('reward_target_catalog_source_invalid') from e
 finally:
  if con is not None:con.close()
  if fd is not None:os.close(fd)
  if parent is not None:os.close(parent)
