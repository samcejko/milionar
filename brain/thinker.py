"""
AI reasoning engine with OpenRouter model fallback.

Core responsibilities:
1. Call LLM via OpenRouter API with automatic fallback through model priority list
2. Implement async tool-calling loop (tools dispatched via MCP or local)
3. Parse structured JSON responses from LLM output
4. Return a trading decision (BUY/SELL/HOLD)
"""

import json
import logging
import re
import asyncio

import aiohttp

from config import Config
from brain.prompts import build_system_prompt, build_analysis_prompt

FALLBACK_MODELS = [
    "poolside/laguna-m.1:free",
    "qwen/qwen3-coder-480b-a35b-instruct:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3-super:free",
    "openrouter/owl-alpha:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "poolside/laguna-xs.2:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "nex-agi/nex-n2-pro:free",
    "google/gemma-4-31b:free",
    "openai/gpt-oss-20b:free",
    "openai/gpt-oss-120b:free",
    "nousresearch/hermes-3-405b-instruct:free"
]

log = logging.getLogger("milionar.brain")


class Thinker:
    """AI brain - LLM reasoning with fallback and async tool-calling."""

    def __init__(self, config: Config):
        self.config = config
        self.headers = {
            "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/milionar-bot",
            "X-Title": "Milionar Trading Bot",
        }

    # ============================================================
    #  Main analysis entry point
    # ============================================================

    async def analyze(self, context: dict, tools) -> dict:
        """
        Run the full AI analysis cycle:
        1. Build prompt with context (tool schemas from MCP + local)
        2. Call LLM (with fallback) - sync HTTP via requests
        3. Handle tool calls (up to MAX_TOOL_CALLS) - async for MCP
        4. Return final decision

        Returns dict with at minimum: {"action": "BUY/SELL/HOLD", ...}
        """
        system_prompt = build_system_prompt(tools.get_all_tool_schemas())
        user_prompt = build_analysis_prompt(context)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # -- Tool-calling loop -------------------------------
        for iteration in range(self.config.MAX_TOOL_CALLS + 1):
            try:
                raw_response = await self._call_llm(messages)
            except RuntimeError as e:
                log.error(f"All models failed: {e}")
                return {
                    "type": "decision",
                    "action": "RETRY",
                    "reasoning": f"All AI models failed: {e}",
                }

            parsed = self._parse_json(raw_response)

            response_type = parsed.get("type", "")

            # -- Tool call: execute tool and continue loop ---
            if response_type == "tool_call":
                tool_name = parsed.get("tool", "")
                tool_args = parsed.get("args", {})
                log.info(
                    f"[TOOL] Call #{iteration + 1}/{self.config.MAX_TOOL_CALLS}: "
                    f"{tool_name}({tool_args})"
                )

                # Safety net: individual tool failures must not crash the cycle
                try:
                    tool_result = await tools.execute(tool_name, tool_args)
                except Exception as e:
                    log.error(f"[ERROR] Tool '{tool_name}' crashed: {e}")
                    tool_result = json.dumps({"error": f"Tool failed: {e}"})

                # -- HARD RULE: Crypto Volatility Kill-Switch --------------
                if tool_name == "get_technical_analysis":
                    try:
                        parsed_result = json.loads(tool_result)
                        if parsed_result.get("is_volatile"):
                            log.warning("[WARNING] Crypto Volatility Kill-Switch triggered during THINK phase!")
                            tool_result = json.dumps({"error": "This crypto is extremely volatile right now. DO NOT BUY IT. Look for other opportunities or choose HOLD if no other options."})
                    except json.JSONDecodeError:
                        pass
                # ----------------------------------------------------------

                # Append tool interaction to conversation history
                messages.append({"role": "assistant", "content": raw_response})
                messages.append({
                    "role": "user",
                    "content": (
                        f"Result of tool '{tool_name}':\n"
                        f"```json\n{tool_result}\n```\n\n"
                        f"Continue analysis. If you have enough information, "
                        f"make a final decision."
                    ),
                })
                continue

            # -- Final decision: return it -------------------
            if response_type == "decision":
                action = parsed.get("action", "HOLD")
                
                if action != "HOLD":
                    # --- Risk Officer Debate ---
                    veto_parsed = await self._run_risk_officer(context, parsed)
                    if veto_parsed.get("veto"):
                        log.warning(f"[WARNING] Risk Officer vetoed trade {action} {parsed.get('ticker')}: {veto_parsed.get('reasoning')}")
                        return {
                            "type": "decision",
                            "action": "HOLD",
                            "reasoning": f"Risk Officer VETO: {veto_parsed.get('reasoning')}",
                        }

                # Calculate confidence from rubric if missing
                if "confidence" not in parsed and "trend_score" in parsed:
                    try:
                        avg_score = (float(parsed.get("trend_score", 0)) + 
                                     float(parsed.get("macro_score", 0)) + 
                                     float(parsed.get("hype_score", 0))) / 3.0
                        # map -1..1 to 0..1
                        parsed["confidence"] = round((avg_score + 1.0) / 2.0, 2)
                    except ValueError:
                        parsed["confidence"] = 0.5
                
                log.info(
                    f"Final decision: {action} "
                    f"{'(' + parsed.get('ticker', '') + ')' if parsed.get('ticker') else ''} "
                    f"[confidence: {parsed.get('confidence', 'N/A')}]"
                )
                return parsed

            # -- Unrecognized format -------------------------
            log.warning(f"Unrecognized response type: '{response_type}'")
            # Try to salvage - if it has an 'action', treat as decision
            if "action" in parsed:
                parsed["type"] = "decision"
                return parsed

            return {
                "action": "HOLD",
                "reasoning": f"Could not parse AI response (type='{response_type}')",
            }

        # Exhausted all tool call iterations
        log.warning("Max tool calls reached - defaulting to HOLD")
        return {
            "action": "HOLD",
            "reasoning": "Maximum tool calls reached without final decision",
        }

    # ============================================================
    #  Risk Officer (Multi-Agent Debate)
    # ============================================================

    async def _run_risk_officer(self, context: dict, decision: dict) -> dict:
        """Second-pass LLM call to act as a Risk Officer."""
        log.info("[RISK] Risk Officer - checking decision...")
        
        ro_prompt = (
            "You are the Chief Risk Officer for a trading fund. Your job is to protect capital but ALSO allow high-quality setups to pass.\n"
            "Your analyst just proposed the following trade:\n"
            f"```json\n{json.dumps(decision, indent=2)}\n```\n\n"
            "Check this proposal against the current market context.\n"
            "CRITICAL INSTRUCTION: Do NOT automatically veto trades just because of general macroeconomic fear, crypto hacks, or geopolitical noise, unless they directly and severely impact this specific asset. Only veto if the technical/fundamental setup is objectively terrible or the risk is extreme.\n"
            "If you find a truly critical and direct problem, veto it (veto: true). Otherwise, allow it (veto: false).\n"
            "Reply strictly in JSON format:\n"
            "{\n"
            '  "type": "risk_assessment",\n'
            '  "veto": true,\n'
            '  "reasoning": "Your argument for or against vetoing."\n'
            "}"
        )
        
        user_prompt = build_analysis_prompt(context)
        
        messages = [
            {"role": "system", "content": "You are an experienced Risk Manager in an algorithmic trading fund. Always respond in strict JSON format as instructed."},
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": "I have analyzed the context. What did the analyst propose?"},
            {"role": "user", "content": ro_prompt}
        ]
        
        try:
            raw_response = await self._call_llm(messages)
            
            blocks = []
            depth = 0
            start = -1
            for i, char in enumerate(raw_response):
                if char == '{':
                    if depth == 0: start = i
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 0 and start != -1:
                        blocks.append(raw_response[start:i+1])
                        start = -1
            for block in reversed(blocks):
                try:
                    obj = json.loads(block)
                    if "veto" in obj:
                        return obj
                except json.JSONDecodeError:
                    pass
            # If Risk Officer answers with invalid JSON, don't block the trade.
            log.warning("Risk Officer did not reply validly, passing trade by default.")
            return {"veto": False, "reasoning": "Risk Officer did not reply with valid JSON, safe pass applied."}
        except Exception as e:
            log.warning(f"Risk Officer failed: {e}")
            return {"veto": False, "reasoning": f"Risk Officer failed to respond properly: {e} (failsafe pass)"}

    # ============================================================
    #  LLM call with model fallback
    # ============================================================

    async def _call_llm(self, messages: list[dict]) -> str:
        """
        Call OpenRouter API with automatic fallback through the model
        priority list. Tries each model in order; on rate limit (429)
        or any error, moves to the next model.

        Raises RuntimeError if ALL models fail.
        """
        last_error = None

        for model_id in FALLBACK_MODELS:
            try:
                log.info(f"Trying model: {model_id}")

                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        self.config.OPENROUTER_URL,
                        headers=self.headers,
                        json={
                            "model": model_id,
                            "messages": messages,
                            "temperature": 0.3,
                            "max_tokens": 1024,
                            "response_format": {"type": "json_object"},
                        },
                        timeout=aiohttp.ClientTimeout(total=90),
                    ) as resp:

                        if resp.status >= 400:
                            err_text = await resp.text()
                            msg = f"HTTP {resp.status} - {err_text}"
                            log.warning(f"Model {model_id} failed: {msg}")
                            last_error = msg
                            await asyncio.sleep(2)
                            continue

                        resp.raise_for_status()
                        data = await resp.json()

                # Extract content from response
                choices = data.get("choices", [])
                if not choices:
                    last_error = f"Empty choices in response: {data}"
                    log.warning(f"Model {model_id} failed: {last_error}")
                    continue

                content = choices[0].get("message", {}).get("content", "")
                if not content or not content.strip():
                    last_error = "Empty content string returned"
                    log.warning(f"Model {model_id} failed: {last_error}")
                    continue

                # JSON Validation
                parsed = self._parse_json(content)
                if parsed.get("reasoning") == "Could not parse AI response as JSON" or parsed.get("reasoning") == "Empty response from AI":
                    last_error = f"Invalid JSON format returned"
                    log.warning(f"Invalid JSON from {model_id}")
                    continue

                log.info(f"Successful response from {model_id}")
                return content

            except Exception as e:
                log.warning(f"Model {model_id} failed or returned empty response, trying next...")
                last_error = str(e)

            # Brief pause between model attempts
            await asyncio.sleep(2)

        raise RuntimeError(f"All {len(FALLBACK_MODELS)} models failed. Last error: {last_error}")

    # ============================================================
    #  JSON parsing from LLM output
    # ============================================================

    def _parse_json(self, text: str) -> dict:
        """
        Extract a JSON object from LLM response text.

        Handles:
        - Raw JSON objects
        - JSON wrapped in ```json ... ``` code blocks
        - JSON with surrounding text/explanation

        Falls back to HOLD if parsing fails.
        """
        if not text or not text.strip():
            return self._hold("Empty response from AI")

        # Strategy 1: Try parsing the entire response as JSON
        try:
            obj = json.loads(text.strip())
            if self._is_valid_schema(obj):
                return obj
        except json.JSONDecodeError:
            pass

        # Strategy 2: Extract from markdown code block
        code_block = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if code_block:
            try:
                obj = json.loads(code_block.group(1).strip())
                if self._is_valid_schema(obj):
                    return obj
            except json.JSONDecodeError:
                pass

        # Strategy 3: Regex JSON block extraction (matches from first { to last })
        match = re.search(r"(\{.*\})", text, re.DOTALL)
        if match:
            block = match.group(1)
            try:
                obj = json.loads(block)
                if self._is_valid_schema(obj):
                    return obj
            except json.JSONDecodeError:
                healed = re.sub(r",(\s*[}\]])", r"\1", block)
                try:
                    obj = json.loads(healed)
                    if self._is_valid_schema(obj):
                        return obj
                except json.JSONDecodeError:
                    pass

        # Strategy 4: Give up - log the response and default to HOLD
        log.warning(f"Could not parse JSON from AI response: {text[:300]}...")
        return self._hold("Could not parse AI response as JSON")

    @staticmethod
    def _hold(reason: str) -> dict:
        """Return a safe HOLD decision."""
        return {"type": "decision", "action": "HOLD", "reasoning": reason}

    def _is_valid_schema(self, obj: dict) -> bool:
        """Strictly validate that the parsed JSON has the required keys."""
        if not isinstance(obj, dict):
            return False
        
        # Auto-heal legacy formats
        if "action" in obj and "type" not in obj:
            obj["type"] = "decision"
            
        resp_type = obj.get("type")
        if resp_type == "decision":
            return "action" in obj and "reasoning" in obj
        elif resp_type == "tool_call":
            return "tool" in obj
        elif resp_type == "risk_assessment":
            return "veto" in obj
        return False
