data_asset_activity_csv_error_codes_v1<-function()c("data_asset_activity_csv_state_invalid","data_asset_activity_csv_context_invalid","data_asset_activity_csv_source_invalid","data_asset_activity_csv_mapping_required","data_asset_activity_csv_preview_required","data_asset_activity_csv_confirmation_required","data_asset_activity_csv_adapter_failed")
.data_asset_activity_csv_abort<-function(code){if(!is.character(code)||length(code)!=1L||is.na(code)||!code%in%data_asset_activity_csv_error_codes_v1())stop("unregistered_data_asset_activity_csv_error",call.=FALSE);stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_asset_activity_csv_error","error","condition")))}
.data_asset_activity_csv_context<-function(context){if(!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE))||!identical(context$runtime_mode,"desktop_product")||!identical(context$role,"desktop_owner")) .data_asset_activity_csv_abort("data_asset_activity_csv_context_invalid");context}

new_data_asset_activity_csv_product_adapter_v1<-function(project_root,context){
  project_root<-normalizePath(project_root,winslash="/",mustWork=TRUE);data_space<-runtime_data_space_path(context);canonical<-runtime_canonical_path(context)
  trusted<-function(bound){.data_asset_activity_csv_context(bound);if(!identical(runtime_context_fingerprint(bound),runtime_context_fingerprint(context))) .data_asset_activity_csv_abort("data_asset_activity_csv_context_invalid");list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id=context$actor_id,role="desktop_owner")}
  run<-function(command,payload)tryCatch(.per_asset_review_adapter_run(project_root,command,payload),error=function(error){if(inherits(error,"spot_data_asset_activity_csv_error"))stop(error);.data_asset_activity_csv_abort("data_asset_activity_csv_adapter_failed")})
  list(
    inspect=function(bound,source,portfolio)run("activity-csv-inspect",list(context=trusted(bound),canonical_path=canonical,data_space_path=data_space,source_path=source,portfolio_id=portfolio))$inspection,
    preview=function(bound,inspection,mapping,at)run("activity-csv-preview",list(context=trusted(bound),canonical_path=canonical,data_space_path=data_space,trusted_inspection=inspection,mapping_selection=mapping,previewed_at_utc=at))$preview,
    confirmation=function(bound,plan,challenge,issued,expires)run("activity-csv-confirmation",list(context=trusted(bound),trusted_plan=plan,challenge_ref=challenge,issued_at_utc=issued,expires_at_utc=expires))$confirmation,
    apply=function(bound,plan,confirmation,at)run("activity-csv-apply",list(context=trusted(bound),canonical_path=canonical,data_space_path=data_space,trusted_plan=plan,confirmation=confirmation,applied_at_utc=at))$result,
    resumable=function(bound)run("activity-csv-resumable",list(context=trusted(bound),data_space_path=data_space))$resumable,
    resume=function(bound,plan_fingerprint)run("activity-csv-resume",list(context=trusted(bound),canonical_path=canonical,data_space_path=data_space,plan_fingerprint=plan_fingerprint))$result,
    export=function(bound,portfolio,asset,at)run("activity-csv-export",list(context=trusted(bound),canonical_path=canonical,data_space_path=data_space,portfolio_id=portfolio,asset_id=if(is.null(asset))NA else asset,exported_at_utc=at))$export
  )
}

new_data_asset_activity_csv_center_v1<-function(adapter){required<-c("inspect","preview","confirmation","apply","resumable","resume");if(!is.list(adapter)||!(identical(names(adapter),required)||identical(names(adapter),c(required,"export")))||!all(vapply(adapter,is.function,logical(1L)))) .data_asset_activity_csv_abort("data_asset_activity_csv_state_invalid");center<-new.env(hash=FALSE,parent=emptyenv());center$adapter<-adapter;center$inspection<-NULL;center$plan<-NULL;center$resumable<-new.env(hash=TRUE,parent=emptyenv());center$sequence<-0L;class(center)<-"spot_data_asset_activity_csv_center_v1";center}
.data_asset_activity_csv_check<-function(center){if(!inherits(center,"spot_data_asset_activity_csv_center_v1")||!is.environment(center)) .data_asset_activity_csv_abort("data_asset_activity_csv_state_invalid")}

