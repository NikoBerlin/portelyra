"""GTK confirmation for read-free ADR-168 cross-boundary recovery."""
from migrations.reference.statement_source_mapping_recovery_v1 import StatementSourceMappingRecoveryError
def gtk_statement_source_mapping_recovery_confirmation_v1(preview):
 try:
  import gi;gi.require_version('Gdk','4.0');gi.require_version('Gtk','4.0');from gi.repository import Gdk,GLib,Gtk;Gtk.init()
  if Gdk.Display.get_default() is None:raise RuntimeError()
 except Exception as e:raise StatementSourceMappingRecoveryError('statement_source_mapping_recovery_boundary_failed') from e
 d=Gtk.Dialog(title='Portelyra – abgebrochenen Mapping-Attempt read-frei abschließen');d.set_modal(True);d.set_default_size(700,360);d.add_button('Abbrechen',Gtk.ResponseType.CANCEL);d.add_button('Ohne erneuten CSV-Read recovern',Gtk.ResponseType.OK);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
 for m in ('top','bottom','start','end'):getattr(box,'set_margin_'+m)(16)
 box.append(Gtk.Label(label='Es wird ausschließlich eine fehlende Terminal-Failure-Datei create-only ergänzt. Die Statement-CSV wird nicht ausgewählt oder geöffnet.',wrap=True,xalign=0));check=Gtk.CheckButton(label='Ich bestätige: kein Source-Read, kein Retry, kein Mapping-Overlay und keine Produktdaten.');box.append(check);error=Gtk.Label(label='',xalign=0);error.add_css_class('error');box.append(error);d.get_content_area().append(box);state={'value':None};loop=GLib.MainLoop()
 def response(current,code):
  if code!=Gtk.ResponseType.OK:current.destroy();loop.quit();return
  if not check.get_active():error.set_text('Die ausdrückliche Bestätigung ist erforderlich.');return
  state['value']={**preview,'owner_confirms_no_source_reread':True};current.destroy();loop.quit()
 d.connect('response',response);d.present();loop.run();return state['value']
