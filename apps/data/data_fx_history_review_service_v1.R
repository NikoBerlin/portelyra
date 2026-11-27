data_fx_history_review_abort_v1 <- function(code) {
  if (!is.character(code) || length(code)!=1L || !grepl('^(data|desktop)_fx_history_review_[a-z_]+$',code)) code <- 'data_fx_history_review_boundary_failed'
  stop(structure(list(message=code,call=NULL,code=code),class=c('spot_data_fx_history_review_error_v1','error','condition')))
}
new_data_fx_history_review_service_v1 <- function(project_root,context,cli_runner=NULL) {
  python<-Sys.which('python3');cli<-file.path(normalizePath(project_root),'scripts','desktop_fx_history_review.py')
  space<-runtime_data_space_path(context);ctx<-list(tenant_id=context$tenant_id,user_id=context$user_id,data_space_id=context$data_space_id,actor_id='market_worker',role='market_worker')
  fetch<-NULL;review<-NULL;inspection<-NULL
  invalidate<-function(){fetch<<-NULL;review<<-NULL;inspection<<-NULL;invisible(NULL)}
  run<-function(cmd,p) {
    p$context<-ctx;p$data_space_path<-space
    if(is.function(cli_runner)) x<-cli_runner(cmd,p) else {
      o<-suppressWarnings(system2(python,c('-B','-E','-s',shQuote(cli),cmd),stdout=TRUE,stderr=TRUE,input=as.character(jsonlite::toJSON(p,auto_unbox=TRUE,null='null',digits=NA))))
      s<-attr(o,'status');if(is.null(s))s<-0L
      x<-tryCatch(jsonlite::fromJSON(tail(o,1),simplifyVector=FALSE),error=function(e)NULL)
      if(s!=0L || is.null(x))data_fx_history_review_abort_v1(if(is.null(x$code))'data_fx_history_review_boundary_failed'else x$code)
    }
    if(!is.list(x)||!identical(x$status,'completed'))data_fx_history_review_abort_v1(if(is.null(x$code))'data_fx_history_review_boundary_failed'else x$code)
    x
  }
  plan<-function(source,target,start,end){invalidate();run('plan',list(source_currency=source,target_currency=target,start_date=start,end_date=end))$result}
  preview<-function(source,target,start,end,now){invalidate();x<-run('preview',list(source_currency=source,target_currency=target,start_date=start,end_date=end,created_at_utc=now));x$public$preview_ref<-x$trusted$preview_fingerprint;fetch<<-x;x$public}
  stage<-function(public,confirmed) {
    if(!isTRUE(confirmed)||is.null(fetch)||!identical(public,fetch$public))data_fx_history_review_abort_v1('data_fx_history_review_confirmation_required')
    x<-fetch;fetch<<-NULL;review<<-NULL # consumed before dispatch, including uncertain failures
    native<-x$public;native$preview_ref<-NULL
    y<-run('stage',list(trusted=x$trusted,public=native,confirmed=TRUE));y$public$review_ref<-y$trusted$staging_fingerprint;review<<-y;y$public
  }
  publish<-function(public,confirmed,now) {
    if(!isTRUE(confirmed)||is.null(review)||!identical(public,review$public))data_fx_history_review_abort_v1('data_fx_history_review_confirmation_required')
    x<-review;review<<-NULL
    native<-x$public;native$review_ref<-NULL
    run('publish',list(trusted=x$trusted,public=native,confirmed=TRUE,completed_at_utc=now))$result
  }
  inspect<-function(){invalidate();x<-run('inspect',list());inspection<<-x;x$public}
  recover<-function(ref,source,target,start,end) {
    if(is.null(inspection)||!any(vapply(inspection$public$rows,function(r)identical(r$attempt_ref,ref)&&identical(r$state,'staged'),logical(1L))))data_fx_history_review_abort_v1('data_fx_history_review_confirmation_required')
    invalidate();x<-run('recover',list(attempt_ref=ref,source_currency=source,target_currency=target,start_date=start,end_date=end))
    if(!identical(x$public$source_currency,source)||!identical(x$public$target_currency,target)||!identical(x$public$start_date,start)||!identical(x$public$end_date,end))data_fx_history_review_abort_v1('data_fx_history_review_confirmation_required')
    x$public$review_ref<-x$trusted$staging_fingerprint;review<<-x;x$public
  }
  acknowledge<-function(ref,confirmed) {
    if(!isTRUE(confirmed)||is.null(inspection))data_fx_history_review_abort_v1('data_fx_history_review_confirmation_required')
    x<-inspection;invalidate()
    run('review-no-result',list(trusted=x$trusted,attempt_ref=ref,confirmed=TRUE))$result
  }
  structure(list(plan=plan,preview=preview,stage=stage,publish=publish,inspect=inspect,recover=recover,acknowledge=acknowledge,invalidate=invalidate,
    automatic_provider_access=FALSE,automatic_retry=FALSE,provider_refetch_on_publish=FALSE,canonical_write=FALSE),class=c('spot_data_fx_history_review_service_v1','list'))
}