data_asset_activity_csv_inspect_v1<-function(center,context,source_path,portfolio_id){.data_asset_activity_csv_check(center);.data_asset_activity_csv_context(context);if(!is.character(source_path)||length(source_path)!=1L||is.na(source_path)||!file.exists(source_path)||dir.exists(source_path)) .data_asset_activity_csv_abort("data_asset_activity_csv_source_invalid");value<-center$adapter$inspect(context,source_path,portfolio_id);if(!is.list(value)||!is.list(value$public_inspection)||!is.list(value$trusted_inspection)) .data_asset_activity_csv_abort("data_asset_activity_csv_adapter_failed");center$inspection<-value$trusted_inspection;center$plan<-NULL;value$public_inspection}

data_asset_activity_csv_default_mapping_v1<-function(public_inspection,input_values=list()){
  build<-function(items,prefix){result<-list();for(index in seq_along(items)){item<-items[[index]];input_name<-sprintf("%s_%03d",prefix,index);selected<-input_values[[input_name]];if(is.null(selected)||!nzchar(selected))selected<-item$auto_mapping_ref;if(is.null(selected)||!nzchar(selected)) .data_asset_activity_csv_abort("data_asset_activity_csv_mapping_required");result[[item$source_key]]<-selected};result}
  list(assets=build(public_inspection$asset_mappings,"activity_csv_asset_mapping"),accounts=build(public_inspection$account_mappings,"activity_csv_account_mapping"))
}

data_asset_activity_csv_prepare_v1<-function(center,context,mapping,now_utc){.data_asset_activity_csv_check(center);.data_asset_activity_csv_context(context);if(is.null(center$inspection)) .data_asset_activity_csv_abort("data_asset_activity_csv_source_invalid");value<-center$adapter$preview(context,center$inspection,mapping,now_utc);if(!is.list(value)||!is.list(value$public_preview)) .data_asset_activity_csv_abort("data_asset_activity_csv_adapter_failed");ready<-identical(value$public_preview$status,"ready_for_confirmation");if(ready&&!is.list(value$trusted_plan)) .data_asset_activity_csv_abort("data_asset_activity_csv_adapter_failed");center$plan<-if(ready)value$trusted_plan else NULL;value$public_preview}

data_asset_activity_csv_execute_v1<-function(center,context,confirmed,now_utc,expires_at_utc){.data_asset_activity_csv_check(center);.data_asset_activity_csv_context(context);if(is.null(center$plan)) .data_asset_activity_csv_abort("data_asset_activity_csv_preview_required");if(!isTRUE(confirmed)) .data_asset_activity_csv_abort("data_asset_activity_csv_confirmation_required");center$sequence<-center$sequence+1L;challenge<-paste0("aic_",substr(digest::digest(charToRaw(enc2utf8(paste(center$plan$plan_fingerprint,center$sequence,sep="|"))),algo="sha256",serialize=FALSE),1L,32L));confirmation<-center$adapter$confirmation(context,center$plan,challenge,now_utc,expires_at_utc);result<-center$adapter$apply(context,center$plan,confirmation,now_utc);center$plan<-NULL;result}

data_asset_activity_csv_resumable_v1<-function(center,context){.data_asset_activity_csv_check(center);.data_asset_activity_csv_context(context);value<-center$adapter$resumable(context);if(!is.list(value)||!is.list(value$candidates)) .data_asset_activity_csv_abort("data_asset_activity_csv_adapter_failed");rm(list=ls(center$resumable,all.names=TRUE),envir=center$resumable);public<-lapply(value$candidates,function(item){assign(item$resume_ref,item$plan_fingerprint,envir=center$resumable);item$plan_fingerprint<-NULL;item});list(status=value$status,candidates=public,path_exposed=FALSE,internal_id_exposed=FALSE)}

data_asset_activity_csv_resume_v1<-function(center,context,resume_ref){.data_asset_activity_csv_check(center);.data_asset_activity_csv_context(context);if(!is.character(resume_ref)||length(resume_ref)!=1L||!exists(resume_ref,envir=center$resumable,inherits=FALSE)) .data_asset_activity_csv_abort("data_asset_activity_csv_preview_required");center$adapter$resume(context,get(resume_ref,envir=center$resumable,inherits=FALSE))}

