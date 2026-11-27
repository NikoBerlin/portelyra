"""Private GTK providers for ADR-169 Reward/Source-Account one-read UAT."""
from __future__ import annotations
import re
from typing import Any
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from migrations.reference.reward_account_owner_uat_v2 import RewardAccountOwnerUATError
from migrations.reference.statement_source_profiler_owner_uat_gtk_v1 import gtk_statement_source_profiler_selection_v1
def _gtk():
 try:
  import gi;gi.require_version('Gdk','4.0');gi.require_version('Gtk','4.0');from gi.repository import Gdk,GLib,Gtk;Gtk.init()
  if Gdk.Display.get_default() is None:raise RuntimeError()
  return GLib,Gtk
 except Exception as e:raise RewardAccountOwnerUATError('reward_account_owner_uat_boundary_failed') from e
def _combo(Gtk,items):
 c=Gtk.ComboBoxText();c.append('', '— aktiv auswählen —')
 for key,label in items:c.append(key,label)
 return c
def gtk_reward_account_authorization_v2(preview):
 GLib,Gtk=_gtk();d=Gtk.Dialog(title='Portelyra – einmaligen Reward-Read autorisieren');d.set_modal(True);d.set_default_size(720,420);d.add_button('Abbrechen',Gtk.ResponseType.CANCEL);d.add_button('Genau einen Read autorisieren',Gtk.ResponseType.OK);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
 for m in ('top','bottom','start','end'):getattr(box,'set_margin_'+m)(16)
 box.append(Gtk.Label(label='Nach der Autorisierung wird die ausgewählte CSV genau einmal gelesen. Danach werden genau ein Source-Asset und Source-Konto einem vorhandenen Portelyra-Asset und Konto zugeordnet. Abbruch verbraucht den Attempt.',wrap=True,xalign=0));checks=[Gtk.CheckButton(label=x) for x in ('Private Source-Werte bleiben nur in diesem Prozess.','Kein Retry, keine Aktivierung und keine Candidate-/Produktdaten.','Ich bestätige den Reward-only Asset×Konto-Scope.')]
 for x in checks:box.append(x)
 err=Gtk.Label(label='',xalign=0);err.add_css_class('error');box.append(err);d.get_content_area().append(box);state={'value':None};loop=GLib.MainLoop()
 def response(cur,code):
  if code!=Gtk.ResponseType.OK:cur.destroy();loop.quit();return
  if not all(x.get_active() for x in checks):err.set_text('Alle drei Bestätigungen sind erforderlich.');return
  state['value']={'activation_authorized':False,'authorization_id':preview['authorization_id'],'automatic_retry_authorized':False,'canonical_write_authorized':False,'context_binding_sha256':preview['context_binding_sha256'],'private_values_local_only_acknowledged':True,'profiler_binding_sha256':preview['profiler_binding_sha256'],'provider_access_authorized':False,'reward_scope':preview['reward_scope'],'reward_scope_acknowledged':True,'selection_binding_sha256':preview['selection_binding_sha256'],'source_read_once_authorized':True};cur.destroy();loop.quit()
 d.connect('response',response);d.present();loop.run();return state['value']
