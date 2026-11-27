#!/usr/bin/env python3
"""Provider-neutral exact Reward valuation evidence proposal."""
from __future__ import annotations
from decimal import Decimal,InvalidOperation
from datetime import date as Date
from fractions import Fraction
import hashlib,json,re
from typing import Any,Mapping
D=re.compile(r"^(0|[1-9][0-9]*)(?:\.[0-9]+)?$");DATE=re.compile(r"^\d{4}-\d{2}-\d{2}$");UTC=re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$");CCY=re.compile(r"^[A-Z]{3}$");FP=re.compile(r"^[a-f0-9]{64}$")
CODES=frozenset({'reward_valuation_request_invalid','reward_valuation_asset_evidence_invalid','reward_valuation_fx_evidence_invalid','reward_valuation_intraday_unavailable','reward_valuation_daily_fallback_confirmation_required','reward_valuation_currency_route_unsupported','reward_valuation_nonterminating_exact_result'})
class RewardValuationV1Error(RuntimeError):
 def __init__(self,code):self.code=code;super().__init__(code)
def _abort(c):raise RewardValuationV1Error(c)
def _canon(v):return json.dumps(v,ensure_ascii=True,allow_nan=False,sort_keys=True,separators=(',',':'))
def _sha(v):return hashlib.sha256(_canon(v).encode()).hexdigest()
def _dec(v,positive=True):
 if not isinstance(v,str) or not D.fullmatch(v):_abort('reward_valuation_request_invalid')
 try:x=Decimal(v)
 except InvalidOperation:_abort('reward_valuation_request_invalid')
 if (positive and x<=0) or (not positive and x<0):_abort('reward_valuation_request_invalid')
 return x
def _fraction(value):return Fraction(value)
def _out(x):
 if isinstance(x,Decimal):x=_fraction(x)
 d=x.denominator;c2=c5=0
 while d%2==0:d//=2;c2+=1
 while d%5==0:d//=5;c5+=1
 if d!=1:_abort('reward_valuation_nonterminating_exact_result')
 scale=max(c2,c5);scaled=x.numerator*(2**(scale-c2))*(5**(scale-c5));digits=str(abs(scaled)).rjust(scale+1,'0');s=('-' if scaled<0 else '')+(digits[:-scale]+'.'+digits[-scale:] if scale else digits);s=s.rstrip('0').rstrip('.') if scale else s;return s or '0'
def _evidence(v,kind,mode,date,event_at):
 if not isinstance(v,Mapping) or v.get('evidence_kind')!=kind or v.get('observation_mode')!=mode or not isinstance(v.get('evidence_fingerprint'),str) or not FP.fullmatch(v['evidence_fingerprint']) or not isinstance(v.get('currency'),str) or not CCY.fullmatch(v['currency']):_abort('reward_valuation_asset_evidence_invalid' if kind=='asset_price' else 'reward_valuation_fx_evidence_invalid')
 _dec(v.get('value_decimal'))
 if mode=='intraday_observation':
  if not isinstance(v.get('observed_at_utc'),str) or not UTC.fullmatch(v['observed_at_utc']) or v['observed_at_utc']>event_at:_abort('reward_valuation_intraday_unavailable')
 else:
  if kind=='asset_price' and v.get('observation_date')!=date:_abort('reward_valuation_asset_evidence_invalid')
  if kind=='fx_rate':
   observation_date=v.get('observation_date');policy=v.get('selection_basis','exact_date');age=v.get('rate_age_days',0)
   if not isinstance(observation_date,str) or not DATE.fullmatch(observation_date) or policy not in {'exact_date','prior_observation'} or not isinstance(age,int) or isinstance(age,bool):_abort('reward_valuation_fx_evidence_invalid')
   try:actual_age=(Date.fromisoformat(date)-Date.fromisoformat(observation_date)).days
   except ValueError:_abort('reward_valuation_fx_evidence_invalid')
   if actual_age!=age or (policy=='exact_date' and age!=0) or (policy=='prior_observation' and (age<1 or age>3)):_abort('reward_valuation_fx_evidence_invalid')
 return dict(v)
def preview_reward_valuation_v1(request:Mapping[str,Any],asset_evidence:Mapping[str,Any],fx_evidence:Mapping[str,Any]|None=None):
 if not isinstance(request,Mapping) or request.get('mode') not in {'intraday_observation','daily_close_fallback'} or request.get('event_type')!='reward' or not isinstance(request.get('local_date'),str) or not DATE.fullmatch(request['local_date']) or not isinstance(request.get('event_at_utc'),str) or not UTC.fullmatch(request['event_at_utc']) or not isinstance(request.get('asset_currency'),str) or not CCY.fullmatch(request['asset_currency']) or not isinstance(request.get('quote_currency'),str) or not CCY.fullmatch(request['quote_currency']) or not isinstance(request.get('valuation_currency'),str) or not CCY.fullmatch(request['valuation_currency']):_abort('reward_valuation_request_invalid')
 qty=_dec(request.get('eligible_quantity_decimal'));mode=request['mode'];asset=_evidence(asset_evidence,'asset_price',mode,request['local_date'],request['event_at_utc'])
 if asset['currency']!=request['quote_currency']:_abort('reward_valuation_asset_evidence_invalid')
 rate=Fraction(1);fx_fp=None;route='identity'
 if request['quote_currency']!=request['valuation_currency']:
  if fx_evidence is None:_abort('reward_valuation_fx_evidence_invalid')
  fx=_evidence(fx_evidence,'fx_rate',mode,request['local_date'],request['event_at_utc']);base=fx.get('base_currency');quote=fx.get('quote_currency')
  if base==request['quote_currency'] and quote==request['valuation_currency']:rate=_fraction(_dec(fx['value_decimal']));route='direct'
  elif base==request['valuation_currency'] and quote==request['quote_currency']:
   rate=Fraction(1,1)/_fraction(_dec(fx['value_decimal']))
   route='inverse'
  else:_abort('reward_valuation_currency_route_unsupported')
  fx_fp=fx['evidence_fingerprint']
 unit=_fraction(_dec(asset['value_decimal']))*rate;total=_fraction(qty)*unit
 body={'contract_version':'reward_valuation_candidate_v1','status':'pending_confirmation','mode':mode,'local_date':request['local_date'],'eligible_quantity_decimal':_out(qty),'asset_currency':request['asset_currency'],'quote_currency':request['quote_currency'],'valuation_currency':request['valuation_currency'],'unit_price_decimal':_out(unit),'fiat_total_decimal':_out(total),'fx_route':route,'asset_evidence_fingerprint':asset['evidence_fingerprint'],'fx_evidence_fingerprint':fx_fp,'fx_observation_date':None if fx_evidence is None else fx.get('observation_date'),'fx_rate_age_days':None if fx_evidence is None else fx.get('rate_age_days',0),'fx_selection_basis':'identity' if fx_evidence is None else fx.get('selection_basis','exact_date'),'fallback_confirmation_required':mode=='daily_close_fallback','provider_access':False,'network_access':False,'activity_draft_write':False,'canonical_write':False};body['candidate_fingerprint']=_sha(body);return body
