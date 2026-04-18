# Petacomm

Linux sunucunu doğal dille yönet. AI destekli terminal aracı.

## Kurulum

```bash
pip install rich psutil
python petacomm.py help
```

Ya da global olarak kullanmak için:

```bash
pip install -e .
petacomm help
```

## Kullanım

```bash
# Sistem durumu
petacomm status

# Sağlık skoru
petacomm health

# Listele
petacomm ls services
petacomm ls ports
petacomm ls backups
petacomm ls processes

# Loglar
petacomm logs nginx
petacomm logs nginx --follow

# Dosya ara ve sil
petacomm find "gatebell"

# Yedekleme
petacomm backup now
petacomm restore 2026-04-17_09-22-00

# AI isteği (Claude API gerekir)
petacomm login
petacomm -r "nginx neden çalışmıyor"
petacomm -r "disk neden dolu, temizle"
petacomm -r "güvenlik açığı var mı"

# Simülasyon modu (çalıştırmadan göster)
petacomm --dry-run -r "mysql'i yeniden başlat"
```

## API Key

https://console.anthropic.com adresinden ücretsiz API key alabilirsin.

```bash
petacomm login
# sk-ant-... şeklinde key'ini gir
```

Key `~/.petacomm/config.json` dosyasına kaydedilir.
