#!/usr/bin/env python3
"""
Petacomm - Linux Server Yönetim Aracı
Kullanım:
    petacomm status                    → Sistem durumu
    petacomm health                    → Sağlık skoru
    petacomm ls services               → Servisleri listele
    petacomm ls ports                  → Açık portlar
    petacomm ls backups                → Yedekleri listele
    petacomm ls processes              → Süreçleri listele
    petacomm -r "isteğin"              → AI'ya sor
    petacomm find "aranacak"           → Dosya ara
    petacomm backup now                → Hemen yedek al
    petacomm restore <isim>            → Yedeği geri yükle
    petacomm login                     → API key gir
"""

import sys
import os
import re
import getpass
from pathlib import Path

# Proje kökünü path'e ekle
sys.path.insert(0, str(Path(__file__).parent))

from core import scanner, executor, claude_api, backup
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich import box
from rich.columns import Columns
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


# ─── Renk yardımcıları ───────────────────────────────────────────────────────

def risk_color(level: str) -> str:
    return {"green": "bright_green", "yellow": "yellow", "red": "red"}.get(level, "white")

def pct_color(pct: float) -> str:
    if pct >= 90: return "red"
    if pct >= 75: return "yellow"
    return "bright_green"

def bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    color = pct_color(pct)
    bar_str = "█" * filled + "░" * (width - filled)
    return f"[{color}]{bar_str}[/] [dim]{pct:.1f}%[/]"

def status_icon(active: bool, status: str = "") -> str:
    if status == "failed": return "[red]✗[/]"
    if active: return "[bright_green]●[/]"
    return "[dim]○[/]"


# ─── Komutlar ────────────────────────────────────────────────────────────────

def cmd_status():
    """Sistem genel durumunu göster."""
    with Progress(SpinnerColumn(), TextColumn("[cyan]Sistem taranıyor..."), transient=True) as p:
        p.add_task("")
        data = scanner.full_scan()

    h = data["health"]
    score_color = {"iyi": "bright_green", "dikkat": "yellow", "kritik": "red"}.get(h["level"], "white")

    # Başlık
    console.print()
    console.print(Panel(
        f"[bold cyan]Petacomm[/] — Linux Server Yönetim Aracı\n"
        f"[dim]{data['scanned_at']}[/]",
        border_style="cyan", padding=(0, 2)
    ))

    # Sistem bilgisi + sağlık skoru yan yana
    info = Table(box=None, show_header=False, padding=(0, 2))
    info.add_column(style="dim", width=16)
    info.add_column()
    info.add_row("Hostname", f"[bold]{data['hostname']}[/]")
    info.add_row("IP", data["ip"])
    info.add_row("OS", data["os"])
    info.add_row("Kernel", data["kernel"])
    info.add_row("Uptime", data["uptime"])
    load = data.get("load", ["-", "-", "-"])
    info.add_row("Load Avg", f"{' '.join(load)}")

    score_panel = Panel(
        f"\n[{score_color} bold]{h['score']}[/][dim]/100[/]\n\n[{score_color}]{h['level'].upper()}[/]\n",
        title="Sağlık Skoru", border_style=score_color, width=20
    )

    console.print(Columns([info, score_panel]))

    # Kaynaklar
    console.print()
    console.print("[bold]Kaynaklar[/]")
    res = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    res.add_column(style="dim", width=6)
    res.add_column(width=30)
    res.add_column()
    res.add_row("CPU", bar(data["cpu"]), f"[dim]{data['cpu']:.1f}%[/]")
    ram = data["ram"]
    res.add_row("RAM", bar(ram["percent"]),
                f"[dim]{scanner.fmt_bytes(ram['used'])} / {scanner.fmt_bytes(ram['total'])}[/]")
    for disk in data["disks"][:3]:
        res.add_row(disk["mount"][:6], bar(disk["percent"]),
                    f"[dim]{scanner.fmt_bytes(disk['used'])} / {scanner.fmt_bytes(disk['total'])}[/]")
    console.print(res)

    # Uyarılar
    if h["criticals"]:
        console.print()
        for c in h["criticals"]:
            console.print(f"  [red]🔴 {c}[/]")
    if h["warnings"]:
        for w in h["warnings"]:
            console.print(f"  [yellow]🟡 {w}[/]")

    # Servisler özet
    active_svcs = [s for s in data["services"] if s["active"]]
    failed_svcs = [s for s in data["services"] if s["status"] == "failed"]
    console.print()
    console.print(
        f"[dim]Servisler:[/] "
        f"[bright_green]{len(active_svcs)} çalışıyor[/]"
        + (f"  [red]{len(failed_svcs)} hatalı[/]" if failed_svcs else "")
    )
    console.print()


