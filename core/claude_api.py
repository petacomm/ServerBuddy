"""
Petacomm - Claude API Integration
Converts natural language requests into server actions,
runs commands, and explains output in human language.
"""

import json
import os
import subprocess
from pathlib import Path


CONFIG_PATH = Path.home() / ".petacomm" / "config.json"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_config(data: dict):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def get_api_key() -> str | None:
    config = load_config()
    return config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")


def set_api_key(key: str):
    config = load_config()
    config["api_key"] = key
    save_config(config)


def _call_claude(messages: list, system: str, api_key: str, max_tokens: int = 1024) -> dict:
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model": "claude-sonnet-4-5",
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["content"][0]["text"]
            return {"success": True, "text": text}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body)
        except Exception:
            msg = body
        return {"success": False, "error": f"API Error: {msg}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _run_command(cmd: str) -> str:
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=15
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        return out if out else err
    except subprocess.TimeoutExpired:
        return "Command timed out after 15 seconds."
    except Exception as e:
        return str(e)


def _build_context(system_context: dict) -> str:
    if not system_context:
        return ""
    ram = system_context.get("ram", {})
    services = system_context.get("services", [])
    health = system_context.get("health", {})
    disks = system_context.get("disks", [])

    disk_info = ""
    for d in disks[:5]:
        disk_info += f"\n  - {d['mount']}: {d['percent']}% used"

    return f"""
Current system state:
- Hostname: {system_context.get('hostname', '?')}
- OS: {system_context.get('os', '?')}
- Kernel: {system_context.get('kernel', '?')}
- IP: {system_context.get('ip', '?')}
- Uptime: {system_context.get('uptime', '?')}
- CPU usage: {system_context.get('cpu', '?')}%
- RAM: {ram.get('percent', '?')}% ({ram.get('used', 0) // 1024 // 1024}MB of {ram.get('total', 0) // 1024 // 1024}MB)
- Disks:{disk_info}
- Running services: {', '.join(s['name'] for s in services if s.get('active')) or 'none'}
- Failed services: {', '.join(s['name'] for s in services if s.get('status') == 'failed') or 'none'}
- Health score: {health.get('score', '?')}/100
- Warnings: {', '.join(health.get('warnings', [])) or 'none'}
- Critical issues: {', '.join(health.get('criticals', [])) or 'none'}
"""


def ask_claude(request: str, system_context: dict = None, api_key: str = None) -> dict:
    """
    Two-turn pipeline:
    1. Claude decides what command to run
    2. Command runs on the server
    3. Claude explains the output in plain human language
    """
    key = api_key or get_api_key()
    if not key:
        return {
            "success": False,
            "error": "API key not found. Run: petacomm login",
            "response": None,
        }

    context_str = _build_context(system_context)

    # ── Turn 1: Decide what command to run ───────────────────────────────────
    turn1_system = f"""You are Petacomm, an AI-powered Linux server management assistant.
Your job is to help users manage their Linux server using plain natural language.

{context_str}

RULES:
1. LANGUAGE: Always detect what language the user is writing in and respond in that exact same language.
   Turkish → Turkish, English → English, German → German, etc.

2. COMMANDS: When you need real data from the server, respond ONLY with this JSON and nothing else:
   {{"run": "the shell command"}}
   Examples:
   {{"run": "df -h"}}
   {{"run": "free -h"}}
   {{"run": "ps aux --sort=-%cpu | head -20"}}

3. DANGEROUS OPS: For destructive operations (rm, drop database, format), never run automatically.
   Instead explain what will happen and ask for confirmation.

4. BEGINNER FRIENDLY: Always explain technical terms simply.
   Bad: "Your /dev/sda1 has 87% inode usage"
   Good: "Your main hard drive is almost full (87% used)"

5. If no command is needed, answer directly in the user's language."""

    turn1 = _call_claude(
        messages=[{"role": "user", "content": request}],
        system=turn1_system,
        api_key=key,
        max_tokens=512,
    )

    if not turn1["success"]:
        return {"success": False, "error": turn1["error"], "response": None}

    turn1_text = turn1["text"].strip()

    # Check if Claude wants to run a command
    command_output = None
    command_ran = None

    try:
        import re
        clean = turn1_text
        # Strip markdown code blocks if present
        if "```" in clean:
            match = re.search(r'\{[^}]+\}', clean, re.DOTALL)
            if match:
                clean = match.group(0)
        parsed = json.loads(clean)
        if "run" in parsed:
            command_ran = parsed["run"]
            command_output = _run_command(command_ran)
    except (json.JSONDecodeError, ValueError):
        pass

    # ── Turn 2: Explain the output in human language ──────────────────────────
    if command_output is not None:
        turn2_system = f"""You are Petacomm, an AI-powered Linux server management assistant.
{context_str}

RULES:
1. LANGUAGE: The user wrote in a specific language. Respond in that EXACT same language.
   Detect it from the user's original message and match it perfectly.

2. You just ran: `{command_ran}`
   Raw output:
   ---
   {command_output}
   ---

3. Explain this output as if talking to someone who has NEVER used Linux before.
   - Replace ALL technical terms with simple explanations
   - Use real-world analogies (hard drive = like a filing cabinet, RAM = like a desk workspace)
   - Show what's ✅ good, ⚠️ needs attention, ❌ is a problem
   - Format sizes in human readable form (GB, MB — not bytes)
   - If there's a problem, tell them exactly what to do next in simple steps

4. Structure:
   - One sentence summary
   - Breakdown of important items
   - Next steps if needed (optional)"""

        turn2 = _call_claude(
            messages=[
                {"role": "user", "content": request},
                {"role": "assistant", "content": turn1_text},
                {"role": "user", "content": f"Here is the command output:\n{command_output}"},
            ],
            system=turn2_system,
            api_key=key,
            max_tokens=1024,
        )

        if not turn2["success"]:
            return {"success": False, "error": turn2["error"], "response": None}

        return {
            "success": True,
            "response": turn2["text"],
            "command_ran": command_ran,
            "command_output": command_output,
            "error": None,
        }

    return {
        "success": True,
        "response": turn1_text,
        "command_ran": None,
        "command_output": None,
        "error": None,
    }
