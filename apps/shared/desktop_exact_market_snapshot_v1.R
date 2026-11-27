# Completed artifact presentation only. Never read valuation stores or calculate.
desktop_exact_market_ratio_v1 <- function(value) {
  if(is.null(value))return("—")
  if(!is.null(value$decimal))return(value$decimal)
  paste0(value$numerator,"/",value$denominator)
}
desktop_exact_market_policy_v1 <- function(policy) {
  if(is.null(policy)||identical(policy$mode,'strict'))return('Strikt · keine Ersatzkurse für unerklärte Quelllücken')
  paste('Letzter gültiger Kurs · höchstens',policy$max_age_days,'Kalendertage')
}
desktop_exact_market_state_v1 <- function(model) {
  v<-model$exact_market_snapshot
  if(is.null(v))return(shiny::p("Kein exakter Marktwertteil in diesem abgeschlossenen Run."))
  quality<-if(identical(v$status,'incomplete'))'unvollständig'else if(identical(v$valuation_status,'substituted'))'ersatzwertgestützt'else'vollständig im Nicht-Cash-Bewertungsumfang'
  portelyra_status_panel(paste("Exakter Nicht-Cash-Marktwert",quality,"·",v$as_of_date),
    paste("Laufstatus:",pl_run_status_label_v1(model$status),"· bekannte Teilsumme",desktop_exact_market_ratio_v1(v$known_market_value_eur),
      "EUR · vollständiger Nicht-Cash-Marktwert",desktop_exact_market_ratio_v1(v$total_market_value_eur),
      "EUR · fehlende Positionen",v$unavailable_position_count,
      '· Bewertungsregel:',desktop_exact_market_policy_v1(v$valuation_policy),
      '· ersatzwertgestützte Positionen:',if(is.null(v$substituted_position_count))0L else v$substituted_position_count,
      "· Quellen bei Veröffentlichung geprüft, keine Live-Frischeprüfung. Ohne Cash, Steuern und Netto-Liquidation; kein Portfolioabschluss."),
    tone=if(identical(v$status,"complete")&&!identical(v$valuation_status,'substituted')&&identical(model$freshness_status,"current"))"neutral"else"warning")
}
desktop_exact_market_assets_v1 <- function(model) {
  rows<-model$exact_market_snapshot$selected_assets
  if(!length(rows))return(data.frame())
  do.call(rbind,lapply(rows,function(v)data.frame(Auswahl=v$ordinal,Asset=v$asset_label,Disposition=v$disposition,check.names=FALSE)))
}
desktop_exact_market_positions_v1 <- function(model) {
  rows<-model$exact_market_snapshot$positions
  if(!length(rows))return(data.frame())
  do.call(rbind,lapply(rows,function(v)data.frame(Position=v$ordinal,Verwahrung=v$account_ordinal,Asset=v$asset_label,
    Basiswährung=v$basis_currency,Status=v$status,Menge=desktop_exact_market_ratio_v1(v$quantity),
    EUR_je_Einheit=desktop_exact_market_ratio_v1(v$unit_value_eur),EUR_Marktwert=desktop_exact_market_ratio_v1(v$market_value_eur),
    Preisbasis=if(is.null(v$price_basis))"—"else v$price_basis,Preisdatum=if(is.null(v$price_source_date))"—"else v$price_source_date,
    Preisalter_Kalendertage=if(is.null(v$price_age_days))'—'else as.character(v$price_age_days),
    FX_Basis=if(is.null(v$fx_basis))"—"else v$fx_basis,FX_Datum=if(is.null(v$fx_source_date))"—"else v$fx_source_date,
    FX_Alter_Kalendertage=if(is.null(v$fx_age_days))'—'else as.character(v$fx_age_days),
    Ersatzbewertung=if(isTRUE(v$substitution_used))'ja'else'nein',
    check.names=FALSE,stringsAsFactors=FALSE)))
}
