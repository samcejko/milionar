import os
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.align import Align

console = Console()

def print_dashboard(context: dict, cycle_interval_minutes: int):
    """
    Clears the screen and prints a beautiful Rich dashboard
    summarizing the current portfolio and cycle state.
    """
    # 1. Clear screen
    os.system('cls' if os.name == 'nt' else 'clear')
    
    # 2. Extract context variables
    now_str = datetime.now().strftime("%H:%M:%S")
    portfolio = context.get("portfolio", {})
    equity = float(portfolio.get("equity", 0.0))
    cash = float(portfolio.get("buying_power", 0.0))
    positions = context.get("open_positions", [])
    watchlist = context.get("watchlist", [])
    lessons = context.get("recent_lessons", [])
    
    # 3. Header Panel
    header_text = f"[bold white]🚀 MILIONÁŘ BOT[/bold white] | [cyan]Aktivní cyklus:[/cyan] [bold yellow]{now_str}[/bold yellow] | [cyan]Další cyklus za:[/cyan] [bold yellow]{cycle_interval_minutes} min[/bold yellow]"
    console.print(Panel(Align.center(header_text), style="bold blue"))
    
    # 4. Account Summary Table
    acc_table = Table(show_header=False, expand=True, border_style="green")
    acc_table.add_column("Key", style="bold cyan")
    acc_table.add_column("Value", style="bold green", justify="right")
    
    acc_table.add_row("Celkové Portfolio (Equity)", f"${equity:,.2f}")
    acc_table.add_row("Volná Hotovost (Buying Power)", f"${cash:,.2f}")
    
    console.print(acc_table)
    console.print()
    
    # 5. Open Positions Table
    pos_table = Table(title="[bold underline]Otevřené Pozice[/bold underline]", expand=True, header_style="bold magenta", border_style="magenta")
    pos_table.add_column("Ticker", style="bold white")
    pos_table.add_column("Množství", justify="right")
    pos_table.add_column("Akt. Cena", justify="right")
    pos_table.add_column("Zisk/Ztráta %", justify="right")
    
    if not positions:
        pos_table.add_row("Žádné", "-", "-", "-")
    else:
        for p in positions:
            symbol = p.get("symbol", "N/A")
            qty = p.get("qty", "0")
            current_price = float(p.get("current_price", 0.0))
            unrealized_plpc = float(p.get("unrealized_plpc", 0.0)) * 100
            
            color = "green" if unrealized_plpc >= 0 else "red"
            sign = "+" if unrealized_plpc >= 0 else ""
            
            pos_table.add_row(
                symbol,
                str(qty),
                f"${current_price:.2f}",
                f"[{color}]{sign}{unrealized_plpc:.2f}%[/{color}]"
            )
            
    console.print(pos_table)
    console.print()
    
    # 6. Active Watchlist & Lessons
    info_table = Table(show_header=False, expand=True, box=None)
    info_table.add_column("A", ratio=1)
    
    # Format watchlist
    wl_str = ", ".join(watchlist) if watchlist else "Žádný (Auto-discovery aktivní)"
    wl_panel = Panel(f"[cyan]{wl_str}[/cyan]", title="Sledovaný Watchlist", border_style="cyan")
    info_table.add_row(wl_panel)
    
    # Format lessons if any
    if lessons:
        lessons_str = "\n".join([f"- {l}" for l in lessons])
        les_panel = Panel(f"[yellow]{lessons_str}[/yellow]", title="Poslední Lekce (Z víkendu)", border_style="yellow")
        info_table.add_row(les_panel)
        
    console.print(info_table)
    console.print()
    
    # 7. Action Log Header
    console.print(Panel("[bold green]Tento Cyklus - Log Událostí[/bold green]", style="green"))
