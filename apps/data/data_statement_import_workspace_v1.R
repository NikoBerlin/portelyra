data_statement_import_workspace_error_v1 <- function(code) {
  structure(list(message=code,call=NULL,code=code),class=c("data_statement_import_workspace_error","error","condition"))
}

data_statement_import_workspace_abort_v1 <- function(code) stop(data_statement_import_workspace_error_v1(code))

.data_statement_import_workspace_exact_names_v1 <- function(value,expected) {
  is.list(value)&&!is.null(names(value))&&identical(sort(names(value)),sort(expected))
}

.data_statement_import_workspace_text_v1 <- function(value,maximum=240L) {
  is.character(value)&&length(value)==1L&&!is.na(value)&&nzchar(value)&&nchar(value,type="bytes")<=maximum&&!grepl("\\x00",value)
}

.data_statement_import_workspace_bool_v1 <- function(value,expected=NULL) {
  valid<-is.logical(value)&&length(value)==1L&&!is.na(value)
  if(!valid)return(FALSE)
  is.null(expected)||identical(value,expected)
}

.data_statement_import_workspace_int_v1 <- function(value,minimum=0L) {
  is.numeric(value)&&length(value)==1L&&!is.na(value)&&is.finite(value)&&value==floor(value)&&value>=minimum
}

.data_statement_import_workspace_decimal_v1 <- function(value) {
  .data_statement_import_workspace_text_v1(value)&&grepl("^-?(0|[1-9][0-9]*)(\\.[0-9]+)?$",value)
}

.data_statement_import_workspace_forbidden_names_v1 <- c(
  "tenant_id","user_id","data_space_id","context","context_fingerprint","source_fingerprint",
  "manifest_fingerprint","candidate_bundle_fingerprint","result_fingerprint","source_path","fixture_path",
  "entrypoint","output_directory","attempt_id","confirmation_id","challenge","existing_event_key",
  "source_identity_binding"
)

.data_statement_import_workspace_all_names_v1 <- function(value) {
  if(!is.list(value))return(character())
  own<-names(value);if(is.null(own))own<-character()
  unique(c(own,unlist(lapply(value,.data_statement_import_workspace_all_names_v1),use.names=FALSE)))
}

.data_statement_import_workspace_fields_v1 <- c(
  "desktop_statement_import_workspace_version","status","execution_purpose","scenario","source_profile",
  "column_mappings","route_rules","identity_policy","catalog_review","valuation_review","provider_enrichment",
  "reconciliation_summary","rows","source_is_public_invented_fixture","activation_authorized",
  "activity_draft_write","automatic_retry","candidate_handoff_available","canonical_write",
  "cash_completeness_claimed","cash_handoff_available","cash_write","catalog_handoff_available","confirmation_available","context_exposed",
  "correction_confirmation_available","fingerprint_exposed","lineage_confirmation_available",
  "mapping_apply_available","network_access","normal_adapter_execution_available","owner_accepted_disabled_recorded","path_exposed",
  "portfolio_completeness_claimed","private_owner_uat_completed","private_source_read","provider_access",
  "source_profile_private_accepted","sql_access","tax_write","temporary_output_persisted","valuation_confirmation_available"
)

.data_statement_import_workspace_candidate_fields_v1 <- c(
  "account_key","amount_input_mode","asset_fee_quantity_decimal","basis_evidence_mode","event_time_evidence",
  "event_type","fee_role","gross_income_decimal","local_date","local_time","price_currency",
  "quantity_decimal","source_asset_key","source_reference","time_zone","unit_price_decimal"
)