data_asset_activity_csv_template_v1<-function(path,project_root){source<-file.path(project_root,"contracts/asset-activity-csv/v1/portelyra-asset-activity.csv");if(!file.exists(source)||file.info(source)$size<=0L) .data_asset_activity_csv_abort("data_asset_activity_csv_source_invalid");bytes<-readBin(source,"raw",n=file.info(source)$size);handle<-file(path,"wb");on.exit(close(handle),add=TRUE);writeBin(bytes,handle);invisible(path)}

# Export in the import format; the content never contains internal IDs or paths.
data_asset_activity_csv_export_v1<-function(center,context,portfolio_id,asset_id,now_utc){.data_asset_activity_csv_check(center);.data_asset_activity_csv_context(context);if(is.null(center$adapter$export)) .data_asset_activity_csv_abort("data_asset_activity_csv_state_invalid");value<-center$adapter$export(context,portfolio_id,asset_id,now_utc);if(!is.list(value)||!is.character(value$content)||length(value$content)!=1L) .data_asset_activity_csv_abort("data_asset_activity_csv_adapter_failed");value}

data_asset_activity_csv_reason_labels_v1<-function()c(
  format_version_invalid="Formatversion fehlt oder ist falsch",row_key_invalid="Zeilenschlüssel ungültig (Kleinbuchstaben, Ziffern, _ oder -, mind. 3 Zeichen)",
  row_key_duplicate="Zeilenschlüssel kommt mehrfach vor",value_invalid="Wert fehlt oder ist ungültig",decimal_invalid="Zahl ungültig (Dezimalpunkt, keine Tausendertrennzeichen, keine Exponenten)",
  time_invalid="Datum/Uhrzeit ungültig",original_time_invalid="Ursprüngliches Anschaffungsdatum ungültig",currency_mismatch="Preiswährung passt nicht zu Asset und Portfolio",
  fee_invalid="Gebührenangaben widersprüchlich",event_invalid="Pflichtfelder für diesen Buchungstyp fehlen oder passen nicht",
  duplicate_existing="Identische Buchung existiert bereits",conflict_changed="Bereits gebuchte Zeile wurde verändert – Korrektur bitte über „Buchung korrigieren“",spreadsheet_number_changed="Zahl vermutlich vom Tabellenprogramm verändert (Punkt als Tausendertrennzeichen gelesen oder Nachkommastellen gerundet) – siehe Anleitung",
  conflict_unknown_export="Exportschlüssel gehört zu keiner vorhandenen Buchung",asset_type_unsupported="Für Cash und Indizes ist der CSV-Import nicht vorgesehen",asset_class_not_selected="Klasse im Portfolio nicht gewählt – dazunehmen (Einstellungen → Portfolio → Umfang dieses Portfolios) oder Zeile aus der Datei entfernen",simulation_failed="Buchung wäre nicht ausführbar (z. B. Bestand reicht nicht)")

# Umfang je Portfolio (#551, Festlegung 11.11.2026): Der CSV-Import bleibt beim Alles-oder-nichts. Zeilen einer im Portfolio nicht gewaehlten
# Klasse sperren mit Grund; der Hinweis nennt die Anzahl je Klasse und bietet "Klasse dazunehmen" (oeffnet Einstellungen -> Umfang).
data_asset_activity_csv_scope_ui_v1<-function(preview,open_settings=NULL){
  classes<-if(is.list(preview))preview$scope_classes else NULL
  if(!length(classes))return(NULL)
  listing<-paste(vapply(classes,function(item)sprintf("%s × „%s“",item$count,item$label),character(1L)),collapse=", ")
  portfolio<-if(is.character(preview$scope_portfolio_label)&&nzchar(preview$scope_portfolio_label))preview$scope_portfolio_label else "–"
  shiny::div(class="pl-field-group",
    portelyra_status_panel("Zeilen einer nicht gewählten Klasse",paste0(listing," – im Portfolio „",portfolio,"“ nicht gewählt. Der CSV-Import bucht alles oder nichts:",
      " die Klasse dazunehmen (über die Vorschau unter Einstellungen → Portfolio → Umfang dieses Portfolios) oder diese Zeilen aus der Datei entfernen und neu prüfen."),tone="warning"),
    shiny::div(class="pl-editor-actions",shiny::actionButton("activity_csv_scope_add","Klasse dazunehmen",class="btn-default",onclick=open_settings)))
}

