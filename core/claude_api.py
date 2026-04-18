"""
Petacomm - Claude API Entegrasyonu
Kullanıcının doğal dil isteğini sisteme özel komutlara çevirir.
"""

import json
import os
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


def ask_claude(request: str, system_context: dict = None, api_key: str = None) -> dict:
    """
    Claude'a istek gönder.
    system_context: Sistem bilgisi (scanner'dan gelen veri)
    """
    import urllib.request
    import urllib.error

    key = api_key or get_api_key()
    if not key:
        return {
            "success": False,
            "error": "API key bulunamadı. Önce: petacomm login",
            "response": None,
        }

    # Sistem bağlamını hazırla
    context_str = ""
    if system_context:
        context_str = f"""
Mevcut sistem bilgisi:
- Hostname: {system_context.get('hostname', '?')}
- OS: {system_context.get('os', '?')}
- CPU kullanımı: %{system_context.get('cpu', '?')}
- RAM kullanımı: %{system_context.get('ram', {}).get('percent', '?')}
- Uptime: {system_context.get('uptime', '?')}
- Çalışan servisler: {', '.join(s['name'] for s in system_context.get('services', []) if s.get('active'))}
- Sağlık skoru: {system_context.get('health', {}).get('score', '?')}/100
- Uyarılar: {', '.join(system_context.get('health', {}).get('warnings', [])) or 'yok'}
- Kritik sorunlar: {', '.join(system_context.get('health', {}).get('criticals', [])) or 'yok'}
"""

    system_prompt = f"""Sen Petacomm'un Linux sunucu yönetim asistanısın. 
Kullanıcının doğal dil isteğini anlayıp Linux sunucusunda ne yapılması gerektiğini açıklarsın.

{context_str}

Kurallar:
1. Kısa ve net cevap ver, gereksiz açıklama yapma
2. Çalıştırılacak komutları açıkça belirt
3. Tehlikeli işlemlerde uyar
4. Türkçe cevap ver
5. Komutları ``` ``` içinde göster
6. Her zaman önce ne yapacağını söyle, sonra nasıl yapacağını

Cevap formatın:
- Ne yapacağını 1-2 cümleyle açıkla
- Gerekli komutları listele
- Varsa uyarıları belirt"""

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": request}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["content"][0]["text"]
            return {"success": True, "response": text, "error": None}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            err = json.loads(body)
            msg = err.get("error", {}).get("message", body)
        except Exception:
            msg = body
        return {"success": False, "error": f"API Hatası: {msg}", "response": None}
    except Exception as e:
        return {"success": False, "error": str(e), "response": None}