validate_data_statement_import_workspace_v1 <- function(value,scenario=NULL) {
  fail<-function()data_statement_import_workspace_abort_v1("data_statement_import_workspace_projection_invalid")
  if(!.data_statement_import_workspace_exact_names_v1(value,.data_statement_import_workspace_fields_v1))fail()
  if(any(.data_statement_import_workspace_all_names_v1(value)%in%.data_statement_import_workspace_forbidden_names_v1))fail()
  if(!identical(value$desktop_statement_import_workspace_version,1L)&&!identical(value$desktop_statement_import_workspace_version,1))fail()
  if(!identical(value$status,"synthetic_workspace_ready")||!identical(value$execution_purpose,"public_synthetic_mapping_reconciliation"))fail()
  scenarios<-c("basis_missing","manual_fiat_total","manual_unit_price")
  if(!.data_statement_import_workspace_text_v1(value$scenario)||!value$scenario%in%scenarios||(!is.null(scenario)&&!identical(value$scenario,scenario)))fail()
  if(!.data_statement_import_workspace_bool_v1(value$source_is_public_invented_fixture,TRUE))fail()
  false_fields<-c(
    "activation_authorized","activity_draft_write","automatic_retry","candidate_handoff_available",
    "canonical_write","cash_completeness_claimed","cash_handoff_available","cash_write","catalog_handoff_available","confirmation_available",
    "context_exposed","correction_confirmation_available","fingerprint_exposed","lineage_confirmation_available",
    "mapping_apply_available","network_access","normal_adapter_execution_available","owner_accepted_disabled_recorded","path_exposed",
    "portfolio_completeness_claimed","private_owner_uat_completed","private_source_read","provider_access",
    "source_profile_private_accepted","sql_access","tax_write","temporary_output_persisted","valuation_confirmation_available"
  )
  if(any(!vapply(false_fields,function(field).data_statement_import_workspace_bool_v1(value[[field]],FALSE),logical(1))))fail()

  profile<-value$source_profile
  profile_fields<-c("column_count","export_profile","format_version","header_change_policy","header_status","institution","locale","medium","private_owner_uat_status","source_profile_id","source_profile_revision","source_profile_status")
  if(!.data_statement_import_workspace_exact_names_v1(profile,profile_fields))fail()
  expected_profile<-list(
    export_profile="ledger_csv",format_version="synthetic_contract_v1",header_change_policy="new_immutable_profile_revision_required",
    header_status="exact_match",institution="kraken",locale="en",medium="csv",private_owner_uat_status="not_completed",
    source_profile_id="kraken_ledger_csv_source_v1",source_profile_revision="r1",
    source_profile_status="synthetic_pending_private_owner_uat"
  )
  if(!.data_statement_import_workspace_int_v1(profile$column_count,1L)||any(!vapply(names(expected_profile),function(field)identical(profile[[field]],expected_profile[[field]]),logical(1))))fail()

  expected_columns<-c("txid","refid","time","type","subtype","aclass","asset","amount","fee","balance")
  expected_roles<-c("source_row_id","source_group_id","event_time_utc_text","source_type","source_subtype","asset_class","source_asset_key","signed_quantity_decimal","asset_fee_quantity_decimal","balance_reconciliation_evidence")
  if(!is.list(value$column_mappings)||length(value$column_mappings)!=length(expected_columns)||profile$column_count!=length(value$column_mappings))fail()
  for(index in seq_along(value$column_mappings)) {
    item<-value$column_mappings[[index]]
    if(!.data_statement_import_workspace_exact_names_v1(item,c("disposition","required","role","source_column")))fail()
    if(!identical(item$source_column,expected_columns[[index]])||!identical(item$role,expected_roles[[index]])||!item$disposition%in%c("mapped","retained_not_imported")||!.data_statement_import_workspace_bool_v1(item$required,TRUE))fail()
  }

  if(!is.list(value$route_rules)||length(value$route_rules)!=3L)fail()
  route_pairs<-character()
  for(item in value$route_rules) {
    if(!.data_statement_import_workspace_exact_names_v1(item,c("adapter_id","domain","route","route_status","source_asset_class","source_subtype","source_type")))fail()
    if(!is.null(item$adapter_id)&&!.data_statement_import_workspace_text_v1(item$adapter_id))fail()
    if(!item$domain%in%c("asset_activity","cash")||!item$route%in%c("reward","trade","cash"))fail()
    if(any(!vapply(c("route_status","source_asset_class","source_subtype","source_type"),function(field).data_statement_import_workspace_text_v1(item[[field]]),logical(1))))fail()
    route_pairs<-c(route_pairs,paste(item$source_type,item$source_subtype,item$source_asset_class,sep="/"))
  }
  if(anyDuplicated(route_pairs))fail()

  identity<-value$identity_policy
  if(!.data_statement_import_workspace_exact_names_v1(identity,c("date_only_matching_allowed","duplicate_txid_disposition","missing_txid_disposition","source_group_identity_components","source_ordinal_role","source_row_identity_components")))fail()
  if(!.data_statement_import_workspace_bool_v1(identity$date_only_matching_allowed,FALSE)||!identical(identity$duplicate_txid_disposition,"diagnostic")||!identical(identity$missing_txid_disposition,"diagnostic")||!identical(identity$source_ordinal_role,"closed_row_ledger_only"))fail()
  if(!is.list(identity$source_row_identity_components)||!identical(unlist(identity$source_row_identity_components,use.names=FALSE),c("source_profile_id","source_profile_revision","txid")))fail()
  if(!is.list(identity$source_group_identity_components)||!identical(unlist(identity$source_group_identity_components,use.names=FALSE),c("source_profile_id","source_profile_revision","refid","sorted_member_txids")))fail()

  catalog<-value$catalog_review
  if(!.data_statement_import_workspace_exact_names_v1(catalog,c("account_mappings","asset_mappings","catalog_creation_requests","catalog_write","portfolio_selection"))||!.data_statement_import_workspace_bool_v1(catalog$catalog_write,FALSE))fail()
  portfolio<-catalog$portfolio_selection
  if(!.data_statement_import_workspace_exact_names_v1(portfolio,c("mapping_status","target_label","target_option_key"))||!identical(portfolio$mapping_status,"selected_existing"))fail()
  if(any(!vapply(c("target_label","target_option_key"),function(field).data_statement_import_workspace_text_v1(portfolio[[field]]),logical(1))))fail()
  if(!is.list(catalog$account_mappings)||length(catalog$account_mappings)!=1L)fail()
  account<-catalog$account_mappings[[1L]]
  if(!.data_statement_import_workspace_exact_names_v1(account,c("mapping_status","source_account_scope","target_label","target_option_key"))||!identical(account$mapping_status,"matched_existing"))fail()
  if(any(!vapply(c("source_account_scope","target_label","target_option_key"),function(field).data_statement_import_workspace_text_v1(account[[field]]),logical(1))))fail()
  if(!is.list(catalog$asset_mappings)||length(catalog$asset_mappings)<1L)fail()
  source_assets<-character()
  for(item in catalog$asset_mappings) {
    if(!.data_statement_import_workspace_exact_names_v1(item,c("mapping_status","source_asset_key","target_label","target_option_key")))fail()
    if(!item$mapping_status%in%c("matched_existing","separate_catalog_handoff_required","route_deferred","cash_domain_deferred","diagnostic_only")||!.data_statement_import_workspace_text_v1(item$source_asset_key))fail()
    if(identical(item$mapping_status,"matched_existing")) {
      if(any(!vapply(c("target_label","target_option_key"),function(field).data_statement_import_workspace_text_v1(item[[field]]),logical(1))))fail()
    } else if(!is.null(item$target_label)||!is.null(item$target_option_key))fail()
    source_assets<-c(source_assets,item$source_asset_key)
  }
  if(anyDuplicated(source_assets))fail()
  if(!is.list(catalog$catalog_creation_requests))fail()
  for(item in catalog$catalog_creation_requests) {
    if(!.data_statement_import_workspace_exact_names_v1(item,c("entity_type","separate_confirmation_required","source_asset_key","synthetic_preview_status")))fail()
    if(!identical(item$entity_type,"asset")||!.data_statement_import_workspace_bool_v1(item$separate_confirmation_required,TRUE)||!identical(item$synthetic_preview_status,"ready")||!.data_statement_import_workspace_text_v1(item$source_asset_key))fail()
  }

  provider<-value$provider_enrichment
  if(!.data_statement_import_workspace_exact_names_v1(provider,c("automatic_retry","market_history_plan_available","network_access","provider_access","status")))fail()
  if(!identical(provider$status,"disabled_separate_market_history_plan_required")||any(!vapply(c("automatic_retry","market_history_plan_available","network_access","provider_access"),function(field).data_statement_import_workspace_bool_v1(provider[[field]],FALSE),logical(1))))fail()

  valuation<-value$valuation_review
  if(!.data_statement_import_workspace_exact_names_v1(valuation,c("exact_decimal_arithmetic","manual_input","rounding_applied","scenario","target_source_row_key","valuation_status")))fail()
  if(!identical(valuation$scenario,value$scenario)||!identical(valuation$target_source_row_key,"synthetic_row_03")||!.data_statement_import_workspace_bool_v1(valuation$exact_decimal_arithmetic,TRUE)||!.data_statement_import_workspace_bool_v1(valuation$rounding_applied,FALSE))fail()
  expected_valuation<-if(identical(value$scenario,"basis_missing"))"basis_missing"else paste0(value$scenario,"_exact")
  if(!identical(valuation$valuation_status,expected_valuation))fail()
  if(identical(value$scenario,"basis_missing")) {
    if(!is.null(valuation$manual_input))fail()
  } else {
    manual<-valuation$manual_input
    if(!.data_statement_import_workspace_exact_names_v1(manual,c("amount_input_mode","basis_evidence_mode","exact_local_date","exact_local_time","exact_local_zone","gross_income_decimal","observed_at_utc","price_currency","unit_price_decimal")))fail()
    if(!manual$amount_input_mode%in%c("quantity_gross_amount","quantity_unit_price")||!identical(manual$basis_evidence_mode,"valuation_confirmed_as_basis")||!identical(manual$exact_local_zone,"UTC")||!identical(manual$price_currency,"EUR"))fail()
    if(any(!vapply(c("exact_local_date","exact_local_time","observed_at_utc"),function(field).data_statement_import_workspace_text_v1(manual[[field]]),logical(1)))||!.data_statement_import_workspace_decimal_v1(manual$gross_income_decimal))fail()
    if(identical(value$scenario,"manual_unit_price")) {
      if(!.data_statement_import_workspace_decimal_v1(manual$unit_price_decimal)||!identical(manual$amount_input_mode,"quantity_unit_price"))fail()
    } else if(!is.null(manual$unit_price_decimal)||!identical(manual$amount_input_mode,"quantity_gross_amount"))fail()
  }

  summary<-value$reconciliation_summary
  if(!.data_statement_import_workspace_exact_names_v1(summary,c("candidate_projection_count","date_only_match_count","disposition_counts","handoff_ready_count","silent_drop_count","source_row_count")))fail()
  for(field in c("candidate_projection_count","date_only_match_count","handoff_ready_count","silent_drop_count","source_row_count"))if(!.data_statement_import_workspace_int_v1(summary[[field]],0L))fail()
  if(summary$source_row_count<1L||summary$date_only_match_count!=0L||summary$silent_drop_count!=0L||!is.list(summary$disposition_counts)||length(summary$disposition_counts)!=8L)fail()
  dispositions<-c("new_candidate","exact_existing_noop","existing_link_required","correction_proposed","ambiguous_match_blocked","deferred","cash_domain_deferred","diagnostic")
  count_values<-integer()
  for(index in seq_along(summary$disposition_counts)) {
    item<-summary$disposition_counts[[index]]
    if(!.data_statement_import_workspace_exact_names_v1(item,c("count","disposition"))||!identical(item$disposition,dispositions[[index]])||!.data_statement_import_workspace_int_v1(item$count,0L))fail()
    count_values<-c(count_values,as.integer(item$count))
  }
  if(sum(count_values)!=summary$source_row_count||!is.list(value$rows)||length(value$rows)!=summary$source_row_count)fail()

  row_fields<-c("candidate_values","domain","existing_match_count","fifo_revalidation_required","handoff_eligibility","mapping_status","mapped_route","predecessor_supersession_required","reason_code","reconciliation_disposition","source_group_status","source_identity_status","source_row_key","source_row_ordinal","valuation_status")
  handoffs<-c("ready_untrusted_candidate","blocked_basis_missing","excluded_exact_noop","separate_lineage_confirmation_required","separate_correction_confirmation_required","blocked_ambiguous_match","not_eligible")
  mapping_statuses<-c("matched_existing","separate_catalog_handoff_required","route_deferred","cash_domain_deferred","diagnostic_only","not_evaluated")
  valuation_statuses<-c("basis_missing","manual_unit_price_exact","manual_fiat_total_exact","not_required_exact_noop","not_applicable")
  row_keys<-character();actual_dispositions<-character();candidate_count<-0L;handoff_ready<-0L
  for(index in seq_along(value$rows)) {
    row<-value$rows[[index]]
    if(!.data_statement_import_workspace_exact_names_v1(row,row_fields)||!.data_statement_import_workspace_int_v1(row$source_row_ordinal,1L)||row$source_row_ordinal!=index)fail()
    if(!.data_statement_import_workspace_text_v1(row$source_row_key)||!grepl("^synthetic_row_[0-9]{2}$",row$source_row_key))fail()
    if(!row$reconciliation_disposition%in%dispositions||!row$handoff_eligibility%in%handoffs||!row$mapping_status%in%mapping_statuses||!row$valuation_status%in%valuation_statuses)fail()
    if(!is.null(row$domain)&&!row$domain%in%c("asset_activity","cash"))fail()
    if(!is.null(row$mapped_route)&&!row$mapped_route%in%c("reward","trade","cash"))fail()
    if(!row$source_group_status%in%c("retained_for_grouping")||!row$source_identity_status%in%c("stable_txid_bound","identity_invalid"))fail()
    if(!.data_statement_import_workspace_int_v1(row$existing_match_count,0L)||!.data_statement_import_workspace_bool_v1(row$fifo_revalidation_required)||!.data_statement_import_workspace_bool_v1(row$predecessor_supersession_required)||!.data_statement_import_workspace_text_v1(row$reason_code))fail()
    if(!is.list(row$candidate_values))fail()
    candidate_fields<-character()
    for(item in row$candidate_values) {
      if(!.data_statement_import_workspace_exact_names_v1(item,c("field","value"))||!item$field%in%.data_statement_import_workspace_candidate_fields_v1||!.data_statement_import_workspace_text_v1(item$value))fail()
      candidate_fields<-c(candidate_fields,item$field)
    }
    if(anyDuplicated(candidate_fields)||!identical(candidate_fields,sort(candidate_fields)))fail()
    if(length(row$candidate_values)>0L)candidate_count<-candidate_count+1L
    if(identical(row$handoff_eligibility,"ready_untrusted_candidate"))handoff_ready<-handoff_ready+1L
    if(identical(row$reconciliation_disposition,"correction_proposed")) {
      if(!isTRUE(row$fifo_revalidation_required)||!isTRUE(row$predecessor_supersession_required))fail()
    } else if(isTRUE(row$fifo_revalidation_required)||isTRUE(row$predecessor_supersession_required))fail()
    row_keys<-c(row_keys,row$source_row_key);actual_dispositions<-c(actual_dispositions,row$reconciliation_disposition)
  }
  if(anyDuplicated(row_keys)||candidate_count!=summary$candidate_projection_count||handoff_ready!=summary$handoff_ready_count)fail()
  actual_counts<-vapply(dispositions,function(disposition)sum(actual_dispositions==disposition),integer(1))
  if(!identical(unname(actual_counts),count_values))fail()
  value
}

