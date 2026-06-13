"""
MCP Client — manages connection to the Alpaca MCP Server.

Responsibilities:
1. Start Alpaca MCP Server as subprocess via stdio
2. Discover available tools and convert to LLM-compatible schemas
3. Execute tool calls by forwarding them to MCP
4. Manage connection lifecycle (connect/disconnect)

The MCP connection is kept alive for the bot's entire lifetime
to avoid ~2s startup overhead per cycle.
"""

import asyncio
import json
import logging
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import Config

log = logging.getLogger("milionar.mcp")


class McpToolProvider:
    """
    Async MCP client that acts as the bot's read-only tool provider.

    Connects to Alpaca MCP Server via stdio and exposes:
    - tool_schemas: list of tool definitions for LLM prompt injection
    - call_tool(): execute a tool call and return the result

    SECURITY: Only account/stock-data/crypto-data toolsets are enabled.
    Trading orders go through executor.py, NOT through MCP.
    """

    def __init__(self, config: Config):
        self.config = config
        self._session: ClientSession | None = None
        self._stdio_context = None
        self._session_context = None
        self._tools: list = []           # Raw MCP tool objects
        self._tool_schemas: list[dict] = []  # LLM-friendly schemas

    @property
    def connected(self) -> bool:
        """Check if MCP session is active."""
        return self._session is not None

    @property
    def tool_schemas(self) -> list[dict]:
        """Tool definitions formatted for the LLM system prompt."""
        return self._tool_schemas

    @property
    def tool_names(self) -> set[str]:
        """Set of available tool names for quick lookup."""
        return {t["name"] for t in self._tool_schemas}

    # ── Connection lifecycle ────────────────────────────────

    async def connect(self) -> None:
        """Start MCP server subprocess and initialize session."""
        log.info("🔌 Connecting to Alpaca MCP Server...")

        toolsets = self.config.MCP_TOOLSETS

        import sys
        if sys.platform == "win32":
            cmd = "cmd.exe"
            args = ["/c", "uvx", "alpaca-mcp-server", "serve"]
        else:
            cmd = "alpaca-mcp-server"
            args = ["serve"]

        server_params = StdioServerParameters(
            command=cmd,
            args=args,
            env={
                **os.environ,
                "ALPACA_API_KEY": self.config.ALPACA_API_KEY,
                "ALPACA_SECRET_KEY": self.config.ALPACA_SECRET_KEY,
                "ALPACA_TOOLSETS": toolsets,
            },
        )

        try:
            # Enter the stdio context (starts subprocess)
            self._stdio_context = stdio_client(server_params)
            read, write = await self._stdio_context.__aenter__()

            # Enter the session context
            self._session_context = ClientSession(read, write)
            self._session = await self._session_context.__aenter__()

            # Initialize MCP handshake (with timeout)
            await asyncio.wait_for(self._session.initialize(), timeout=1000)

            # Discover tools
            await self._discover_tools()

            log.info(
                f"✅ MCP connected — {len(self._tools)} tools available: "
                f"{', '.join(t.name for t in self._tools)}"
            )
        except asyncio.TimeoutError:
            log.error("❌ MCP server handshake timed out (1000s)")
            await self.disconnect()
            raise RuntimeError("MCP server handshake timed out")
        except OSError as e:
            log.error(f"❌ Cannot start MCP server process: {e}")
            await self.disconnect()
            raise RuntimeError(f"Cannot start MCP server: {e}")
        except Exception as e:
            log.error(f"❌ MCP connection failed: {e}", exc_info=True)
            await self.disconnect()
            raise

    async def disconnect(self) -> None:
        """Gracefully close MCP session and subprocess."""
        log.info("🔌 Disconnecting from MCP server...")
        try:
            if self._session_context:
                await self._session_context.__aexit__(None, None, None)
            if self._stdio_context:
                await self._stdio_context.__aexit__(None, None, None)
        except Exception as e:
            log.warning(f"MCP disconnect warning: {e}")
        finally:
            self._session = None
            self._stdio_context = None
            self._session_context = None
            self._tools = []
            self._tool_schemas = []

    # ── Tool discovery ──────────────────────────────────────

    async def _discover_tools(self) -> None:
        """Fetch tool list from MCP server and build LLM-friendly schemas."""
        result = await self._session.list_tools()
        self._tools = result.tools

        self._tool_schemas = []
        for tool in self._tools:
            schema = {
                "name": tool.name,
                "description": tool.description or "",
                "args": {},
            }
            # Extract parameter info from inputSchema (JSON Schema)
            if tool.inputSchema and "properties" in tool.inputSchema:
                for param_name, param_def in tool.inputSchema["properties"].items():
                    param_type = param_def.get("type", "string")
                    param_desc = param_def.get("description", "")
                    required = param_name in tool.inputSchema.get("required", [])
                    schema["args"][param_name] = (
                        f"{param_type} — {param_desc}"
                        + (" (povinný)" if required else " (nepovinný)")
                    )
            self._tool_schemas.append(schema)

    # ── Tool execution ──────────────────────────────────────

    async def call_tool(self, tool_name: str, args: dict) -> str:
        """
        Execute a tool call via MCP and return the result as a JSON string.

        This is the main interface used by the thinker's tool-calling loop.
        Never raises — always returns a JSON string (possibly with an error key).
        """
        if not self._session:
            return json.dumps({"error": "MCP session not connected"})

        if tool_name not in self.tool_names:
            return json.dumps({"error": f"Neznámý MCP nástroj: {tool_name}"})

        try:
            log.info(f"🔧 MCP call_tool: {tool_name}({args})")
            result = await asyncio.wait_for(
                self._session.call_tool(tool_name, arguments=args),
                timeout=30,
            )

            # Check for error flag
            if result.isError:
                error_texts = []
                for block in (result.content or []):
                    if hasattr(block, "text"):
                        error_texts.append(block.text)
                error_msg = "\n".join(error_texts) or "Unknown MCP error"
                log.error(f"MCP tool '{tool_name}' returned error: {error_msg}")
                return json.dumps({"error": error_msg})

            # Extract text content from CallToolResult
            texts = []
            for block in (result.content or []):
                if hasattr(block, "text"):
                    texts.append(block.text)

            combined = "\n".join(texts) if texts else "{}"

            # Try to parse as JSON for cleaner output
            try:
                parsed = json.loads(combined)
                return json.dumps(parsed, ensure_ascii=False, default=str)
            except json.JSONDecodeError:
                return combined

        except asyncio.TimeoutError:
            log.error(f"⚠️ MCP tool '{tool_name}' timed out (30s)")
            return json.dumps({"error": f"MCP nástroj '{tool_name}' timeout (30s)"})
        except ConnectionError as e:
            log.error(f"⚠️ MCP connection lost during '{tool_name}': {e}")
            return json.dumps({"error": f"MCP spojení ztraceno: {e}"})
        except Exception as e:
            log.error(f"❌ MCP tool '{tool_name}' failed: {e}", exc_info=True)
            return json.dumps({"error": str(e)})
