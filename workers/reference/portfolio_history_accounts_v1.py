"""Kennwerte je Asset und Konto (rc.294) - die walletbezogene Sicht des Verlaufs.

Der FIFO-Kern rechnet je Konto (seit rc.245): Ein Verkauf verbraucht die Lose des Kontos, von dem er abgeht; ein Transfer
traegt Lose mit Anschaffungsdatum und -kosten ins Zielkonto. Dieselbe Sicht gibt es im Verlauf
der Kennwerte. Fuer jedes Asset, das an mindestens einem Tag auf mehr als einem Konto lag, entsteht je Konto dieselbe Reihe wie
je Asset: Menge und Wert je Tag aus der Tageshistorie, Einstand aus dem FIFO-Stand, Zu- und Abfluesse, Erfolgsbruecke und
Renditen je Zeitraum.

Rechnung je Konto wie je Asset (portfolio_history_performance_v1), mit einem Unterschied: Ein Transfer zwischen eigenen Konten
ist fuer das Asset kein Fluss, fuer das Konto aber schon - er verlaesst das Quellkonto zum Tageswert und kommt im Zielkonto
zum Tageswert an. Die mitgetragenen Anschaffungskosten (aus der Lot-Spur des Kerns) wandern mit; die Bruecke fuehrt den
Unterschied zwischen Tageswert und Kosten als Wertaenderung der Ab- und Zugaenge, wie bei Ein- und Auslieferungen.
Netto je Konto gibt es nicht: Die Steuer rechnet je Verkauf, die Netto-Sicht steht je Asset.

FIFO-Wallet aus mehreren Konten (#508, rc.311): Die Lose gehoeren dann der Wallet, nicht dem einzelnen Konto. Ein Einzelkonto der
Wallet behaelt Menge, Wert, Zu- und Abgaenge, Renditen sowie realisierte GuV und Ertraege; Einstand, unrealisierte GuV und Netto
hat es nicht. Dafuer steht die Wallet als eigener Eintrag daneben - mit
denselben Reihen wie ein Konto, ueber alle ihre Konten; eine Umbuchung innerhalb der Wallet ist dort weder Fluss noch Wertaenderung.
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from typing import Any, Callable, Mapping, Sequence

from migrations.reference.exact_amount_v1 import exact_amount_v1
from workers.reference.portfolio_history_performance_v1 import (
    ZERO, _Daily, _exact, _text, active_range_v1, with_bridge_v1,
)


def multi_account_assets_v1(positions: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    """Je Asset die Konten, wenn es an mindestens einem Tag auf mehr als einem Konto lag."""
    per_day: dict[tuple[str, str], set[str]] = defaultdict(set)
    accounts: dict[str, set[str]] = defaultdict(set)
    for row in positions:
        per_day[(row["asset_id"], row["day"])].add(row["account_id"])
        accounts[row["asset_id"]].add(row["account_id"])
    several = {asset for (asset, _), held in per_day.items() if len(held) > 1}
    return {asset: sorted(accounts[asset]) for asset in sorted(several)}


FIFO_WALLET_KEY_PREFIX = "fifo_wallet|"
# Teile der Bruecke, die am Einstand haengen - bei einem Einzelkonto einer FIFO-Wallet nicht verfuegbar (#508).
BASIS_BRIDGE_PARTS = ("unrealised_change", "disposal_change", "delivery_change", "fee_basis", "rest")


def wallet_groups_v1(wallets: Mapping[str, str]) -> dict[str, str]:
    """Je Konto einer FIFO-Wallet aus mehreren Konten (#508) der Schluessel der Wallet; Konten ohne Zuordnung fehlen."""
    groups: dict[str, str] = {}
    for member, main in wallets.items():
        groups[member] = groups[main] = FIFO_WALLET_KEY_PREFIX + main
    return groups


def wallet_label_v1(labels: Mapping[str, str], wallets: Mapping[str, str], main: str) -> str:
    """'FIFO-Wallet Hauptkonto mit Unterkonto, ...' - wie im Steuerreport."""
    members = sorted((labels.get(member, member) for member, root in wallets.items() if root == main), key=str.lower)
    return "FIFO-Wallet " + labels.get(main, main) + (" mit " + ", ".join(members) if members else "")


def _moved_basis(moves: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Je Transfer die mitgetragenen Anschaffungskosten (Summe der bewegten Lose; fehlt eine, fehlt die Summe)."""
    result: dict[str, Any] = {}
    for move in moves:
        total = ZERO
        for lot in move["moved_lots"]:
            basis = _exact(lot["fifo_basis"])
            if basis is None:
                total = None
                break
            total += basis
        result[move["event_ref"]] = total
    return result


def account_dailies_v1(days: Sequence[str], positions: Sequence[Mapping[str, Any]], ledger: Sequence[Mapping[str, Any]],
                       fifo: Mapping[str, Mapping[str, Any]], timeline: Mapping[str, list[tuple[str, int, dict[str, Any]]]],
                       moves: Sequence[Mapping[str, Any]], wanted: Mapping[str, Sequence[str]],
                       group: Callable[[str], str] | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    """Je (Asset, Konto) die Tagesteile (_Daily), die Menge je Tag mit Bestand und die Mengenstufen.

    Mit 'group' (#508) je (Asset, Gruppe): Ein Konto zaehlt zu seiner Gruppe (der FIFO-Wallet), Menge und Wert sind die Summe
    ihrer Konten, und eine Umbuchung innerhalb der Gruppe ist weder Fluss noch Einstandsaenderung."""
    size = len(days)
    of = group or (lambda account: account)
    related_of = {row["event_ref"]: row.get("related_account_ref") for entries in timeline.values() for _, _, row in entries}
    index_of = {day: position for position, day in enumerate(days)}
    moved = _moved_basis(moves)
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for asset, accounts in wanted.items():
        for account in accounts:
            result[(asset, account)] = {"daily": _Daily(size), "series": {"day": [], "quantity": [], "unit_value": [], "market_value": []},
                                        "inflow": [ZERO] * size, "outflow": [ZERO] * size}

    def flow(key: tuple[str, str], position: int, amount: Any) -> None:
        # Netto fuer Fluss und IZF, getrennt fuer die zeitgewichtete Rendite (Kauf und Abgang am selben Tag).
        entry = result[key]
        entry["daily"].flow[position] += amount
        if amount > 0:
            entry["inflow"][position] += amount
        else:
            entry["outflow"][position] -= amount
    unit: dict[str, dict[int, Any]] = defaultdict(dict)
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in positions:
        if row["unit_value_decimal"] is not None and row["day"] in index_of:
            unit[row["asset_id"]][index_of[row["day"]]] = exact_amount_v1(row["unit_value_decimal"])
        if (row["asset_id"], of(row["account_id"])) in result:
            grouped[(row["asset_id"], of(row["account_id"]), row["day"])].append(row)
    for (asset, account, day), rows in sorted(grouped.items()):
        entry = result[(asset, account)]
        position = index_of.get(day)
        values = [row["market_value_decimal"] for row in rows]
        missing = any(not row["valued"] or value is None for row, value in zip(rows, values))
        total = None if missing else sum((exact_amount_v1(value) for value in values), start=ZERO)
        if position is not None:
            entry["daily"].value[position] = total
        series = entry["series"]
        series["day"].append(day)
        series["quantity"].append(_text(sum((exact_amount_v1(row["quantity_decimal"]) for row in rows), start=ZERO)))
        series["unit_value"].append(next((row["unit_value_decimal"] for row in rows if row["unit_value_decimal"] is not None), None))
        series["market_value"].append(None if total is None else _text(total))

    # Lag ein Konto zwischendurch leer, traegt seine Reihe an den Raendern der Luecke je einen Tag mit Menge und Wert 0 (ohne
    # Kurs): Die Anzeige faellt dort auf 0, statt ueber die Luecke zu verbinden. Seit rc.369 (#526) auch nach dem letzten
    # Abgang: Endet die Reihe vor dem letzten Tag des Verlaufs, folgt der Abgangstag mit Menge und Wert 0.
    for entry in result.values():
        series = entry["series"]
        if series["day"] and series["day"][-1] in index_of and index_of[series["day"][-1]] + 1 < len(days):
            for name, value in (("day", days[index_of[series["day"][-1]] + 1]), ("quantity", "0"), ("unit_value", None), ("market_value", "0")):
                series[name].append(value)
        if len(series["day"]) < 2:
            continue
        rows = list(zip(series["day"], series["quantity"], series["unit_value"], series["market_value"]))
        filled = [rows[0]]
        for before, after in zip(rows, rows[1:]):
            gap_start, gap_end = index_of[before[0]] + 1, index_of[after[0]] - 1
            if gap_start <= gap_end:
                filled.append((days[gap_start], "0", None, "0"))
                if gap_end > gap_start:
                    filled.append((days[gap_end], "0", None, "0"))
            filled.append(after)
        for name, position in (("day", 0), ("quantity", 1), ("unit_value", 2), ("market_value", 3)):
            series[name] = [row[position] for row in filled]

    def price_at(asset: str, position: int) -> Any:
        known = unit.get(asset, {})
        for back in range(position, max(-1, position - 10), -1):
            if back in known:
                return known[back]
        return None

    # Einstand je Konto: Summe der Aenderungen bis zum Tag - Zugang, Verbrauch und die Kosten, die Transfers mitnehmen.
    changes: dict[tuple[str, str], list[tuple[str, Any]]] = defaultdict(list)
    quantity_steps: dict[tuple[str, str], list[tuple[str, int, Any]]] = defaultdict(list)
    for asset, entries in timeline.items():
        held: dict[str, Any] = {}
        for day, sequence, row in entries:
            event = fifo.get(row["event_ref"]) or {}
            source = (asset, of(row["account_ref"]))
            target = (asset, of(row["related_account_ref"])) if row.get("related_account_ref") else None
            kind = event.get("type")
            if group is None:
                if source in result:
                    quantity_steps[source].append((day, int(sequence), row["custody_quantity_after_decimal"]))
                if target in result:
                    quantity_steps[target].append((day, int(sequence), row["destination_custody_quantity_after_decimal"]))
            else:
                # Die Menge einer Gruppe ist die Summe ihrer Konten nach jedem Vorgang.
                if row["custody_quantity_after_decimal"] is not None:
                    held[row["account_ref"]] = exact_amount_v1(row["custody_quantity_after_decimal"])
                if target is not None and row["destination_custody_quantity_after_decimal"] is not None:
                    held[row["related_account_ref"]] = exact_amount_v1(row["destination_custody_quantity_after_decimal"])
                for key in {source, target} - {None}:
                    if key in result:
                        total = _text(sum((value for account, value in held.items() if of(account) == key[1]), start=ZERO))
                        # Eine Umbuchung innerhalb der Gruppe aendert die Menge nicht: keine eigene Stufe.
                        if not quantity_steps[key] or quantity_steps[key][-1][2] != total:
                            quantity_steps[key].append((day, int(sequence), total))
            if target == source:
                # Umbuchung innerhalb einer Gruppe (#508): kein Los bewegt, kein Einstand veraendert.
                continue
            if kind in ("buy", "stock_dividend", "reward", "deposit"):
                if source in result:
                    changes[source].append((day, event.get("basis_added") or ZERO))
            elif kind in ("sell", "withdrawal"):
                if source in result:
                    changes[source].append((day, -(event.get("basis_consumed") or ZERO)))
            elif kind == "transfer":
                carried = moved.get(row["event_ref"]) or ZERO
                if source in result:
                    changes[source].append((day, -carried - (event.get("basis_consumed") or ZERO)))
                if target in result:
                    changes[target].append((day, carried))
    for key, entry in result.items():
        steps = sorted(changes.get(key, []), key=lambda item: item[0])
        step_days = [day for day, _ in steps]
        cumulative, running = [], ZERO
        for _, delta in steps:
            running += delta
            cumulative.append(running)
        for position, day in enumerate(days):
            hit = bisect_right(step_days, day) - 1
            entry["daily"].basis[position] = cumulative[hit] if hit >= 0 else ZERO
        entry["quantity_steps"] = sorted(quantity_steps.get(key, []), key=lambda item: (item[0], item[1]))
        entry["basis_steps"] = [(day, value) for day, value in zip(step_days, cumulative)]
    # Fluesse und Bruecke je Konto - wie je Asset, dazu Transfers zum Tageswert.
    for row in ledger:
        kind, day, asset = row["event_type"], row["local_date"], row["asset_id"]
        if not day or row["basis_currency"] != "EUR" or day not in index_of:
            continue
        position = index_of[day]
        event = fifo.get(row["event_ref"]) or {}
        source = (asset, of(row["account_id"]))
        if kind == "transfer":
            related = related_of.get(row["event_ref"])
            if related is not None and of(related) == source[1]:
                # Innerhalb einer Gruppe (#508) ist eine Umbuchung kein Fluss.
                continue
            move = next((item for item in moves if item["event_ref"] == row["event_ref"]), None)
            # Das Zielkonto wie gebucht; die Lot-Spur nennt seit #508 die Wallet.
            target = (asset, of(related)) if related is not None else (asset, move["destination_account_ref"]) if move is not None else None
            price = price_at(asset, position)
            carried = moved.get(row["event_ref"])
            if price is None or row["quantity_decimal"] is None:
                continue
            value = exact_amount_v1(row["quantity_decimal"]) * price
            if source in result:
                daily = result[source]["daily"]
                flow(source, position, -value)
                daily.parts["disposal_change"][position] += value - (carried or ZERO)
                if event.get("basis_consumed"):
                    daily.parts["fee_basis"][position] += event["basis_consumed"]
            if target in result:
                daily = result[target]["daily"]
                flow(target, position, value)
                daily.parts["delivery_change"][position] += value - (carried or ZERO)
            continue
        if source not in result:
            continue
        daily = result[source]["daily"]
        if kind == "buy" and row["gross_economic_amount_decimal"] is not None:
            flow(source, position, exact_amount_v1(row["gross_economic_amount_decimal"]) + exact_amount_v1(row["monetary_fee_decimal"] or "0"))
        elif kind == "sell" and row["net_trade_proceeds_decimal"] is not None:
            flow(source, position, -exact_amount_v1(row["net_trade_proceeds_decimal"]))
            if event.get("realized") is not None:
                daily.parts["realized"][position] += event["realized"]
        elif kind == "dividend":
            value = row.get("gross_income_decimal") if row.get("gross_income_decimal") is not None else row.get("gross_amount_decimal")
            if value is not None:
                amount = exact_amount_v1(value)
                flow(source, position, -amount)
                daily.dividends[position] += amount
                daily.parts["income"][position] += amount
        elif kind == "reward":
            if event.get("basis_added") is not None:
                daily.parts["income"][position] += event["basis_added"]
        elif kind in ("deposit", "withdrawal"):
            price = price_at(asset, position if kind == "deposit" else max(0, position - 1)) or price_at(asset, position)
            if price is None or row["quantity_decimal"] is None:
                continue
            value = exact_amount_v1(row["quantity_decimal"]) * price
            if kind == "deposit":
                flow(source, position, value)
                daily.parts["delivery_change"][position] += value - (event.get("basis_added") or ZERO)
            else:
                flow(source, position, -value)
                daily.parts["disposal_change"][position] += value - (event.get("basis_consumed") or ZERO)
    for entry in result.values():
        daily = entry["daily"]
        previous, cumulative = ZERO, ZERO
        for position in range(size):
            value = daily.value[position]
            if value is not None:
                unrealised = value - daily.basis[position]
                daily.parts["unrealised_change"][position] = unrealised - previous
                previous = unrealised
            if daily.parts["realized"][position]:
                cumulative += daily.parts["realized"][position]
                daily.realized_steps.append({"day": days[position], "realized_cumulative": _text(cumulative)})
    return result


def account_views_v1(days: Sequence[str], positions: Sequence[Mapping[str, Any]], ledger: Sequence[Mapping[str, Any]],
                     fifo: Mapping[str, Mapping[str, Any]], timeline: Mapping[str, list[tuple[str, int, dict[str, Any]]]],
                     trace: Mapping[str, Any], events: Mapping[str, Mapping[str, Any]], income: Mapping[str, list[dict[str, Any]]],
                     returns: Callable[..., dict[str, Any]], complete: Sequence[bool]) -> dict[str, list[dict[str, Any]]]:
    """Je Asset auf mehreren Konten die Eintraege je Konto - in der Form eines Asset-Eintrags (Tage, Einstand, Zu- und Abgaenge,
    Ertraege, Kennzahlen), groesster Bestand am letzten Tag zuerst."""
    wanted = multi_account_assets_v1(positions)
    if not wanted:
        return {}
    labels = trace.get("labels", {})
    wallets = trace.get("wallets") or {}
    groups = wallet_groups_v1(wallets)
    dailies = account_dailies_v1(days, positions, ledger, fifo, timeline, trace.get("moves", []), wanted)
    # Je FIFO-Wallet aus mehreren Konten (#508) ein eigener Eintrag, wenn mindestens zwei ihrer Konten das Asset hielten.
    wallet_wanted: dict[str, list[str]] = {}
    for asset, accounts in wanted.items():
        held = defaultdict(int)
        for account in accounts:
            if account in groups:
                held[groups[account]] += 1
        if any(count > 1 for count in held.values()):
            wallet_wanted[asset] = sorted(key for key, count in held.items() if count > 1)
    if wallet_wanted:
        dailies.update(account_dailies_v1(days, positions, ledger, fifo, timeline, trace.get("moves", []), wallet_wanted,
                                          group=lambda account: groups.get(account, account)))
    members_of: dict[str, set[str]] = defaultdict(set)
    for account, key in groups.items():
        members_of[key].add(account)
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (asset, account), entry in dailies.items():
        daily = entry["daily"]
        is_wallet = account.startswith(FIFO_WALLET_KEY_PREFIX)
        main = account[len(FIFO_WALLET_KEY_PREFIX):] if is_wallet else None
        label = (wallet_label_v1(labels, wallets, main) if is_wallet else labels.get(account, account))[:240]
        accounts_here = members_of[account] if is_wallet else {account}
        values = [None if value is None else _text(value) for value in daily.value]
        flows = [None] + [_text(value) for value in daily.flow[1:]]
        active = active_range_v1(daily.value, daily.flow)
        try:
            periods = [] if active is None else returns(list(days), values, flows, list(complete), spans=False, active=active,
                                                        split=list(zip(entry["inflow"], entry["outflow"])))["periods"]
        except (ZeroDivisionError, OverflowError, ValueError):
            # Laesst sich ein Konto nicht rechnen, bleiben seine Reihen; Kennzahlen je Zeitraum fehlen dann sichtbar.
            periods = []
        quantity_by_day: dict[str, Any] = {}
        for day, _, text in entry["quantity_steps"]:
            quantity_by_day[day] = exact_amount_v1(text) if text is not None else quantity_by_day.get(day, ZERO)
        basis_by_day = dict(entry["basis_steps"])
        steps, trades, previous = [], [], ZERO
        # Nur wo mindestens zwei Konten der Wallet das Asset hielten, rechnet das Konto in der Wallet; hielt es nur dieses Konto,
        # sind seine Lose die der Wallet, und es behaelt Einstand und Netto.
        member = not is_wallet and account in groups and groups[account] in wallet_wanted.get(asset, [])
        for day in sorted(set(quantity_by_day) | set(basis_by_day)):
            quantity = quantity_by_day.get(day, previous)
            hit = bisect_right([step[0] for step in entry["basis_steps"]], day) - 1
            steps.append({"day": day, "quantity": _text(quantity), "cost_basis": _text(entry["basis_steps"][hit][1]) if hit >= 0 else "0"})
            change = quantity - previous
            if change != 0:
                trades.append({"day": day, "kind": "other_in" if change > 0 else "other_out", "quantity_change": _text(change), "events": []})
            previous = quantity
        # Die Buchungen eines Tages auf diesem Konto (Quelle oder Ziel) - fuer den Klick auf einen Punkt.
        by_day: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for day, _, row in timeline.get(asset, []):
            if accounts_here & {row["account_ref"], row.get("related_account_ref")} and row["event_ref"] in events:
                by_day[day].append(row)
        # Tage mit Split (#451) auf diesem Konto: ohne Buchung dieses Tages ist die Aenderung der Split selbst.
        split_days = {day for day, _, row in timeline.get(asset, []) if "split" in row and row["account_ref"] in accounts_here}
        for trade in trades:
            rows = by_day.get(trade["day"], [])
            kinds = {(fifo.get(row["event_ref"]) or {}).get("type") for row in rows}
            positive = trade["quantity_change"][0] != "-"
            trade["kind"] = next((candidate for candidate in ("buy", "sell", "reward", "stock_dividend", "deposit", "withdrawal")
                                  if candidate in kinds and positive == (candidate not in ("sell", "withdrawal"))),
                                 ("transfer_in" if positive else "transfer_out") if "transfer" in kinds else trade["kind"])
            if not rows and trade["day"] in split_days:
                trade["kind"] = "split"
            trade["events"] = [events[row["event_ref"]] for row in rows]
        account_labels = sorted((labels.get(item, item) for item in accounts_here), key=str.lower)
        periods = with_bridge_v1(periods, list(days), daily.parts)
        if member:
            # Einzelkonto einer FIFO-Wallet (#508): Einstand und alles, was daran haengt, rechnet in der Wallet.
            steps = []
            for row in periods:
                row["bridge"].update({name: None for name in BASIS_BRIDGE_PARTS})
        extra = {}
        if is_wallet or member:
            wallet_main = main if is_wallet else groups[account][len(FIFO_WALLET_KEY_PREFIX):]
            extra["fifo_wallet"] = {"role": "wallet" if is_wallet else "member", "wallet_label": wallet_label_v1(labels, wallets, wallet_main),
                                    "accounts": sorted((labels.get(item, item) for item in members_of[groups[wallet_main]]), key=str.lower)}
        result[asset].append({
            "label": label, "days": entry["series"], "basis": steps, "trades": trades,
            "income": [row for row in income.get(asset, []) if row.get("account") in account_labels],
            "performance": {"periods": periods, "realized_steps": daily.realized_steps}, **extra,
            "_last_quantity": exact_amount_v1(entry["series"]["quantity"][-1]) if entry["series"]["quantity"] else ZERO,
            # Fuer Netto je Konto (#499) in der Veroeffentlichung; vor dem Schreiben entfernt. Ein Einzelkonto einer FIFO-Wallet
            # bekommt kein Netto (#508): Seine Lose gehoeren der Wallet.
            "_key": (asset, account), "_daily": daily, "_net": not member,
        })
    for rows in result.values():
        rows.sort(key=lambda row: (-row["_last_quantity"], row["label"]))
        for row in rows:
            row.pop("_last_quantity")
    return dict(result)


__all__ = ["BASIS_BRIDGE_PARTS", "FIFO_WALLET_KEY_PREFIX", "account_dailies_v1", "account_views_v1", "multi_account_assets_v1", "wallet_groups_v1",
           "wallet_label_v1"]
