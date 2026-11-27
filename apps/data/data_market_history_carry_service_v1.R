# Session-local boundary: liest den eigenen Kursbestand und schreibt ihn unter
# eine zweite Listing-Freigabe. Kein Anbieterzugriff, kein Netz.
data_market_history_carry_abort_v1<-function(code){if(!is.character(code)||length(code)!=1L||!grepl("^(data|desktop)_market_history_carry_[a-z_]+$",code))code<-"data_market_history_carry_boundary_failed";stop(structure(list(message=code,call=NULL,code=code),class=c("spot_data_market_history_carry_error_v1","error","condition")))}
new_data_market_history_carry_service_v1<-function(project_root,context){
 if(!is.character(project_root)||length(project_root)!=1L||!dir.exists(project_root)||!isTRUE(tryCatch(runtime_context_valid(context),error=function(error)FALSE))||!identical(context$runtime_mode,"desktop_product")||!identical(context$role,"desktop_owner"))data_market_history_carry_abort_v1("data_market_history_carry_service_invalid")
 project_root<-normalizePath(project_root,winslash="/",mustWork=TRUE);python<-Sys.which("python3");cli<-file.path(project_root,"scripts","desktop_market_history_carry.py");data_space<-runtime_data_space_path(context)
 if(!nzchar(python)||!file.exists(cli)||!dir.exists(data_space)||nzchar(Sys.readlink(cli))||nzchar(Sys.readlink(data_space)))data_market_history_carry_abort_v1("data_market_history_carry_service_invalid")
 context_payload<-list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id)
 carry<-function(source_listing_ref,target_listing_ref,start_date,end_date,carried_at_utc,dry_run=FALSE){
  payload<-list(context=context_payload,data_space_path=data_space,source_listing_ref=source_listing_ref,target_listing_ref=target_listing_ref,start_date=start_date,end_date=end_date,carried_at_utc=carried_at_utc,dry_run=isTRUE(dry_run))
  encoded<-as.character(jsonlite::toJSON(payload,auto_unbox=TRUE,null="null"));output<-tryCatch(suppressWarnings(system2(python,c("-B","-E","-s",shQuote(cli)),stdout=TRUE,stderr=TRUE,input=encoded)),error=function(error)structure(character(),status=1L));status<-attr(output,"status");if(is.null(status))status<-0L
  parsed<-tryCatch(jsonlite::fromJSON(tail(output,1L),simplifyVector=FALSE),error=function(error)NULL)
  if(is.null(parsed)||as.integer(status)!=0L||!identical(parsed$status,"completed"))data_market_history_carry_abort_v1(if(is.null(parsed$code))"data_market_history_carry_boundary_failed"else parsed$code)
  result<-parsed$result;if(!is.list(result)||!result$status%in%c("carried","preview")||isTRUE(result$provider_access)||isTRUE(result$network_access)||isTRUE(result$canonical_write))data_market_history_carry_abort_v1("data_market_history_carry_boundary_failed");result
 }
 preview<-function(source_listing_ref,target_listing_ref,start_date,end_date,carried_at_utc)carry(source_listing_ref,target_listing_ref,start_date,end_date,carried_at_utc,dry_run=TRUE)
 structure(list(contract_version="data_market_history_carry_service_v1",carry=carry,preview=preview,provider_access=FALSE,network_access=FALSE,market_history_write=TRUE,canonical_write=FALSE),class=c("spot_data_market_history_carry_service_v1","list"))
}
