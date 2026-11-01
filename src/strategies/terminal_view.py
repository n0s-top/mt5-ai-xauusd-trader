"""Terminal presentation for manual analysis; no data fetching or trading."""

from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

COLORS = {
    "BUY": "bold green",
    "SELL": "bold red",
    "WAIT": "bold yellow",
    "REVIEW": "bold cyan",
    "BLOCKED": "bold red",
}


def local_time(value):
    try:
        return (
            datetime.fromisoformat(value)
            .astimezone(timezone(timedelta(hours=7)))
            .strftime("%d/%m %H:%M:%S")
            + " (UTC+7)"
        )
    except (ValueError, TypeError):
        return str(value)


def render_plan(plan, console=None):
    console = console or Console()
    if plan.get("strategy_id") == "donchian_55_20_d1_demo_v1":
        render_donchian(plan, console)
        return
    status = plan["status"]
    heading = Text(f"{plan['symbol']}  |  {status}", style=COLORS.get(status, "white"))
    console.print(Panel(heading, border_style=COLORS.get(status, "white")))
    if plan.get("strategy_id"):
        console.print(
            Text(
                f"Chien luoc: {plan['strategy_id']} | Setup: {plan.get('setup_type', 'WAIT')}",
                style="cyan",
            )
        )
    if plan.get("experimental"):
        console.print(
            Text(
                "BAN THU NGHIEM: chua chung minh vuot chien luoc cu ngoai mau.", style="bold yellow"
            )
        )
    if "bid" in plan:
        quote = Table.grid(padding=(0, 3))
        quote.add_row(
            Text(f"BID {plan['bid']:.3f}", style="cyan"),
            Text(f"ASK {plan['ask']:.3f}", style="cyan"),
            Text(f"SPREAD {plan['ask'] - plan['bid']:.3f}", style="yellow"),
        )
        console.print(quote)
    if "equity" in plan:
        console.print(
            Text(
                f"Von: {plan['equity']:.2f} {plan['currency']} | "
                f"Tran rui ro: {plan.get('risk_percent', 0):.2f}%",
                style="dim",
            )
        )
    if plan.get("forecast"):
        forecast = plan["forecast"]
        if forecast.get("probabilities"):
            probabilities = forecast["probabilities"]
            description = " | ".join(f"{key}: {probabilities[key]:.1%}" for key in ("UP", "FLAT", "DOWN"))
            description += f"\nNguong bien dong: {forecast['movement_threshold_price']:.3f} don vi gia"
            description += "\n" + forecast["validation_status"]
            description += "\nXac suat huong gia, KHONG phai xac suat thang lenh. Chi de nghien cuu."
        else:
            description = "UNAVAILABLE: " + forecast.get("reason", "Missing forecast")
        console.print(Panel(Text(description), title="Du bao huong gia 5 phut", border_style="cyan"))
    side = plan.get("preferred_side") or plan.get("side")
    if side in ("BUY", "SELL"):
        console.print(Text(f"HUONG UU TIEN: {side}", style=COLORS[side]))
    if status != "REVIEW":
        console.print(Text(f"Ly do cho: {plan.get('reason', '')}", style="yellow"))
    if plan.get("direction_reason"):
        console.print(Text(plan["direction_reason"], style="dim"))
    if plan.get("mtf_warning"):
        console.print(
            Panel(Text(plan["mtf_warning"], style="bold yellow"), title="CANH BAO DA KHUNG")
        )

    candidates = [plan] if status == "REVIEW" else plan.get("reference_scenarios", [])
    for candidate in candidates[:2]:
        side = candidate.get("side", "WAIT")
        reference = candidate.get("status") == "REFERENCE_ONLY"
        table = Table(
            title=f"{side} | "
            + ("THAM KHAO - CHUA DU DIEU KIEN" if reference else "KICH BAN CO DIEU KIEN"),
            title_style=COLORS.get(side, "white"),
            show_header=False,
            border_style=COLORS.get(side, "white"),
            expand=True,
        )
        table.add_column("Muc", style="bold", ratio=1)
        table.add_column("Gia tri", ratio=2)
        for key, label, style in (
            ("entry", "Gia kich hoat", "bold cyan"),
            ("stop_loss", "SL - Cat lo", "bold red"),
            ("take_profit", "TP - Chot loi", "bold green"),
        ):
            if candidate.get(key) is not None:
                table.add_row(label, Text(f"{candidate[key]:.3f}", style=style))
        if candidate.get("reward_risk") is not None:
            table.add_row("Risk : Reward", f"1 : {candidate['reward_risk']:.2f}")
        if candidate.get("net_reward_risk") is not None:
            table.add_row("R:R sau phi/truot gia", f"1 : {candidate['net_reward_risk']:.2f}")
        if candidate.get("distance_to_entry") is not None:
            table.add_row(
                "Cach gia kich hoat",
                f"{candidate['distance_to_entry']:.3f} ({candidate['distance_atr']:.2f} ATR)",
            )
        volume = candidate.get("volume")
        table.add_row(
            "Lot mo phong" if reference else "Lot de xuat",
            Text(
                str(volume) if volume is not None else "N/A",
                style="bold cyan" if volume is not None else "yellow",
            ),
        )
        for key, label in (
            ("estimated_risk", "Lo uoc tinh tai SL"),
            ("estimated_margin", "Margin uoc tinh"),
            ("estimated_net_profit", "Lai rong uoc tinh tai TP"),
        ):
            if candidate.get(key) is not None:
                table.add_row(label, f"{candidate[key]:.2f} {plan.get('currency', '')}")
        console.print(table)
        if candidate.get("sizing_note"):
            console.print(Text(f"LOT: {candidate['sizing_note']}", style="yellow"))
        if reference:
            console.print(
                Text(
                    "Lot mo phong theo tran rui ro, khong phai Kelly. Chua xac nhan vao lenh.",
                    style="bold yellow",
                )
            )
        console.print(
            Text(
                "Dong lenh tai TP/SL: "
                + ("ban de dong BUY." if side == "BUY" else "mua de dong SELL."),
                style="dim",
            )
        )

    details = plan.get("entry_details")
    if details and plan.get("status") == "REVIEW":
        explanation = [details["trigger_rule"],
                       f"High/Low nen: {details['signal_high']:.3f} / {details['signal_low']:.3f}",
                       f"Khoang Entry-SL: {details['risk_distance']:.3f} | Entry-TP: {details['reward_distance']:.3f}",
                       details["stop_rule"], details["target_rule"], details["cancel_rule"]]
        console.print(Panel(Text("\n".join(explanation)), title="Chi tiet Entry / SL / TP", border_style="cyan"))
    checks = plan.get("setup_checks", [])
    if plan.get("strategy_checks"):
        strategy_checks = Table(title="Bo loc chien luoc", expand=True)
        strategy_checks.add_column("Dieu kien")
        strategy_checks.add_column("Ket qua")
        for check in plan["strategy_checks"]:
            strategy_checks.add_row(
                Text(check["label"]),
                Text(
                    "DAT" if check["passed"] else "CHUA DAT",
                    style="green" if check["passed"] else "yellow",
                ),
            )
        console.print(strategy_checks)
    if checks:
        passed = sum(item["passed"] for item in checks)
        checklist = Table(
            title=f"Dieu kien vao lenh: {passed}/{len(checks)} (khong phai xac suat thang)",
            expand=True,
        )
        checklist.add_column("Dieu kien")
        checklist.add_column("Ket qua")
        for check in checks:
            checklist.add_row(
                Text(check["label"]),
                Text(
                    "DAT" if check["passed"] else "CHUA DAT",
                    style="green" if check["passed"] else "yellow",
                ),
            )
        console.print(checklist)
    exposure = plan.get("account_risk")
    if exposure:
        risk_text = Text(
            f"{exposure['status']} | {exposure['positions']} vi the | "
            f"{exposure['orders']} lenh cho",
            style="cyan" if exposure["status"] == "READY" else "yellow",
        )
        if "used_percent" in exposure:
            risk_text.append(
                f"\nRui ro tai SL: {exposure['stop_risk']:.2f} {plan.get('currency', '')} "
                f"({exposure['used_percent']:.2f}% von) | Tran {exposure['cap_percent']:.2f}%"
                f"\nNgan sach con lai: {exposure['available_percent']:.2f}% von"
            )
        if exposure.get("reason"):
            risk_text.append("\n" + exposure["reason"])
        console.print(Panel(risk_text, title="Rui ro toan tai khoan", border_style="cyan"))
    if plan.get("indicators"):
        indicators = Table(title="Co so phan tich", expand=True)
        indicators.add_column("Khung")
        indicators.add_column("Chi bao")
        indicators.add_column("Trang thai")
        for item in plan["indicators"]:
            indicators.add_row(
                item["timeframe"],
                Text(item["values"]),
                Text(item["state"], style=COLORS.get(item["state"], "yellow")),
            )
        console.print(indicators)
    if plan.get("higher_timeframes"):
        higher = Table(title="Boi canh H1 / H4 - khong phai tin hieu vao lenh", expand=True)
        higher.add_column("Khung")
        higher.add_column("Huong")
        higher.add_column("EMA / Vung gia 20 nen da dong")
        for label, context in plan["higher_timeframes"].items():
            state = context["state"]
            detail = context.get("reason", "")
            if state != "UNAVAILABLE":
                detail = (
                    f"EMA21 {context['ema21']:.3f} | EMA200 {context['ema200']:.3f}\n"
                    f"Day {context['range_low']:.3f} | Dinh {context['range_high']:.3f}"
                )
            higher.add_row(label, Text(state, style=COLORS.get(state, "yellow")), Text(detail))
        console.print(higher)
    if "setup_probability" in plan:
        console.print(
            Text(
                "XAC SUAT THANG CUA SETUP: CHUA KIEM CHUNG - khong gan % tu chi bao.",
                style="bold yellow",
            )
        )
    kelly = plan.get("kelly")
    if kelly:
        text = Text(
            f"KELLY {kelly['status']} | {kelly['trades']} lenh | "
            f"Rui ro {kelly['risk_percent']:.3f}%",
            style="cyan" if kelly["status"] == "READY" else "yellow",
        )
        if "win_rate" in kelly:
            text.append(
                f"\nThang lich su {kelly['win_rate']:.1%} | "
                f"Uoc tinh than trong {kelly['conservative_win_rate']:.1%} | "
                f"Loi/lo TB {kelly['payoff_ratio']:.2f}"
            )
            if "win_rate_upper" in kelly:
                text.append(
                    f"\nKhoang Wilson 95% cho ty le thang lich su: "
                    f"{kelly['conservative_win_rate']:.1%} - {kelly['win_rate_upper']:.1%}"
                    "\nThong ke lich su, khong phai xac suat setup hien tai."
                )
        if kelly.get("reason"):
            text.append("\n" + kelly["reason"])
        console.print(Panel(text, title="Quan ly von", border_style="yellow"))
    if plan.get("reference_note"):
        console.print(Text(plan["reference_note"], style="yellow"))
    if plan.get("generated_at_utc"):
        console.print(Text("Phan tich: " + local_time(plan["generated_at_utc"]), style="dim"))
    if plan.get("expires_at_utc"):
        console.print(Text("Het han: " + local_time(plan["expires_at_utc"]), style="yellow"))
    console.print(Text("Kich ban khong bao dam gia tuong lai. Bot khong tu dat lenh.", style="dim"))


