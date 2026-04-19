from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.rule import Rule
from rich.box import ROUNDED
from rich.table import Table
import sys


class ChatConsole:
    def __init__(self):
        self.console = Console()

    def print_header(self, title: str, subtitle: str = ""):
        self.console.print()
        self.console.print(Rule(style="bold cyan", title=title))
        if subtitle:
            self.console.print(f"[dim]{subtitle}[/dim]")
        self.console.print()

    def print_welcome(self):
        self.print_header("🚀 Tech Blog AI Assistant", "基于 Ollama 的智能技术博客助手")

        table = Table(box=ROUNDED, show_header=False, pad_edge=False)
        table.add_column(style="cyan")
        table.add_column(style="white")

        table.add_row("📝 技术栈", "Rust, Node.js, Vue, React, NestJS, Koa, Next.js, Vite, LangChain, Android, Flutter, 微前端, RPC")
        table.add_row("💬 模式", "流式对话 / 批量推理")
        table.add_row("🎯 模型", "qwen2.5:1.5b")

        self.console.print(table)
        self.console.print()

    def print_input_prompt(self):
        self.console.print("[bold cyan]┌─── 输入问题 ───[/bold cyan]")
        self.console.print("[cyan]│[/cyan] ", end="")

    def print_user_message(self, message: str):
        self.console.print()
        panel = Panel(
            message,
            title="[user]👤 你[/user]",
            border_style="green",
            box=ROUNDED,
            padding=(0, 1)
        )
        self.console.print(panel)
        self.console.print()

    def print_ai_start(self):
        self.console.print("[bold cyan]┌─── AI 响应 ───[/bold cyan]")
        self.console.print("[cyan]│[/cyan] ", end="", flush=True)

    def stream_ai_response(self, response_generator):
        self.console.print()
        response = ""
        with Live(
            Panel(
                "",
                title="[ai]🤖 AI 正在思考...[/ai]",
                border_style="blue",
                box=ROUNDED,
            ),
            console=self.console,
            refresh_per_second=10,
            transient=True
        ) as live:
            panel_content = ""
            for chunk in response_generator:
                response += chunk
                panel_content = response
                if len(response) > 500:
                    panel_content = response[:500] + "[dim]...[/dim]"

                live.update(Panel(
                    panel_content,
                    title="[ai]🤖 AI 响应中...[/ai]",
                    border_style="blue",
                    box=ROUNDED,
                ))
                if len(response) > 500:
                    break

        return response

    def print_ai_response(self, response: str):
        if len(response) <= 500:
            panel = Panel(
                response,
                title="[ai]🤖 AI[/ai]",
                border_style="blue",
                box=ROUNDED,
                padding=(0, 1)
            )
            self.console.print(panel)
        else:
            panel = Panel(
                response,
                title="[ai]🤖 AI[/ai]",
                border_style="blue",
                box=ROUNDED,
                padding=(0, 1),
                width=self.console.width - 2
            )
            self.console.print(panel)

    def print_error(self, message: str):
        panel = Panel(
            f"[red]{message}[/red]",
            title="[error]❌ 错误[/error]",
            border_style="red",
            box=ROUNDED
        )
        self.console.print(panel)

    def print_success(self, message: str):
        panel = Panel(
            f"[green]{message}[/green]",
            title="[success]✅ 成功[/success]",
            border_style="green",
            box=ROUNDED
        )
        self.console.print(panel)

    def print_info(self, message: str):
        self.console.print(f"[dim]{message}[/dim]")

    def print_command_hint(self):
        self.console.print()
        self.console.print(Rule(style="dim"))
        self.console.print("[dim]命令:[/dim] [yellow]quit[/yellow]/[yellow]exit[/yellow]/[yellow]q[/yellow] 退出  |  [yellow]clear[/yellow] 清除屏幕")
        self.console.print()

    def clear_screen(self):
        self.console.clear()


class ProgressConsole:
    def __init__(self):
        self.console = Console()
        self.progress = None

    def start(self):
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console
        )
        self.progress.start()

    def add_task(self, description: str, total: int = 100):
        if self.progress:
            return self.progress.add_task(description, total=total)
        return None

    def update(self, task_id, advance: int = 1):
        if self.progress:
            self.progress.update(task_id, advance=advance)

    def stop(self):
        if self.progress:
            self.progress.stop()