def cmd_health():
    """Detaylı sağlık raporu."""
    with Progress(SpinnerColumn(), TextColumn("[cyan]Analiz ediliyor..."), transient=True) as p:
        p.add_task("")
        data = scanner.full_scan()

    h = data["health"]
    score_color = {"iyi": "bright_green", "dikkat": "yellow", "kritik": "red"}.get(h["level"], "white")

    console.print()
    console.print(Panel(
        f"[{score_color} bold]Sağlık Skoru: {h['score']}/100 — {h['level'].upper()}[/]",
        border_style=score_color
    ))

    if not h["criticals"] and not h["warnings"]:
        console.print("[bright_green]✓ Sistem sağlıklı görünüyor, sorun tespit edilmedi.[/]")
    else:
        if h["criticals"]:
            console.print("\n[bold red]Kritik Sorunlar:[/]")
            for c in h["criticals"]:
                console.print(f"  🔴 {c}")
        if h["warnings"]:
            console.print("\n[bold yellow]Uyarılar:[/]")
            for w in h["warnings"]:
                console.print(f"  🟡 {w}")

    console.print()


def cmd_ls(target: str):
    """Listele: services, ports, backups, processes."""

    if target in ("services", "servisler", "service"):
        with Progress(SpinnerColumn(), TextColumn("[cyan]Servisler taranıyor..."), transient=True) as p:
            p.add_task("")
            services = scanner.get_services()

        console.print()
        t = Table(title="Servisler", box=box.ROUNDED, border_style="cyan")
        t.add_column("Durum", width=4)
        t.add_column("Servis", style="bold")
        t.add_column("Durum", width=12)
        for s in services:
            t.add_row(
                status_icon(s["active"], s["status"]),
                s["name"],
                f"[bright_green]{s['status']}[/]" if s["active"] else
                f"[red]{s['status']}[/]" if s["status"] == "failed" else
                f"[dim]{s['status']}[/]"
            )
        console.print(t)

    elif target in ("ports", "port"):
        with Progress(SpinnerColumn(), TextColumn("[cyan]Portlar taranıyor..."), transient=True) as p:
            p.add_task("")
            ports = scanner.get_open_ports()

        console.print()
        t = Table(title="Açık Portlar", box=box.ROUNDED, border_style="cyan")
        t.add_column("Port", style="yellow", width=8)
        t.add_column("Servis")
        for p in ports:
            t.add_row(str(p["port"]), p["service"] or "—")
        console.print(t)

    elif target in ("backups", "backup", "yedek", "yedekler"):
        backups = backup.list_backups()
        console.print()
        if not backups:
            console.print("[dim]Henüz yedek yok.[/]")
            return
        t = Table(title="Yedekler", box=box.ROUNDED, border_style="cyan")
        t.add_column("#", width=4, style="dim")
        t.add_column("Ad")
        t.add_column("Tarih", style="dim")
        t.add_column("Dosya", width=7, justify="right")
        t.add_column("Boyut", width=10, justify="right")
        for i, b in enumerate(backups, 1):
            t.add_row(str(i), b["name"], b["created_at"], str(b["files"]), b["size"])
        console.print(t)

    elif target in ("processes", "process", "ps", "süreçler"):
        with Progress(SpinnerColumn(), TextColumn("[cyan]Süreçler alınıyor..."), transient=True) as p:
            p.add_task("")
            out = executor.run_command("ps aux --sort=-%cpu | head -20")

        console.print()
        console.print(Panel(out["output"], title="En Yoğun 20 Süreç", border_style="cyan"))

    elif target in ("logs", "log"):
        console.print()
        console.print("[dim]Hangi log? Örnek:[/]")
        console.print("  petacomm logs nginx")
        console.print("  petacomm logs system")

    else:
        console.print(f"[yellow]Bilinmeyen hedef: {target}[/]")
        console.print("[dim]Kullanılabilir: services, ports, backups, processes[/]")