.data_statement_import_workspace_read_raw_v1 <- function(path,maximum=32000000L) {
  info<-file.info(path)
  if(nrow(info)!=1L||is.na(info$size)||info$size<0||info$size>maximum)data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  connection<-file(path,"rb");on.exit(close(connection),add=TRUE)
  readBin(connection,"raw",n=maximum+1L)
}

.data_statement_import_workspace_run_cli_v1 <- function(project_root,command,payload) {
  python<-Sys.which("python3");cli<-file.path(project_root,"scripts","statement_import_workspace.py")
  if(!nzchar(python)||!file.exists(cli)||isTRUE(file.info(cli)$isdir)||nzchar(Sys.readlink(cli)))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  encoded<-as.character(jsonlite::toJSON(payload,auto_unbox=TRUE,null="null",na="null",digits=NA,pretty=FALSE))
  if(nchar(encoded,type="bytes")>32000000L)data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  temporary<-tempfile("portelyra-statement-workspace-r-")
  if(!dir.create(temporary,mode="0700"))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  on.exit(unlink(temporary,recursive=TRUE,force=TRUE),add=TRUE)
  stdout_path<-file.path(temporary,"stdout.json");stderr_path<-file.path(temporary,"stderr.txt")
  if(!file.create(stdout_path)||!file.create(stderr_path))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  Sys.chmod(c(stdout_path,stderr_path),mode="0600",use_umask=FALSE)
  status<-tryCatch(suppressWarnings(system2(python,c("-B","-E","-s",shQuote(cli),shQuote(command)),stdout=stdout_path,stderr=stderr_path,input=encoded,wait=TRUE)),error=function(error)NA_integer_)
  stdout<-.data_statement_import_workspace_read_raw_v1(stdout_path);stderr<-.data_statement_import_workspace_read_raw_v1(stderr_path)
  if(length(stderr)!=0L||length(stdout)<2L||length(stdout)>32000000L||stdout[[length(stdout)]]!=as.raw(10)||any(stdout[-length(stdout)]==as.raw(10))||any(stdout==as.raw(0))||any(stdout==as.raw(13)))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  if(length(status)!=1L||is.na(status))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  parsed<-tryCatch(jsonlite::fromJSON(rawToChar(stdout[-length(stdout)]),simplifyVector=FALSE),error=function(error)NULL)
  if(is.null(parsed)||!is.list(parsed)||is.null(names(parsed)))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  if(as.integer(status)!=0L) {
    if(.data_statement_import_workspace_exact_names_v1(parsed,c("status","code"))&&identical(parsed$status,"blocked")&&.data_statement_import_workspace_text_v1(parsed$code))data_statement_import_workspace_abort_v1(parsed$code)
    data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  }
  if(!.data_statement_import_workspace_exact_names_v1(parsed,c("status","result"))||!identical(parsed$status,"complete")||!is.list(parsed$result))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  parsed$result
}

