"""
Petacomm - Claude API Integration
Two-turn pipeline: understands request -> runs command -> explains output in human language.
"""

import json
import os
import re
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
        with urllib.request.urlopen(req, timeout=60) as resp:
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
            cmd, shell=True, capture_output=True, text=True, timeout=60
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        return out if out else err
    except subprocess.TimeoutExpired:
        return "Command timed out after 60 seconds."
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


def _detect_language(text: str, api_key: str) -> str:
    result = _call_claude(
        messages=[{"role": "user", "content": f"What language is this text written in? Reply with only the language name in English, nothing else. Text: {text}"}],
        system="You are a language detector. Reply with only the language name in English (e.g. Turkish, English, German). Nothing else.",
        api_key=api_key,
        max_tokens=10,
    )
    return result.get("text", "English").strip()


def _confirmation_words(language: str) -> dict:
    words = {
        "Turkish":    {"yes": ["evet", "e", "tamam", "ok"], "no": ["hayır", "h", "iptal"],    "prompt": "Onaylıyor musunuz? (Evet/Hayır)"},
        "English":    {"yes": ["yes", "y", "ok", "sure"],   "no": ["no", "n", "cancel"],       "prompt": "Do you confirm? (Yes/No)"},
        "German":     {"yes": ["ja", "j", "ok"],             "no": ["nein", "n"],               "prompt": "Bestätigen Sie? (Ja/Nein)"},
        "French":     {"yes": ["oui", "o", "ok"],            "no": ["non", "n"],                "prompt": "Confirmez-vous? (Oui/Non)"},
        "Spanish":    {"yes": ["sí", "si", "s", "ok"],       "no": ["no", "n"],                 "prompt": "¿Confirma? (Sí/No)"},
    }
    return words.get(language, words["English"])


