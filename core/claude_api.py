"""
Petacomm - Claude API Integration
Two-turn pipeline: understands request → runs command → explains output.
Supports interactive confirmation in the user's language.
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
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        return out if out else err
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds."
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
    """Detect the language of the user's request."""
    result = _call_claude(
        messages=[{"role": "user", "content": f"What language is this text written in? Reply with only the language name in English, nothing else. Text: {text}"}],
        system="You are a language detector. Reply with only the language name in English (e.g. Turkish, English, German, French, Spanish). Nothing else.",
        api_key=api_key,
        max_tokens=10,
    )
    return result.get("text", "English").strip()


def _confirmation_words(language: str) -> dict:
    """Return yes/no words for a given language."""
    words = {
        "Turkish":    {"yes": ["evet", "e", "tamam", "ok"],    "no": ["hayır", "h", "iptal", "vazgeç"],    "prompt": "Onaylıyor musunuz? (Evet/Hayır)"},
        "English":    {"yes": ["yes", "y", "ok", "sure"],      "no": ["no", "n", "cancel", "abort"],        "prompt": "Do you confirm? (Yes/No)"},
        "German":     {"yes": ["ja", "j", "ok"],                "no": ["nein", "n", "abbrechen"],            "prompt": "Bestätigen Sie? (Ja/Nein)"},
        "French":     {"yes": ["oui", "o", "ok"],               "no": ["non", "n", "annuler"],               "prompt": "Confirmez-vous? (Oui/Non)"},
        "Spanish":    {"yes": ["sí", "si", "s", "ok"],          "no": ["no", "n", "cancelar"],               "prompt": "¿Confirma? (Sí/No)"},
        "Italian":    {"yes": ["sì", "si", "s", "ok"],          "no": ["no", "n", "annulla"],                "prompt": "Confermi? (Sì/No)"},
        "Portuguese": {"yes": ["sim", "s", "ok"],               "no": ["não", "nao", "n", "cancelar"],       "prompt": "Confirma? (Sim/Não)"},
        "Russian":    {"yes": ["да", "д", "ok"],                "no": ["нет", "н", "отмена"],                "prompt": "Подтверждаете? (Да/Нет)"},
        "Arabic":     {"yes": ["نعم", "ok"],                    "no": ["لا", "إلغاء"],                       "prompt": "هل تؤكد؟ (نعم/لا)"},
        "Japanese":   {"yes": ["はい", "yes", "ok"],             "no": ["いいえ", "no"],                      "prompt": "確認しますか？(はい/いいえ)"},
    }
    return words.get(language, words["English"])