def gtk_reward_account_review_v2(review:dict[str,Any],catalog:dict[str,Any]):
 GLib,Gtk=_gtk();d=Gtk.Dialog(title='Portelyra – Reward-Importvorschau zuordnen');d.set_modal(True);d.set_default_size(1050,820);d.add_button('Abbrechen',Gtk.ResponseType.CANCEL);d.add_button('Auswahl und Bewertung prüfen',Gtk.ResponseType.OK);outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
 for m in ('top','bottom','start','end'):getattr(outer,'set_margin_'+m)(12)
 outer.append(Gtk.Label(label='Keine Auswahl ist vorausgewählt. Genau eine Source-Kontospalte, ein Source-Asset/-Konto und ein vorhandenes Ziel-Asset/-Konto wählen. Andere Zeilen bleiben deferred.',wrap=True,xalign=0));scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);unknown=[x for x in review['column_dispositions'] if x['status']=='owner_role_review_required'];account_col=_combo(Gtk,[(str(x['column_ordinal']),f"Spalte {x['column_ordinal']}: {x['raw_header']}") for x in unknown]);box.append(Gtk.Label(label='Source-Kontospalte',xalign=0));box.append(account_col);asset=_combo(Gtk,[]);account=_combo(Gtk,[]);box.append(Gtk.Label(label='Source-Asset',xalign=0));box.append(asset);box.append(Gtk.Label(label='Source-Konto',xalign=0));box.append(account)
 asset_idx=next((x['column_ordinal']-1 for x in review['column_dispositions'] if x['role']=='source_asset_key'),None);rows=review['private_source_rows_by_ordinal']
 def refresh_accounts(*_):
  account.remove_all();account.append('','— aktiv auswählen —');raw=account_col.get_active_id();chosen=asset.get_active_id()
  if not raw or not chosen:return
  idx=int(raw)-1
  for value in sorted({r[idx] for r in rows if r[asset_idx]==chosen}):account.append(value,value)
 def refresh_source(*_):
  asset.remove_all();asset.append('','— aktiv auswählen —');account.remove_all();account.append('','— aktiv auswählen —');raw=account_col.get_active_id()
  if not raw or asset_idx is None:return
  for value in sorted({r[asset_idx] for r in rows}):asset.append(value,value)
 account_col.connect('changed',refresh_source);asset.connect('changed',refresh_accounts)
 route_widgets=[];route_values=[('reward','Reward importieren'),('nonreward_trade_deferred','Trade deferred'),('manual_account_transfer_deferred','Transfer manuell'),('cash_domain_deferred','Cash-Domain deferred'),('diagnostic','Diagnostic')]
 for item in review['semantic_route_tuples']:
  box.append(Gtk.Label(label=f"{item['source_type']} | {item['source_subtype']} | {item['asset_class']} — {item['row_count']} Zeilen",xalign=0));c=_combo(Gtk,route_values);box.append(c);route_widgets.append((item,c))
 portfolio=_combo(Gtk,[(x['option_key'],x['label']) for x in catalog['portfolio_options']]);target_asset=_combo(Gtk,[]);target_account=_combo(Gtk,[]);box.append(Gtk.Label(label='Portelyra-Portfolio',xalign=0));box.append(portfolio);box.append(Gtk.Label(label='Vorhandenes Portelyra-Asset',xalign=0));box.append(target_asset);box.append(Gtk.Label(label='Vorhandenes Portelyra-Zielkonto',xalign=0));box.append(target_account)
 def refresh_target_accounts(*_):
  target_account.remove_all();target_account.append('','— aktiv auswählen —');p=portfolio.get_active_id();chosen=target_asset.get_active_id()
  for x in catalog['account_options']:
   if x['portfolio_option_key']==p and chosen in x['supported_asset_option_keys']:target_account.append(x['option_key'],x['label']+(f" — {x['institution_label']}" if x['institution_label'] else ''))
 def refresh_targets(*_):
  target_asset.remove_all();target_asset.append('','— aktiv auswählen —');target_account.remove_all();target_account.append('','— aktiv auswählen —');p=portfolio.get_active_id()
  for x in catalog['asset_options']:
   if x['portfolio_option_key']==p:target_asset.append(x['option_key'],f"{x['label']} ({x['price_currency']})")
 portfolio.connect('changed',refresh_targets);target_asset.connect('changed',refresh_target_accounts)
 zone=Gtk.Entry();zone.set_placeholder_text('Exakte IANA-Zeitzone, z. B. UTC oder Europe/Berlin');box.append(Gtk.Label(label=f"Erkanntes Zeitformat: {review['time_format']}. Zeitzone ausdrücklich bestätigen:",xalign=0));box.append(zone);valuation=_combo(Gtk,[('basis_missing','Fiat-Basis fehlt'),('manual_fiat_total','Fiat-Gesamtwert je Reward'),('manual_unit_price','Stückpreis je Reward'),('provider_price_planned','Providerpreis später (kein Zugriff jetzt)')]);box.append(Gtk.Label(label='Bewertungsmodus',xalign=0));box.append(valuation);checks=[Gtk.CheckButton(label=x) for x in ('Alle nicht ausgewählten Source-Assets/-Konten bleiben deferred.','Source-Saldo wird nicht verwendet; Portelyra berechnet Bestände.','Reward und Fee betreffen dasselbe Ziel-Asset und Zielkonto.','Fiat-Wert bedeutet vor persönlicher Steuer und nach Fee, bezogen auf die Nettomenge.','Preview bleibt deaktiviert; keine Candidates, Produktdaten oder automatische Wiederholung.')]
 for x in checks:box.append(x)
 err=Gtk.Label(label='',wrap=True,xalign=0);err.add_css_class('error');box.append(err);scroll.set_child(box);outer.append(scroll);d.get_content_area().append(outer);state={'base':None};loop=GLib.MainLoop()
 def response(cur,code):
  if code!=Gtk.ResponseType.OK:cur.destroy();loop.quit();return
  route={f"{x['source_type']}|{x['source_subtype']}|{x['asset_class']}":c.get_active_id() for x,c in route_widgets};required=[account_col.get_active_id(),asset.get_active_id(),account.get_active_id(),portfolio.get_active_id(),target_asset.get_active_id(),target_account.get_active_id(),valuation.get_active_id(),zone.get_text().strip()]
  if any(not x for x in required) or list(route.values()).count('reward')!=1 or any(not x for x in route.values()) or not all(x.get_active() for x in checks):err.set_text('Alle Auswahlen, genau ein Reward-Tupel und fünf Bestätigungen sind erforderlich.');return
  try:ZoneInfo(zone.get_text().strip())
  except (ZoneInfoNotFoundError,ValueError):err.set_text('Die exakte IANA-Zeitzone ist ungültig.');return
  state['base']={'fee_sign_convention':'nonnegative_fee_subtracted','owner_acknowledgements':{'disabled_only':True,'fiat_value_before_tax_after_fee':True,'no_activation':True,'row_complete':True,'source_balance_not_used':True},'route_decisions':route,'source_account':account.get_active_id(),'source_account_column_ordinal':int(account_col.get_active_id()),'source_asset':asset.get_active_id(),'target_account_option_key':target_account.get_active_id(),'target_asset_option_key':target_asset.get_active_id(),'target_portfolio_option_key':portfolio.get_active_id(),'time_zone':zone.get_text().strip(),'valuation_mode':valuation.get_active_id(),'valuation_values':{}};cur.destroy();loop.quit()
 d.connect('response',response);d.present();loop.run();base=state['base']
 if base is None:return None
 if base['valuation_mode'] not in {'manual_fiat_total','manual_unit_price'}:return base
 account_idx=base['source_account_column_ordinal']-1;type_idx={x['role']:x['column_ordinal']-1 for x in review['column_dispositions'] if x['role']};reward_key=next(k for k,v in base['route_decisions'].items() if v=='reward').split('|');eligible=[r for r in rows if [r[type_idx['source_type']],r[type_idx['source_subtype']],r[type_idx['asset_class']]]==reward_key and r[asset_idx]==base['source_asset'] and r[account_idx]==base['source_account']];vd=Gtk.Dialog(title='Portelyra – Reward-Bewertungen eingeben');vd.set_modal(True);vd.set_default_size(760,650);vd.add_button('Abbrechen',Gtk.ResponseType.CANCEL);vd.add_button('Deaktivierte Vorschau versiegeln',Gtk.ResponseType.OK);vb=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
 for m in ('top','bottom','start','end'):getattr(vb,'set_margin_'+m)(12)
 entries=[]
 for r in eligible:
  vb.append(Gtk.Label(label=f"{r[type_idx['event_time_text']]} | {r[type_idx['source_row_id']]} — {'Fiat-Gesamtwert nach Fee' if base['valuation_mode']=='manual_fiat_total' else 'Fiat-Stückpreis'}",xalign=0));e=Gtk.Entry();e.set_placeholder_text('Exakte Dezimalzahl mit Punkt');vb.append(e);entries.append((r[type_idx['source_row_id']],e))
 verr=Gtk.Label(label='',xalign=0);verr.add_css_class('error');vb.append(verr);sc=Gtk.ScrolledWindow();sc.set_vexpand(True);sc.set_child(vb);vd.get_content_area().append(sc);vloop=GLib.MainLoop();ok={'value':False}
 def vresponse(cur,code):
  if code!=Gtk.ResponseType.OK:cur.destroy();vloop.quit();return
  if any(re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.[0-9]+)?',e.get_text().strip()) is None for _,e in entries):verr.set_text('Jede Zeile benötigt eine nichtnegative exakte Dezimalzahl mit Punkt.');return
  base['valuation_values']={key:e.get_text().strip() for key,e in entries};ok['value']=True;cur.destroy();vloop.quit()
 vd.connect('response',vresponse);vd.present();vloop.run();return base if ok['value'] else None
__all__=['gtk_reward_account_authorization_v2','gtk_reward_account_review_v2','gtk_statement_source_profiler_selection_v1']