def clean_response(text: str) -> str:
    """Remove markdown and leaked JSON from Claude response."""
    # Remove JSON blocks completely (run, confirm, danger)
    text = re.sub(r'\{[^{}]*?"run"\s*:[^{}]*?\}', '', text, flags=re.DOTALL)
    text = re.sub(r'\{[^{}]*?"confirm"\s*:[^{}]*?\}', '', text, flags=re.DOTALL)
    text = re.sub(r'\{[^{}]*?"danger"\s*:[^{}]*?\}', '', text, flags=re.DOTALL)
    # Remove markdown headers
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # Remove bold/italic
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', text)
    # Remove code blocks but keep content
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    # Remove inline code backticks but keep content
    text = re.sub(r'`([^`\n]+)`', r'\1', text)
    # Replace horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '─' * 40, text, flags=re.MULTILINE)
    # Clean extra blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def ask_claude(request: str, system_context: dict = None, api_key: str = None) -> dict:
    """
    Two-turn pipeline:
    1. Claude decides what to do
    2. If safe command -> run immediately
    3. If dangerous -> ask confirmation in user's language
    4. Explain output in plain human language
    """
    key = api_key or get_api_key()
    if not key:
        return {"success": False, "error": "API key not found. Run: petacomm login", "response": None}

    context_str = _build_context(system_context)
    language = _detect_language(request, key)

    # ── Turn 1: Decide what to do ─────────────────────────────────────────────
    turn1_system = f"""You are Petacomm, an AI-powered Linux server management assistant.
The user's language is: {language}. You MUST respond in {language}.

{context_str}

RULES:
1. Always respond in {language}.

2. To run safe read-only commands (ls, df, free, ps, cat, grep, journalctl, ss, who, last, whois, host, etc.):
   Respond with ONLY this on the very last line, nothing after it:
   PETACOMM_RUN: <the full shell command>
   
   If multiple commands needed, chain them with && or use pipes in ONE single command.
   Example: PETACOMM_RUN: journalctl -u sshd --since '24 hours ago' | grep 'Failed' | grep -oE '([0-9]{{1,3}}\.){{3}}[0-9]{{1,3}}' | sort | uniq -c | sort -rn
   
   For SSH logs always use "sshd" not "ssh" in journalctl.
   NEVER write explanations after PETACOMM_RUN line.

3. For DANGEROUS or MODIFYING operations (apt upgrade, rm, systemctl restart/stop, useradd, etc.):
   - Explain what will happen in simple terms in {language}
   - List the risks
   - End with EXACTLY this on the last line, nothing after:
   PETACOMM_CONFIRM: <the exact command to run> | DANGER: low|medium|high

4. If no command needed, just answer directly in {language}.

5. Explain everything as if talking to a complete beginner. Use simple analogies."""

    turn1 = _call_claude(
        messages=[{"role": "user", "content": request}],
        system=turn1_system,
        api_key=key,
        max_tokens=768,
    )

    if not turn1["success"]:
        return {"success": False, "error": turn1["error"], "response": None}

    turn1_text = turn1["text"].strip()

    # ── Parse response ────────────────────────────────────────────────────────
    command_ran = None
    command_output = None
    confirmed = False

    # Check for PETACOMM_RUN
    run_match = re.search(r'PETACOMM_RUN:\s*(.+?)$', turn1_text, re.MULTILINE)

    # Check for PETACOMM_CONFIRM
    confirm_match = re.search(r'PETACOMM_CONFIRM:\s*(.+?)\s*\|\s*DANGER:\s*(low|medium|high)', turn1_text, re.IGNORECASE)

    if run_match:
        command_ran = run_match.group(1).strip()
        command_output = _run_command(command_ran)

    elif confirm_match:
        confirm_cmd = confirm_match.group(1).strip()
        danger = confirm_match.group(2).strip()

        # Show explanation (everything before the PETACOMM_CONFIRM line)
        explanation = turn1_text[:confirm_match.start()].strip()
        explanation = clean_response(explanation)

        conf_words = _confirmation_words(language)

        danger_icon = {"low": "⚠️", "medium": "⚠️", "high": "🔴"}.get(danger, "⚠️")

        print()
        print("─" * 60)
        if explanation:
            print(explanation)
            print()
        print(f"{danger_icon} {conf_words['prompt']} ", end="", flush=True)

        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return {"success": True, "response": "Cancelled.", "command_ran": None, "command_output": None, "error": None}

        if answer in conf_words["yes"]:
            confirmed = True
            command_ran = confirm_cmd
            command_output = _run_command(command_ran)
        else:
            cancelled = {"Turkish": "İptal edildi.", "English": "Cancelled.", "German": "Abgebrochen.", "French": "Annulé.", "Spanish": "Cancelado."}
            return {"success": True, "response": cancelled.get(language, "Cancelled."), "command_ran": None, "command_output": None, "error": None}

    # ── Turn 2: Explain output ────────────────────────────────────────────────
    if command_output is not None:
        turn2_system = f"""You are Petacomm, an AI-powered Linux server management assistant.
The user's language is: {language}. You MUST respond in {language}.

{context_str}

You just ran: {command_ran}
Raw output:
---
{command_output}
---

RULES:
1. Respond ONLY in {language}.
2. Explain as if talking to a complete beginner who never used Linux.
3. Replace ALL technical terms with simple real-world analogies.
4. Use ✅ for good, ⚠️ for warning, ❌ for problem.
5. Show sizes in human readable format (GB, MB).
6. If there is a problem, give simple next steps.
7. Do NOT use markdown formatting - no ##, no **, no backticks.
8. Write in plain text only."""

        messages = [
            {"role": "user", "content": request},
            {"role": "assistant", "content": turn1_text},
            {"role": "user", "content": f"Command output:\n{command_output}"},
        ]

        turn2 = _call_claude(messages=messages, system=turn2_system, api_key=key, max_tokens=1024)

        if not turn2["success"]:
            return {"success": False, "error": turn2["error"], "response": None}

        return {
            "success": True,
            "response": clean_response(turn2["text"]),
            "command_ran": command_ran,
            "command_output": command_output,
            "error": None,
        }

    # Direct answer
    return {
        "success": True,
        "response": clean_response(turn1_text),
        "command_ran": None,
        "command_output": None,
        "error": None,
    }