def cmd_logs(target: str, follow: bool = False):
    """Log dosyasını göster."""
    log_map = {
        "nginx": "/var/log/nginx/error.log",
        "apache": "/var/log/apache2/error.log",
        "mysql": "/var/log/mysql/error.log",
        "system": "/var/log/syslog",
        "auth": "/var/log/auth.log",
        "kern": "/var/log/kern.log",
    }

    log_file = log_map.get(target, f"/var/log/{target}.log")

    if follow:
        console.print(f"[dim]Canlı log: {log_file} (Ctrl+C ile çık)[/]")
        os.execlp("tail", "tail", "-f", log_file)
    else:
        out = executor.run_command(f"tail -50 {log_file}")
        if out["success"]:
            console.print(Panel(out["output"], title=f"Log: {log_file}", border_style="cyan"))
        else:
            console.print(f"[red]Log okunamadı: {log_file}[/]")
            console.print(f"[dim]{out['output']}[/]")


def cmd_find(query: str):
    """Dosya ara, numaralı listele, seçili olanları sil."""
    console.print()
    with Progress(SpinnerColumn(), TextColumn(f"[cyan]'{query}' aranıyor..."), transient=True) as p:
        p.add_task("")
        results = executor.find_files(query)

    if not results:
        console.print(f"[dim]'{query}' ile eşleşen dosya bulunamadı.[/]")
        return

    # Listele
    t = Table(box=box.SIMPLE, show_header=True)
    t.add_column("#", width=4, style="dim")
    t.add_column("Tür", width=7)
    t.add_column("Yol")
    t.add_column("Boyut", width=10, justify="right", style="dim")

    for r in results:
        icon = "📁" if r["is_dir"] else "📄"
        t.add_row(str(r["num"]), icon + " " + r["type"], r["path"], r["size_fmt"])

    console.print(t)
    console.print(f"[dim]{len(results)} sonuç bulundu.[/]")
    console.print()

    # Silmek istiyor mu?
    console.print("[dim]Silmek istediklerini yaz (örn: delete 1,2,3) ya da Enter ile çık:[/]")
    choice = Prompt.ask("", default="")

    if not choice.lower().startswith("delete"):
        return

    # Seçimleri parse et
    nums_str = choice.lower().replace("delete", "").strip()
    try:
        nums = [int(n.strip()) for n in nums_str.split(",") if n.strip().isdigit()]
    except Exception:
        console.print("[red]Geçersiz format.[/]")
        return

    selected = [r for r in results if r["num"] in nums]
    if not selected:
        console.print("[dim]Hiçbir öğe seçilmedi.[/]")
        return

    # Özet göster
    console.print()
    console.print("[bold]Silinecekler:[/]")
    total_size = 0
    for item in selected:
        risk = executor.risk_check(f"rm {'-rf' if item['is_dir'] else ''} {item['path']}")
        color = risk_color(risk["level"])
        console.print(
            f"  [{color}]{'🔴' if risk['level'] == 'red' else '🟡' if risk['level'] == 'yellow' else '🟢'}[/] "
            f"{item['path']}  [dim]{item['size_fmt']}[/]"
        )
        total_size += item["size"]

    console.print(f"\n[dim]Toplam: {executor.fmt_size(total_size)}[/]")
    console.print()

    # Onay
    console.print("[bold]Emin misin?[/]")
    console.print("  [bright_green]Y[/]  → Sil")
    console.print("  [red]N[/]  → İptal")
    console.print("  [cyan]B[/]  → Yedekle sonra sil")
    console.print()

    ans = Prompt.ask("Seçim", choices=["Y", "y", "N", "n", "B", "b"], default="N")

    if ans.upper() == "N":
        console.print("[dim]İptal edildi.[/]")
        return

    backup_dir = None
    if ans.upper() == "B":
        # Yedek al
        with Progress(SpinnerColumn(), TextColumn("[cyan]Yedekleniyor..."), transient=True) as p:
            p.add_task("")
            bk = backup.create_backup([r["path"] for r in selected], label=query)
        if bk["success"]:
            console.print(f"[bright_green]✓ Yedek alındı → {bk['backup_path']}[/]")
            backup_dir = bk["backup_path"]
        else:
            console.print("[red]Yedekleme başarısız! Silme iptal edildi.[/]")
            return

    # Sil
    console.print()
    result = executor.delete_items(selected, backup_dir)

    for path in result["success"]:
        console.print(f"[bright_green]✓[/] {path}")
    for fail in result["failed"]:
        console.print(f"[red]✗[/] {fail['path']} — {fail['error']}")

    if result["success"]:
        console.print(f"\n[bright_green]✓ {len(result['success'])} öğe silindi.[/]")
        if backup_dir:
            console.print(f"[dim]Geri almak için: petacomm restore {Path(backup_dir).name}[/]")


