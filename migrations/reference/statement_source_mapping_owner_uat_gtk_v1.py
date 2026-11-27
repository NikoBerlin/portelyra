"""GTK providers for ADR-167; private values never leave widgets/in-memory return."""
from __future__ import annotations
from typing import Any
from migrations.reference.statement_source_mapping_overlay_v1 import DECIMALS,NONSEMANTIC,REGISTERED_ROLES,ROUTES
from migrations.reference.statement_source_mapping_owner_uat_v1 import StatementSourceMappingOwnerUATError
from migrations.reference.statement_source_profiler_owner_uat_gtk_v1 import gtk_statement_source_profiler_authorization_v1,gtk_statement_source_profiler_selection_v1
def _gtk():
 try:
  import gi;gi.require_version('Gdk','4.0');gi.require_version('Gtk','4.0');from gi.repository import Gdk,GLib,Gtk;Gtk.init()
  if Gdk.Display.get_default() is None:raise RuntimeError()
  return GLib,Gtk
 except Exception as e:raise StatementSourceMappingOwnerUATError('statement_source_mapping_owner_uat_boundary_failed') from e
def _combo(Gtk,values):
 box=Gtk.ComboBoxText();box.append('', '— aktiv auswählen —')
 for value in values:box.append(value,value)
 return box
def gtk_statement_source_mapping_owner_review_v1(review:dict[str,Any]):
 GLib,Gtk=_gtk();dialog=Gtk.Dialog(title='Portelyra – Statement-Mapping vollständig bestätigen');dialog.set_modal(True);dialog.set_default_size(1100,800);dialog.add_button('Abbrechen',Gtk.ResponseType.CANCEL);dialog.add_button('Hash-Overlay versiegeln (deaktiviert)',Gtk.ResponseType.OK)
 outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
 for m in ('top','bottom','start','end'):getattr(outer,'set_margin_'+m)(12)
 outer.append(Gtk.Label(label='Private Header und Kategorien – keine Auswahl ist vorausgewählt. Jede offene Entscheidung muss aktiv getroffen werden.',wrap=True,xalign=0));scroll=Gtk.ScrolledWindow();scroll.set_vexpand(True);content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);column_widgets=[]
 for item in review['column_dispositions']:
  if item['status']=='owner_role_review_required':
   row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8);row.append(Gtk.Label(label=f"Spalte {item['column_ordinal']}: {item['raw_header']}",xalign=0));combo=_combo(Gtk,[NONSEMANTIC]+sorted(REGISTERED_ROLES));row.append(combo);content.append(row);column_widgets.append((item,combo))
 decimal_widgets=[]
 for role,observed in sorted(review['decimal_formats'].items()):
  row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8);row.append(Gtk.Label(label=f'Decimal {role} (beobachtet: {observed})',xalign=0));combo=_combo(Gtk,sorted(DECIMALS));row.append(combo);content.append(row);decimal_widgets.append((role,combo))
 zone=Gtk.Entry();zone.set_placeholder_text('Exakte Zone aktiv eingeben, z. B. UTC oder Europe/Berlin');content.append(zone);tuple_widgets=[]
 for n,item in enumerate(review['semantic_route_tuples'],1):
  row=Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL,spacing=8);row.append(Gtk.Label(label=f"{item['source_type']} | {item['source_subtype']} | {item['asset_class']} | {item['row_count']} Zeilen",xalign=0));combo=_combo(Gtk,sorted(ROUTES));row.append(combo);content.append(row);tuple_widgets.append((n,combo))
 checks=[Gtk.CheckButton(label=x) for x in ('Alle Zeilen und Tupel sind vollständig disponiert.','Persistiert werden ausschließlich Hashbindungen und Counts.','Overlay bleibt deaktiviert; keine Candidates oder Produktdaten.','Keine Aktivierung oder automatische Wiederholung.')]
 for x in checks:content.append(x)
 error=Gtk.Label(label='',wrap=True,xalign=0);error.add_css_class('error');content.append(error);scroll.set_child(content);outer.append(scroll);dialog.get_content_area().append(outer);state={'value':None};loop=GLib.MainLoop()
 def response(current,code):
  if code!=Gtk.ResponseType.OK:current.destroy();loop.quit();return
  def selected(combo):return combo.get_active_id()
  if any(not selected(c) for _,c in column_widgets+decimal_widgets+tuple_widgets) or not zone.get_text().strip() or not all(x.get_active() for x in checks):error.set_text('Alle Entscheidungen und vier Bestätigungen sind erforderlich.');return
  columns=[]
  for item,combo in column_widgets:
   value=selected(combo);columns.append({'column_ordinal':item['column_ordinal'],'disposition':NONSEMANTIC if value==NONSEMANTIC else 'owner_role_mapping','role':None if value==NONSEMANTIC else value})
  state['value']={'column_decisions':columns,'decimal_decisions':{role:selected(combo) for role,combo in decimal_widgets},'owner_acknowledgements':{'disabled_only':True,'hash_only_persistence':True,'no_activation':True,'row_complete':True},'semantic_tuple_decisions':[{'tuple_ordinal':n,'route':selected(combo)} for n,combo in tuple_widgets],'time_zone_decision':{'exact_local_zone':zone.get_text().strip(),'lexical_format':review['time_format'],'owner_confirmed':True}};current.destroy();loop.quit()
 dialog.connect('response',response);dialog.present();loop.run();return state['value']
__all__=['gtk_statement_source_mapping_owner_review_v1','gtk_statement_source_profiler_authorization_v1','gtk_statement_source_profiler_selection_v1']