new_data_statement_import_workspace_v1 <- function(project_root,context,command_runner=NULL) {
  root<-normalizePath(project_root,mustWork=TRUE)
  if(!is.list(context)||!all(c("tenant_id","user_id","data_space_id")%in%names(context)))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  runner<-if(is.null(command_runner))function(command,payload).data_statement_import_workspace_run_cli_v1(root,command,payload)else command_runner
  if(!is.function(runner))data_statement_import_workspace_abort_v1("data_statement_import_workspace_boundary_failed")
  state<-new.env(parent=emptyenv());state$review<-NULL
  review_synthetic<-function(scenario) {
    if(!.data_statement_import_workspace_text_v1(scenario)||!scenario%in%c("basis_missing","manual_fiat_total","manual_unit_price"))data_statement_import_workspace_abort_v1("data_statement_import_workspace_input_invalid")
    result<-validate_data_statement_import_workspace_v1(runner("review-synthetic",list(scenario=scenario)),scenario)
    state$review<-result;result
  }
  list(review_synthetic=review_synthetic,state=function()list(review=state$review))
}

data_statement_import_workspace_column_table_v1 <- function(review) {
  review<-validate_data_statement_import_workspace_v1(review)
  data.frame(
    Quellspalte=vapply(review$column_mappings,`[[`,character(1),"source_column"),
    Explizite_Rolle=vapply(review$column_mappings,`[[`,character(1),"role"),
    Disposition=vapply(review$column_mappings,`[[`,character(1),"disposition"),
    Pflicht=vapply(review$column_mappings,function(item)if(isTRUE(item$required))"ja"else"nein",character(1)),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_workspace_route_table_v1 <- function(review) {
  review<-validate_data_statement_import_workspace_v1(review)
  data.frame(
    Typ=vapply(review$route_rules,`[[`,character(1),"source_type"),
    Subtyp=vapply(review$route_rules,`[[`,character(1),"source_subtype"),
    Assetklasse=vapply(review$route_rules,`[[`,character(1),"source_asset_class"),
    Route=vapply(review$route_rules,`[[`,character(1),"route"),
    Domain=vapply(review$route_rules,`[[`,character(1),"domain"),
    Status=vapply(review$route_rules,`[[`,character(1),"route_status"),
    Adapter=vapply(review$route_rules,function(item)if(is.null(item$adapter_id))"—"else item$adapter_id,character(1)),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_workspace_catalog_table_v1 <- function(review) {
  review<-validate_data_statement_import_workspace_v1(review)
  catalog<-review$catalog_review
  rows<-list(list(Art="Portfolio",Quelle="explizite Auswahl",Ziel=catalog$portfolio_selection$target_label,Status=catalog$portfolio_selection$mapping_status))
  rows<-c(rows,lapply(catalog$account_mappings,function(item)list(Art="Konto",Quelle=item$source_account_scope,Ziel=item$target_label,Status=item$mapping_status)))
  rows<-c(rows,lapply(catalog$asset_mappings,function(item)list(Art="Asset",Quelle=item$source_asset_key,Ziel=if(is.null(item$target_label))"—"else item$target_label,Status=item$mapping_status)))
  data.frame(
    Art=vapply(rows,`[[`,character(1),"Art"),Quelle=vapply(rows,`[[`,character(1),"Quelle"),
    Ziel=vapply(rows,`[[`,character(1),"Ziel"),Status=vapply(rows,`[[`,character(1),"Status"),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_workspace_row_table_v1 <- function(review) {
  review<-validate_data_statement_import_workspace_v1(review)
  values<-function(row)if(!length(row$candidate_values))""else paste(vapply(row$candidate_values,function(item)paste0(item$field,"=",item$value),character(1)),collapse=" · ")
  data.frame(
    Zeile=vapply(review$rows,function(row)as.integer(row$source_row_ordinal),integer(1)),
    Synthetischer_Zeilenschluessel=vapply(review$rows,`[[`,character(1),"source_row_key"),
    Route=vapply(review$rows,function(row)if(is.null(row$mapped_route))"—"else row$mapped_route,character(1)),
    Mapping=vapply(review$rows,`[[`,character(1),"mapping_status"),
    Bewertung=vapply(review$rows,`[[`,character(1),"valuation_status"),
    Reconciliation=vapply(review$rows,`[[`,character(1),"reconciliation_disposition"),
    Treffer=vapply(review$rows,function(row)as.integer(row$existing_match_count),integer(1)),
    Handoff=vapply(review$rows,`[[`,character(1),"handoff_eligibility"),
    Grund=vapply(review$rows,`[[`,character(1),"reason_code"),
    Candidate_Werte=vapply(review$rows,values,character(1)),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_workspace_count_table_v1 <- function(review) {
  review<-validate_data_statement_import_workspace_v1(review)
  data.frame(
    Disposition=vapply(review$reconciliation_summary$disposition_counts,`[[`,character(1),"disposition"),
    Anzahl=vapply(review$reconciliation_summary$disposition_counts,function(item)as.integer(item$count),integer(1)),
    stringsAsFactors=FALSE,check.names=FALSE
  )
}

data_statement_import_workspace_status_v1 <- function(review=NULL,error_code=NULL) {
  if(!is.null(error_code))return(list(tone="blocked",title="Synthetische Import-Arbeitsfläche blockiert",copy=error_code))
  if(is.null(review))return(list(tone="neutral",title="Synthetisches Kraken-Profil noch nicht geprüft",copy="Nur erfundene, hash-gebundene Zeilen; keine private Datei wird gelesen."))
  summary<-review$reconciliation_summary
  list(
    tone="success",title="Synthetische Zuordnung und Abstimmung vollständig",
    copy=sprintf("%d erfundene Zeilen · 0 stillschweigend verworfen · %d nicht vertrauenswürdige Vorschläge fachlich bereit · keine Datenwirkung.",summary$source_row_count,summary$handoff_ready_count)
  )
}