def cmd_request(request: str, dry_run: bool = False):
    """Send a natural language request to Claude AI."""
    api_key = claude_api.get_api_key()
    if not api_key:
        console.print("[yellow]No API key found. Run: petacomm login[/]")
        
        return

    # Önce sistemi tara
    with Progress(SpinnerColumn(), TextColumn("[cyan]Sistem taranıyor..."), transient=True) as p:
        p.add_task("")
        sys_data = scanner.full_scan()

    with Progress(SpinnerColumn(), TextColumn("[cyan]Claude'a soruluyor..."), transient=True) as p:
        p.add_task("")
        result = claude_api.ask_claude(request, system_context=sys_data, api_key=api_key)

    if not result["success"]:
        console.print(f"[red]Error: {result['error']}[/]")
        return

    console.print()

    if result.get("command_ran"):
        console.print(f"[dim]▸ Ran:[/] [yellow]{result['command_ran']}[/]")
        console.print()

    console.print(Panel(
        result["response"],
        title=f"[cyan]Petacomm AI[/] [dim]— {request[:50]}[/]",
        border_style="cyan",
        padding=(1, 2),
    ))

    if dry_run:
        console.print("[dim][DRY RUN — Nothing was executed][/]")

    console.print()


def cmd_backup(action: str, target: str = ""):
    if action in ("now", "al", "create"):
        paths = [target] if target else [str(Path.home())]
        with Progress(SpinnerColumn(), TextColumn("[cyan]Yedekleniyor..."), transient=True) as p:
            p.add_task("")
            result = backup.create_backup(paths, label=target or "manual")

        if result["success"]:
            console.print(f"[bright_green]✓ Yedek alındı → {result['backup_path']}[/]")
        else:
            console.print("[red]Yedekleme başarısız.[/]")
    else:
        console.print(f"[yellow]Bilinmeyen backup komutu: {action}[/]")


def cmd_restore(name: str):
    backups = backup.list_backups()
    names = [b["name"] for b in backups]

    if name not in names:
        console.print(f"[red]Yedek bulunamadı: {name}[/]")
        console.print("[dim]Mevcut yedekler: petacomm ls backups[/]")
        return

    if not Confirm.ask(f"'{name}' yedeği geri yüklenecek. Emin misin?"):
        return

    with Progress(SpinnerColumn(), TextColumn("[cyan]Geri yükleniyor..."), transient=True) as p:
        p.add_task("")
        result = backup.restore_backup(name)

    if result["success"]:
        for r in result["restored"]:
            console.print(f"[bright_green]✓[/] {r}")
        console.print(f"\n[bright_green]✓ Geri yükleme tamamlandı.[/]")
    else:
        console.print(f"[red]Hata: {result.get('error', 'Bilinmeyen hata')}[/]")