def render_donchian(plan, console):
    console.print(
        Panel(
            Text(
                f"{plan['symbol']} | Donchian 55/20 D1 | DEMO | {plan['status']}", style="bold cyan"
            )
        )
    )
    console.print(Text(plan.get("reason", ""), style="yellow"))
    if plan.get("levels"):
        levels = Table(title="Kenh D1 tu cac phien da dong", show_header=False)
        for key, label in (
            ("entry_high_55", "Dinh 55"),
            ("entry_low_55", "Day 55"),
            ("exit_high_20", "Dinh thoat 20"),
            ("exit_low_20", "Day thoat 20"),
            ("atr20", "ATR20"),
        ):
            levels.add_row(label, f"{plan['levels'][key]:.3f}")
        console.print(levels)
    for candidate in plan.get("entry_scenarios", []):
        table = Table(title=f"{candidate['side']} | {candidate['status']}", show_header=False)
        for label, value in (
            ("Gia kich hoat", f"{candidate['entry']:.3f}"),
            ("SL ban dau", f"{candidate['stop_loss']:.3f}"),
            ("TP", "Khong co TP co dinh; thoat theo kenh 20 D1"),
            ("Lot", str(candidate.get("volume") or "N/A")),
        ):
            table.add_row(label, value)
        if candidate.get("estimated_risk") is not None:
            table.add_row(
                "Rui ro tai SL", f"{candidate['estimated_risk']:.2f} {plan.get('currency', '')}"
            )
        console.print(table)
        console.print(Text(candidate.get("reason", ""), style="yellow"))
    if plan.get("management"):
        item = plan["management"]
        console.print(
            Panel(
                Text(
                    f"{item['side']} | {item['action']}\nSL hien tai {item['existing_sl']:.3f} | SL de xem xet {item['suggested_sl']:.3f}\nBroker cho phep khoang cach sua SL: {item['broker_distance_allows_modify']}",
                    style="bold yellow",
                )
            )
        )
    for key in ("exit_rule", "demo_note", "cost_note"):
        if plan.get(key):
            console.print(Text(plan[key], style="yellow"))
    if plan.get("expires_at_utc"):
        console.print(
            Text("Quote/lot het han: " + local_time(plan["expires_at_utc"]), style="yellow")
        )
    console.print(
        Text(
            "Chi ho tro thu cong. Khong tu gui/sua/huy lenh. Chua xac nhan loi nhuan live.",
            style="dim",
        )
    )
