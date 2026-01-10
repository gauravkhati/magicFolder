import sys
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from textual.app import App, ComposeResult
from textual.containers import  Horizontal, Vertical
from textual.widgets import Header, Footer, DirectoryTree, RichLog, Input, Label
from textual.binding import Binding
from textual import work, on

# MCP & AI Imports
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import tool

MOUNT_POINT = "/Users/gauravkhati/MagicFolder_Search/"

class MagicHeader(Header):
    """Custom header with sci-fi styling."""
    def __init__(self):
        super().__init__(show_clock=True)
        self.styles.background = "#001100"
        self.styles.color = "#00ff00"

class MagicTree(DirectoryTree):
    """Styled directory tree."""
    def on_mount(self):
        self.styles.background = "#000800"
        self.styles.color = "#00aa00"
        self.styles.border = ("heavy", "#00ff00")

class MagicLog(RichLog):
    """Styled log window."""
    def on_mount(self):
        self.styles.background = "#000500"
        self.styles.color = "#00ff00"
        self.styles.border = ("heavy", "#00ff00")

class MagicInput(Input):
    """Styled input."""
    def on_mount(self):
        self.styles.background = "#001100"
        self.styles.color = "#00ff00"
        self.styles.border = ("heavy", "#00ff00")

class AGenFinder(App):
    """A System Monitor for MagicFolder (AI Agent)."""

    CSS = """
    Screen { background: #000000; color: #00ff00; }
    Container { height: 1fr; }
    Horizontal { height: 1fr; }
    Vertical { height: 1fr; width: 1fr; }
    Label { padding: 1; background: #002200; color: #00ff00; text-align: center; width: 100%; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "refresh_tree", "Refresh Tree"),
    ]

    def compose(self) -> ComposeResult:
        yield MagicHeader()
        with Horizontal():
            with Vertical():
                yield Label(":: FINDER ON STEROIDS ::")
                path = MOUNT_POINT if os.path.exists(MOUNT_POINT) else "."
                yield MagicTree(path, id="tree_view")
            with Vertical():
                yield Label(":: HEARTBEAT ::")
                yield MagicLog(id="log_view", highlight=True, markup=True)
        yield Label(":: COMMAND INTERFACE ::")
        yield MagicInput(placeholder="Speak, mortal... I'm listening (probably)")
        yield Footer()

    def on_mount(self) -> None:
        self.log_message("[bold green]SYSTEM INITIALIZED.[/]")
        self.log_message("Initializing Neural Link (MCP)...")

    def log_message(self, message: str) -> None:
        log_view = self.query_one("#log_view", RichLog)
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_view.write(f"[{timestamp}] {message}")

    @work(exclusive=True)
    async def process_user_request(self, user_input: str) -> None:
        """The Brain: Connects to MCP, gets tools, binds to LLM, and executes."""
        self.log_message(f"User Query: [bold yellow]'{user_input}'[/]")
        
        # 1. Setup MCP Connection
        server_script = os.path.join(os.path.dirname(__file__), '..', 'mcp_server', 'server.py')
        python_exe = sys.executable 
        server_params = StdioServerParameters(
            command=python_exe, args=[server_script], env=os.environ.copy()
        )
        

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    mcp_tools_list = await session.list_tools()
                    self.log_message(f"Discovered {len(mcp_tools_list.tools)} tools from MCP Server.")

                    # Convert MCP tools to LangChain format
                
                    langchain_tools = []
                    for t in mcp_tools_list.tools:
                        @tool(t.name)
                        def dynamic_tool(**kwargs):
                            """Dynamic MCP Tool"""
                            # This is a placeholder; the actual execution happens in the loop below
                            pass
                        
                        dynamic_tool.name = t.name
                        dynamic_tool.description = t.description or "No description"
                        langchain_tools.append(dynamic_tool)

                    google_api_key = os.getenv("GOOGLE_API_KEY")
                    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.2,api_key=google_api_key)
                    llm_with_tools = llm.bind_tools(langchain_tools)

                    #todo:  Currently (Simple 1-turn). Need to enhance for more multi-tasking
                    messages = [HumanMessage(content=user_input)]
                    ai_msg = await llm_with_tools.ainvoke(messages)
                    messages.append(ai_msg)
                    # 6. Handle Tool Calls
                    if ai_msg.tool_calls:
                        for tool_call in ai_msg.tool_calls:
                            tool_name = tool_call["name"]
                            tool_args = tool_call["args"]
                            
                            # Fix: Unwrap 'kwargs' if LangChain wrapped the arguments
                            if "kwargs" in tool_args:
                                tool_args = tool_args["kwargs"]
                            
                            self.log_message(f"AI Decision: Call [bold cyan]{tool_name}[/] with {tool_args}")
                            
                            # Execute via MCP Session
                            result = await session.call_tool(tool_name, arguments=tool_args)
                            self.log_message(f"{result}")
                            # Parse result
                            tool_output = ""
                            if result.content:
                                for c in result.content:
                                    if c.type == "text": tool_output += c.text
                            
                            self.log_message(f"Tool Output: {tool_output[:1000]}...") # Log preview
                            messages.append(ToolMessage(content=tool_output, tool_call_id=tool_call["id"]))

                        # 7. Get Final Response
                        final_response = await llm_with_tools.ainvoke(messages)
                        self.log_message(f"[bold white]AI Response:[/]\n{final_response.content}")
                    else:
                        # No tool needed
                        self.log_message(f"[bold white]AI Response:[/]\n{ai_msg.content}")

        except Exception as e:
            self.log_message(f"[bold red]System Error: {type(e).__name__}: {str(e)}[/]")
            import traceback
            tb = traceback.format_exc()
            self.log_message(f"[red]{tb}[/]")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value
        if not query: return
        event.input.value = ""
        self.process_user_request(query)

    @on(DirectoryTree.FileSelected)
    def handle_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection to open the file with system default."""
        path = event.path
        self.log_message(f"[bold yellow]:: LAUNCHING FILE: {os.path.basename(path)} ::[/]")
        
        try:
            if sys.platform == "darwin":
                os.system(f'open "{path}"')
            elif sys.platform == "linux":
                os.system(f'xdg-open "{path}"')
            elif sys.platform == "win32":
                os.startfile(path)
            
        except Exception as e:
            self.log_message(f"[bold red]Error opening file: {e}[/]")

    def action_refresh_tree(self) -> None:
        tree = self.query_one("#tree_view", DirectoryTree)
        tree.reload()
        self.log_message("Filesystem matrix refreshed.")


if __name__ == "__main__":
    app = AGenFinder()
    app.run()

# Find files having train tickets from haldwani to lucknow
# Fin