def cmd_login():
    """API key kaydet."""
    console.print()
    console.print(Panel(
        "[bold]Claude API Key Girişi[/]\n\n"
        "API key almak için:\n"
        "  [cyan]https://console.anthropic.com[/]\n\n"
        "[dim]Key güvenli şekilde ~/.petacomm/config.json dosyasına kaydedilir.[/]",
        border_style="cyan"
    ))
    console.print()

    key = getpass.getpass("API Key (sk-ant-...): ")
    if not key.startswith("sk-"):
        console.print("[yellow]Uyarı: Geçersiz format gibi görünüyor. Yine de kaydedildi.[/]")

    claude_api.set_api_key(key.strip())
    console.print("[bright_green]✓ API key kaydedildi.[/]")
    console.print()


def cmd_help():
    console.print()
    console.print(Panel(
        "[bold cyan]Petacomm[/] — Linux Server Yönetim Aracı\n\n"
        "[bold]Komutlar:[/]\n"
        "  [yellow]petacomm status[/]              Sistem durumu\n"
        "  [yellow]petacomm health[/]              Sağlık skoru\n"
        "  [yellow]petacomm ls services[/]         Servisleri listele\n"
        "  [yellow]petacomm ls ports[/]            Açık portları listele\n"
        "  [yellow]petacomm ls backups[/]          Yedekleri listele\n"
        "  [yellow]petacomm ls processes[/]        Süreçleri listele\n"
        "  [yellow]petacomm logs nginx[/]          Nginx loglarını göster\n"
        "  [yellow]petacomm logs nginx --follow[/] Canlı log takibi\n"
        "  [yellow]petacomm find \"kelime\"[/]       Dosya ara ve sil\n"
        "  [yellow]petacomm backup now[/]          Hemen yedek al\n"
        "  [yellow]petacomm restore <isim>[/]      Yedeği geri yükle\n"
        "  [yellow]petacomm -r \"isteğin\"[/]        AI'ya sor (Claude)\n"
        "  [yellow]petacomm --dry-run -r \"..\"[/]   Simüle et, çalıştırma\n"
        "  [yellow]petacomm login[/]               API key gir\n"
        "  [yellow]petacomm help[/]                Bu yardım\n",
        border_style="cyan", padding=(1, 2)
    ))


# ─── Ana giriş noktası ────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]

    if not args:
        cmd_help()
        return

    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    cmd = args[0]

    # petacomm -r "istek"
    if cmd == "-r":
        request = " ".join(args[1:])
        if not request:
            console.print("[red]Hata: İstek boş.[/]")
            console.print("[dim]Örnek: petacomm -r \"nginx neden çalışmıyor\"[/]")
            return
        cmd_request(request, dry_run=dry_run)

    elif cmd == "status":
        cmd_status()

    elif cmd == "health":
        cmd_health()

    elif cmd == "ls":
        target = args[1] if len(args) > 1 else ""
        if not target:
            console.print("[yellow]Ne listelensin?[/]")
            console.print("[dim]Örnek: petacomm ls services[/]")
        else:
            cmd_ls(target)

    elif cmd == "logs":
        target = args[1] if len(args) > 1 else "system"
        follow = "--follow" in args or "-f" in args
        cmd_logs(target, follow=follow)

    elif cmd == "find":
        query = " ".join(args[1:])
        if not query:
            console.print("[red]Hata: Arama terimi gerekli.[/]")
            console.print("[dim]Örnek: petacomm find \"gatebell\"[/]")
        else:
            cmd_find(query)

    elif cmd == "backup":
        action = args[1] if len(args) > 1 else "now"
        target = args[2] if len(args) > 2 else ""
        cmd_backup(action, target)

    elif cmd == "restore":
        name = args[1] if len(args) > 1 else ""
        if not name:
            console.print("[red]Hata: Yedek adı gerekli.[/]")
            console.print("[dim]Örnek: petacomm restore 2026-04-17_09-22-00[/]")
        else:
            cmd_restore(name)

    elif cmd == "login":
        cmd_login()

    elif cmd in ("help", "--help", "-h"):
        cmd_help()

    else:
        console.print(f"[yellow]Bilinmeyen komut: {cmd}[/]")
        console.print("[dim]Yardım için: petacomm help[/]")


if __name__ == "__main__":
    main()