def ask_claude(request: str, system_context: dict = None, api_key: str = None) -> dict:
    """
    Two-turn pipeline:
    1. Claude decides what to do (run command or ask confirmation)
    2. If confirmation needed → ask user in their language → wait for answer
    3. Run command → explain output in human language
    """
    key = api_key or get_api_key()
    if not key:
        return {
            "success": False,
            "error": "API key not found. Run: petacomm login",
            "response": None,
        }

    context_str = _build_context(system_context)

    # Detect user's language
    language = _detect_language(request, key)

    # ── Turn 1: Decide what to do ─────────────────────────────────────────────
    turn1_system = f"""You are Petacomm, an AI-powered Linux server management assistant.
The user's language is: {language}. You MUST respond in {language}.

{context_str}

RULES:
1. Always respond in {language} — this is critical.

2. To run a safe read-only command (ls, df, free, ps, top, etc.), output ONLY this JSON:
   {{"run": "command here"}}

3. For DANGEROUS or MODIFYING operations (apt upgrade, rm, systemctl restart, etc.):
   - Explain what will happen in simple terms
   - List the risks
   - End your message with EXACTLY this JSON on the last line (nothing after it):
   {{"confirm": "the exact command to run", "danger": "low|medium|high"}}

4. If no command is needed, just answer directly in {language}.

5. Always explain technical terms simply — the user may be a complete beginner."""

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

    # Check for {"run": ...} — safe command, run immediately
    run_match = re.search(r'\{"run"\s*:\s*"([^"]+)"\}', turn1_text)

    # Check for {"confirm": ..., "danger": ...} — needs user confirmation
    confirm_match = re.search(r'\{"confirm"\s*:\s*"([^"]+)"\s*,\s*"danger"\s*:\s*"([^"]+)"\}', turn1_text)

    if run_match:
        command_ran = run_match.group(1)
        command_output = _run_command(command_ran)

    elif confirm_match:
        confirm_cmd = confirm_match.group(1)
        danger = confirm_match.group(2)

        # Show explanation (everything before the JSON)
        explanation = turn1_text[:confirm_match.start()].strip()

        # Get confirmation words in user's language
        conf_words = _confirmation_words(language)

        # Color for danger level
        danger_colors = {"low": "\033[33m", "medium": "\033[33m", "high": "\033[31m"}
        color = danger_colors.get(danger, "\033[33m")
        reset = "\033[0m"

        print()
        print(f"\033[36m{'─' * 60}\033[0m")
        if explanation:
            print(explanation)
            print()
        print(f"{color}❯ {conf_words['prompt']}{reset} ", end="", flush=True)

        try:
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return {
                "success": True,
                "response": "Cancelled." if language == "English" else "İptal edildi.",
                "command_ran": None,
                "command_output": None,
                "error": None,
            }

        if answer in conf_words["yes"]:
            confirmed = True
            command_ran = confirm_cmd
            command_output = _run_command(command_ran)
        else:
            cancelled_msg = {
                "Turkish": "İptal edildi.",
                "English": "Cancelled.",
                "German": "Abgebrochen.",
                "French": "Annulé.",
                "Spanish": "Cancelado.",
            }
            return {
                "success": True,
                "response": cancelled_msg.get(language, "Cancelled."),
                "command_ran": None,
                "command_output": None,
                "error": None,
            }

    # ── Turn 2: Explain output ────────────────────────────────────────────────
    if command_output is not None:
        turn2_system = f"""You are Petacomm, an AI-powered Linux server management assistant.
The user's language is: {language}. You MUST respond in {language}.

{context_str}

You just ran: `{command_ran}`
Raw output:
---
{command_output}
---

RULES:
1. Respond in {language} — absolutely required.
2. Explain the output as if talking to a complete beginner who has never used Linux.
3. Replace ALL technical terms with simple real-world analogies.
4. Use ✅ for good things, ⚠️ for warnings, ❌ for problems.
5. Show sizes in human-readable format (GB, MB — not bytes or kilobytes).
6. If there's a problem, give simple next steps.
7. Keep it friendly and concise."""

        messages = [
            {"role": "user", "content": request},
            {"role": "assistant", "content": turn1_text},
            {"role": "user", "content": f"Command output:\n{command_output}"},
        ]

        if confirmed:
            messages.append({
                "role": "assistant",
                "content": f"The command `{command_ran}` was executed. Here is the output."
            })

        turn2 = _call_claude(
            messages=messages,
            system=turn2_system,
            api_key=key,
            max_tokens=1024,
        )

        if not turn2["success"]:
            return {"success": False, "error": turn2["error"], "response": None}

        return {
            "success": True,
            "response": clean_markdown(turn2["text"]),
            "command_ran": command_ran,
            "command_output": command_output,
            "error": None,
        }

    # Direct answer, no command
    return {
        "success": True,
        "response": clean_markdown(turn1_text),
        "command_ran": None,
        "command_output": None,
        "error": None,
    }


def clean_markdown(text: str) -> str:
    """Remove markdown formatting for clean terminal output."""
    import re
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*{1,3}([^*\n]+)\*{1,3}', r'\1', text)
    text = re.sub(r'_{1,3}([^_\n]+)_{1,3}', r'\1', text)
    text = re.sub(r'[\x60]{3}[a-z]*\n?', '', text)
    text = re.sub(r'[\x60]([^\x60\n]+)[\x60]', r'\1', text)
    text = re.sub(r'^[-*_]{3,}\s*$', '─' * 40, text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