data_asset_activity_csv_rows_frame_v1<-function(preview){
  if(is.null(preview)||!length(preview$rows))return(data.frame())
  labels<-data_asset_activity_csv_reason_labels_v1();status<-c(ready="Neu",unchanged="Unverändert",blocked="Blockiert",not_evaluated="Nicht geprüft")
  text<-function(value)if(is.null(value))""else as.character(value)
  data.frame(check.names=FALSE,
    Zeile=vapply(preview$rows,function(row)text(row$source_row_ordinal),character(1L)),
    Ergebnis=vapply(preview$rows,function(row)unname(status[text(row$status)]),character(1L)),
    Grund=vapply(preview$rows,function(row){code<-text(row$reason_code);if(!nzchar(code))return("");paste0(if(code%in%names(labels))labels[[code]]else code,if(nzchar(text(row$reason_field)))paste0(" · Spalte ",row$reason_field)else"")},character(1L)),
    Datum=vapply(preview$rows,function(row)text(row$local_date),character(1L)),
    Typ=vapply(preview$rows,function(row)text(row$event_type),character(1L)),
    Asset=vapply(preview$rows,function(row)text(row$asset_key),character(1L)),
    Konto=vapply(preview$rows,function(row)text(row$account_key),character(1L)),
    `Bestandsänderung`=vapply(preview$rows,function(row)text(row$portfolio_quantity_change_decimal),character(1L)),
    `Realisiert vor Steuern`=vapply(preview$rows,function(row)text(row$realized_gain_before_tax),character(1L)))
}

# Belegangaben im Buchungs-CSV (#439): Transaktions-ID und Adresse gehen in den Beleg-Speicher, nur in leere Felder.
data_asset_activity_csv_ready_text_v1<-function(preview){
  angaben<-as.integer(if(is.null(preview$reference_row_count))0L else preview$reference_row_count)
  neu<-as.integer(preview$ready_row_count)
  if(identical(neu,0L)&&angaben>0L)return(paste0(angaben," gebuchte Zeile(n) tragen Transaktions-ID oder Adresse. „Neue Zeilen übernehmen“ trägt nur diese Angaben ein, und nur in leere Felder; ",
    "eine Buchung entsteht nicht."))
  paste0(neu," neue Zeilen · ",preview$unchanged_row_count," unverändert",if(angaben>0L)paste0(" · ",angaben," mit Transaktions-ID oder Adresse")else"",
    ". Mit „Neue Zeilen übernehmen“ werden genau diese gebucht.")
}
data_asset_activity_csv_reference_note_v1<-function(result){
  if(identical(result$reference_status,"failed"))return("· Transaktions-ID und Adresse ließen sich nicht eintragen – im Bereich „Beleg“ der Buchung nachholen")
  geschrieben<-as.integer(if(is.null(result$reference_written_count))0L else result$reference_written_count)
  if(geschrieben>0L)paste("·",geschrieben,"Mal Transaktions-ID oder Adresse eingetragen")else""
}
data_asset_activity_csv_reference_state_v1<-function(result){
  if(identical(result$reference_status,"failed"))return(list(tone="error",title="Angaben nicht eingetragen",copy="Der Speicher der Belegangaben ließ sich nicht schreiben. Die Buchungen sind unverändert."))
  geschrieben<-as.integer(result$reference_written_count);behalten<-as.integer(result$reference_kept_count)
  list(tone="positive",title=if(geschrieben>0L)"Angaben eingetragen"else"Nichts geändert",copy=paste0(geschrieben," Buchung(en) haben jetzt Transaktions-ID oder Adresse",
    if(behalten>0L)paste0("; bei ",behalten," stand schon etwas und bleibt")else"",". Keine neue Buchung, keine neue Generation."))
}
