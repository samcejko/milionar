"""
Trade execution via Alpaca REST API.

Direct HTTP calls to Alpaca Trading API - supports fractional shares
for stocks and spot crypto. No SDK dependency.
"""

import logging
import urllib.parse
import asyncio

import aiohttp

from config import Config

log = logging.getLogger("milionar.trader")

def _safe_float(val, default=0.0) -> float:
    return float(val) if val is not None else default



class TradeExecutor:
    """Execute trades through Alpaca Paper Trading API."""

    def __init__(self, config: Config):
        self.config = config
        self.base_url = config.ALPACA_BASE_URL
        self.headers = {
            "APCA-API-KEY-ID": config.ALPACA_API_KEY,
            "APCA-API-SECRET-KEY": config.ALPACA_SECRET_KEY,
            "Content-Type": "application/json",
        }
        self.session = None

    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    # ============================================================
    #  Account & Positions
    # ============================================================

    async def get_portfolio(self) -> dict:
        """Get account information (equity, cash, buying power)."""
        data = await self._request("GET", "/v2/account")
        if "error" in data:
            return {"equity": 0, "cash": 0, "buying_power": 0, "error": data["error"]}

        return {
            "equity": _safe_float(data.get("equity", 0)),
            "cash": _safe_float(data.get("cash", 0)),
            "buying_power": _safe_float(data.get("buying_power", 0)),
            "portfolio_value": _safe_float(data.get("portfolio_value", 0)),
            "initial_equity": _safe_float(data.get("last_equity", data.get("equity", 0))),
        }

    async def get_positions(self) -> list[dict]:
        """Get all open positions with P&L."""
        data = await self._request("GET", "/v2/positions")

        if isinstance(data, dict):
            if "error" in data:
                log.error(f"Failed to get positions: {data['error']}")
            return []

        return [
            {
                "symbol": pos.get("symbol", ""),
                "qty": _safe_float(pos.get("qty", 0)),
                "market_value": _safe_float(pos.get("market_value", 0)),
                "avg_entry_price": _safe_float(pos.get("avg_entry_price", 0)),
                "current_price": _safe_float(pos.get("current_price", 0)),
                "unrealized_pl": _safe_float(pos.get("unrealized_pl", 0)),
                "unrealized_plpc": _safe_float(pos.get("unrealized_plpc", 0)),
                "side": pos.get("side", "long"),
            }
            for pos in data
        ]

    # ============================================================
    #  Order Execution
    # ============================================================

    async def buy(self, ticker: str, amount_pct: float, equity: float, stop_loss_pct: float = None, take_profit_pct: float = None) -> dict:
        """
        Buy a position using a notional (dollar) amount.
        Uses fractional shares for stocks. amount_pct is % of total equity.
        """
        notional = round(equity * (amount_pct / 100), 2)

        if notional < 1.0:
            msg = f"Notional too small: ${notional:.2f} (need at least $1)"
            log.warning(msg)
            return {"executed": False, "reason": msg}

        order = {
            "symbol": ticker.upper().strip(),
            "notional": str(notional),
            "side": "buy",
            "type": "market",
            "time_in_force": "gtc" if "/" in ticker else "day",
        }

        log.info(f"BUY {ticker} - ${notional:.2f} ({amount_pct}% of ${equity:.2f})")
        result = await self._request("POST", "/v2/orders", order)

        if "error" in result:
            log.error(f"Buy order failed: {result['error']}")
            return {"executed": False, "reason": result["error"]}

        order_id = result.get("id")
        if order_id:
            order = await self.wait_for_order(order_id)
            if order.get("status") == "filled":
                filled_qty = order.get("filled_qty")
                filled_avg_price = _safe_float(order.get("filled_avg_price", 0))
                
                if filled_qty and filled_avg_price > 0 and stop_loss_pct:
                    trail_pct = float(stop_loss_pct)
                    ts_order = {
                        "symbol": ticker.upper().strip(),
                        "qty": filled_qty,
                        "side": "sell",
                        "type": "trailing_stop",
                        "trail_percent": str(round(trail_pct, 2)),
                        "time_in_force": "gtc" if "/" in ticker else "day",
                    }
                    ts_res = await self._request("POST", "/v2/orders", ts_order)
                    if "error" in ts_res:
                        log.error(f"Failed to submit Trailing Stop order for {ticker}: {ts_res['error']}")
                    else:
                        log.info(f"Trailing Stop order submitted for {ticker}: Trail {trail_pct}%")

                return {
                    "executed": True,
                    "order_id": order_id,
                    "symbol": ticker,
                    "notional": notional,
                    "side": "buy",
                    "status": "filled",
                    "filled_avg_price": filled_avg_price,
                }
            else:
                log.warning(f"Buy order {order_id} for {ticker} not filled: {order.get('status')}. Cancelling...")
                await self._request("DELETE", f"/v2/orders/{order_id}")
                return {
                    "executed": False,
                    "reason": f"Order pending or rejected: {order.get('status')} - Cancelled.",
                    "order_id": order_id,
                }
                
        return {"executed": False, "reason": "No order ID returned"}

    async def short(self, ticker: str, amount_pct: float, equity: float, stop_loss_pct: float = None, take_profit_pct: float = None) -> dict:
        """Open a SHORT position using a notional amount."""
        if "/" in ticker:
            msg = f"Cannot short crypto on Alpaca: {ticker}"
            log.warning(msg)
            return {"executed": False, "reason": msg}

        notional = round(equity * (amount_pct / 100), 2)
        if notional < 1.0:
            return {"executed": False, "reason": "Notional too small"}

        order = {
            "symbol": ticker.upper().strip(),
            "notional": str(notional),
            "side": "sell",
            "type": "market",
            "time_in_force": "day",
        }

        log.info(f"SHORT {ticker} - ${notional:.2f} ({amount_pct}% of ${equity:.2f})")
        result = await self._request("POST", "/v2/orders", order)

        if "error" in result:
            return {"executed": False, "reason": result["error"]}

        order_id = result.get("id")
        if order_id:
            order_info = await self.wait_for_order(order_id)
            if order_info.get("status") == "filled":
                filled_qty = order_info.get("filled_qty")
                filled_avg_price = _safe_float(order_info.get("filled_avg_price", 0))
                
                if filled_qty and filled_avg_price > 0 and stop_loss_pct:
                    trail_pct = float(stop_loss_pct)
                    ts_order = {
                        "symbol": ticker.upper().strip(),
                        "qty": filled_qty,
                        "side": "buy",
                        "type": "trailing_stop",
                        "trail_percent": str(round(trail_pct, 2)),
                        "time_in_force": "day",
                    }
                    ts_res = await self._request("POST", "/v2/orders", ts_order)
                    if "error" in ts_res:
                        log.error(f"Failed to submit Short Trailing Stop for {ticker}: {ts_res['error']}")
                    else:
                        log.info(f"Short Trailing Stop submitted for {ticker}: Trail {trail_pct}%")

                return {
                    "executed": True,
                    "order_id": order_id,
                    "symbol": ticker,
                    "notional": notional,
                    "side": "sell",
                    "status": "filled",
                    "filled_avg_price": filled_avg_price,
                }
            else:
                log.warning(f"Short order {order_id} not filled. Cancelling...")
                await self._request("DELETE", f"/v2/orders/{order_id}")
                return {"executed": False, "reason": "Order cancelled"}
                
        return {"executed": False, "reason": "No order ID returned"}

    async def sell(self, ticker: str) -> dict:
        """
        Sell/close entire position in a symbol.
        Uses Alpaca's DELETE /v2/positions/{symbol} endpoint.
        """
        ticker = ticker.upper().strip()
        safe_ticker = urllib.parse.quote(ticker, safe="")
        log.info(f"SELL {ticker} - closing entire position")

        result = await self._request("DELETE", f"/v2/positions/{safe_ticker}")

        if "error" in result:
            log.error(f"Sell order failed: {result['error']}")
            return {"executed": False, "reason": result["error"]}

        order_id = result.get("id")
        if order_id:
            order = await self.wait_for_order(order_id)
            if order.get("status") == "filled":
                return {
                    "executed": True,
                    "symbol": ticker,
                    "side": "sell",
                    "status": "filled",
                    "order_id": order_id,
                    "filled_avg_price": _safe_float(order.get("filled_avg_price", 0)),
                }
            else:
                log.warning(f"Sell order {order_id} for {ticker} not filled: {order.get('status')}. Cancelling...")
                # Cleanup pending order
                await self._request("DELETE", f"/v2/orders/{order_id}")
                return {
                    "executed": False,
                    "reason": f"Order pending or rejected: {order.get('status')} - Cancelled.",
                    "order_id": order_id,
                }

        return {
            "executed": True,
            "symbol": ticker,
            "side": "sell",
            "status": "closed",
            "order_id": "",
        }

    async def wait_for_order(self, order_id: str, timeout: int = 15) -> dict:
        """Wait for an order to be filled or rejected."""
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            order = await self._request("GET", f"/v2/orders/{order_id}")
            if "error" in order:
                return order
            
            status = order.get("status")
            if status in ("filled", "canceled", "expired", "rejected"):
                return order
                
            await asyncio.sleep(1)
            
        return {"error": "Timeout waiting for order", "status": "pending"}

    # ============================================================
    #  HTTP Helper
    # ============================================================

    async def _request(self, method: str, endpoint: str, data: dict = None) -> dict:
        """Make authenticated request to Alpaca Trading API with retries."""
        url = f"{self.base_url}{endpoint}"
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                session = await self.get_session()
                async with session.request(method, url, json=data, timeout=15) as resp:
                    if resp.status == 429:
                        log.warning(f"Alpaca API Rate Limit (429). Retrying in 2s (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                        
                    if resp.status >= 500:
                        log.warning(f"Alpaca Server Error ({resp.status}). Retrying in 2s (Attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                        
                    if resp.status >= 400:
                        try:
                            error_body = await resp.json()
                            error_msg = error_body.get("message", f"HTTP {resp.status}")
                        except Exception:
                            error_text = await resp.text()
                            error_msg = f"HTTP {resp.status} - {error_text[:200]}"
                        log.error(f"Alpaca API {method} {endpoint}: {error_msg}")
                        return {"error": error_msg}
                    
                    content = await resp.read()
                    if content:
                        try:
                            return await resp.json()
                        except ValueError:
                            text = await resp.text()
                            log.error(f"Alpaca API {method} {endpoint} returned invalid JSON: {text[:200]}")
                            return {"error": "Invalid JSON response"}
                    return {}
            except aiohttp.ClientError as e:
                log.warning(f"Network error on {endpoint}: {e}. Retrying in 2s (Attempt {attempt+1}/{max_retries})")
                await asyncio.sleep(2)
            except Exception as e:
                log.error(f"Alpaca API {method} {endpoint} unexpected error: {e}")
                return {"error": str(e)}
                
        return {"error": f"Failed after {max_retries} attempts"}