def preview_source_reward_fx_valuation_v1(request:Mapping[str,Any],fx_evidence:Mapping[str,Any]):
 if not isinstance(request,Mapping) or request.get('mode') not in {'source_fiat_total_fx','source_unit_price_fx'} or request.get('event_type')!='reward' or not isinstance(request.get('local_date'),str) or not DATE.fullmatch(request['local_date']) or not isinstance(request.get('event_at_utc'),str) or not UTC.fullmatch(request['event_at_utc']) or not isinstance(request.get('source_currency'),str) or not CCY.fullmatch(request['source_currency']) or not isinstance(request.get('valuation_currency'),str) or not CCY.fullmatch(request['valuation_currency']) or not isinstance(request.get('source_evidence_fingerprint'),str) or not FP.fullmatch(request['source_evidence_fingerprint']):_abort('reward_valuation_request_invalid')
 qty=_fraction(_dec(request.get('eligible_quantity_decimal')));source_value=_fraction(_dec(request.get('source_value_decimal')));source_total=source_value if request['mode']=='source_fiat_total_fx' else qty*source_value
 fx=_evidence(fx_evidence,'fx_rate','daily_close_fallback',request['local_date'],request['event_at_utc']);base=fx.get('base_currency');quote=fx.get('quote_currency')
 if base==request['source_currency'] and quote==request['valuation_currency']:rate=_fraction(_dec(fx['value_decimal']));route='direct'
 elif base==request['valuation_currency'] and quote==request['source_currency']:rate=Fraction(1,1)/_fraction(_dec(fx['value_decimal']));route='inverse'
 else:_abort('reward_valuation_currency_route_unsupported')
 total=source_total*rate
 body={'contract_version':'reward_valuation_candidate_v1','status':'pending_confirmation','mode':request['mode'],'local_date':request['local_date'],'eligible_quantity_decimal':_out(qty),'asset_currency':request.get('asset_currency','AST'),'quote_currency':request['source_currency'],'valuation_currency':request['valuation_currency'],'unit_price_decimal':None,'fiat_total_decimal':_out(total),'fx_route':route,'asset_evidence_fingerprint':None,'source_valuation_evidence_fingerprint':request['source_evidence_fingerprint'],'fx_evidence_fingerprint':fx['evidence_fingerprint'],'fx_observation_date':fx['observation_date'],'fx_rate_age_days':fx.get('rate_age_days',0),'fx_selection_basis':fx.get('selection_basis','exact_date'),'fallback_confirmation_required':True,'provider_access':False,'network_access':False,'activity_draft_write':False,'canonical_write':False};body['candidate_fingerprint']=_sha(body);return body
def confirm_reward_valuation_v1(candidate,confirmed):
 if not isinstance(candidate,Mapping) or candidate.get('candidate_fingerprint')!=_sha({k:v for k,v in candidate.items() if k!='candidate_fingerprint'}):_abort('reward_valuation_request_invalid')
 if candidate['mode'] in {'daily_close_fallback','source_fiat_total_fx','source_unit_price_fx'} and confirmed is not True:_abort('reward_valuation_daily_fallback_confirmation_required')
 evidence={'contract_version':'reward_valuation_evidence_v1','status':'confirmed','valuation_method':candidate['mode'],'local_date':candidate['local_date'],'unit_price_decimal':candidate['unit_price_decimal'],'fiat_total_decimal':candidate['fiat_total_decimal'],'valuation_currency':candidate['valuation_currency'],'fx_route':candidate['fx_route'],'fx_observation_date':candidate.get('fx_observation_date'),'fx_rate_age_days':candidate.get('fx_rate_age_days'),'fx_selection_basis':candidate.get('fx_selection_basis'),'asset_evidence_fingerprint':candidate['asset_evidence_fingerprint'],'fx_evidence_fingerprint':candidate['fx_evidence_fingerprint'],'candidate_fingerprint':candidate['candidate_fingerprint'],'provider_access':False,'activity_draft_write':False,'canonical_write':False}
 if candidate['mode'] in {'source_fiat_total_fx','source_unit_price_fx'}:evidence['source_valuation_evidence_fingerprint']=candidate['source_valuation_evidence_fingerprint']
 return evidence
__all__=['RewardValuationV1Error','preview_reward_valuation_v1','preview_source_reward_fx_valuation_v1','confirm_reward_valuation_v1']
