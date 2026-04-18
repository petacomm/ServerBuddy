#!/bin/bash
# Petacomm Kurulum Script'i

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo "  ██████╗ ███████╗████████╗ █████╗  ██████╗ ██████╗ ███╗   ███╗███╗   ███╗"
echo "  ██╔══██╗██╔════╝╚══██╔══╝██╔══██╗██╔════╝██╔═══██╗████╗ ████║████╗ ████║"
echo "  ██████╔╝█████╗     ██║   ███████║██║     ██║   ██║██╔████╔██║██╔████╔██║"
echo "  ██╔═══╝ ██╔══╝     ██║   ██╔══██║██║     ██║   ██║██║╚██╔╝██║██║╚██╔╝██║"
echo "  ██║     ███████╗   ██║   ██║  ██║╚██████╗╚██████╔╝██║ ╚═╝ ██║██║ ╚═╝ ██║"
echo "  ╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝"
echo ""
echo "  Linux Server Yönetim Aracı"
echo ""

# ─── Python kontrolü ─────────────────────────────────────────────────────────
echo -n "  Python3 kontrol ediliyor... "
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}bulunamadı!${NC}"
    echo ""
    echo "  Python3 kuruluyor..."
    sudo apt-get update -qq && sudo apt-get install -y python3 python3-pip
else
    VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✓ $VERSION${NC}"
fi

# ─── pip kontrolü ────────────────────────────────────────────────────────────
echo -n "  pip kontrol ediliyor... "
if ! command -v pip3 &>/dev/null; then
    echo -e "${YELLOW}kuruluyor...${NC}"
    sudo apt-get install -y python3-pip -qq
else
    echo -e "${GREEN}✓${NC}"
fi

# ─── Bağımlılıklar ───────────────────────────────────────────────────────────
echo -n "  Bağımlılıklar kuruluyor... "
pip3 install rich psutil -q --break-system-packages 2>/dev/null || pip3 install rich psutil -q
echo -e "${GREEN}✓${NC}"

# ─── Script kopyala ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -n "  Petacomm kuruluyor... "

# /usr/local/lib/petacomm dizinine kopyala
sudo mkdir -p /usr/local/lib/petacomm
sudo cp -r "$SCRIPT_DIR/core" /usr/local/lib/petacomm/
sudo cp "$SCRIPT_DIR/petacomm.py" /usr/local/lib/petacomm/

# Çalıştırıcı script oluştur
sudo tee /usr/local/bin/petacomm > /dev/null <<'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/local/lib/petacomm')
from petacomm import main
main()
EOF

sudo chmod +x /usr/local/bin/petacomm
echo -e "${GREEN}✓${NC}"

# ─── Test ────────────────────────────────────────────────────────────────────
echo -n "  Test ediliyor... "
if petacomm help &>/dev/null; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}hata!${NC}"
    exit 1
fi

# ─── Bitti ───────────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}✓ Petacomm başarıyla kuruldu!${NC}"
echo ""
echo "  Kullanım:"
echo -e "  ${YELLOW}petacomm status${NC}          → Sistem durumu"
echo -e "  ${YELLOW}petacomm health${NC}          → Sağlık skoru"
echo -e "  ${YELLOW}petacomm ls services${NC}     → Servisler"
echo -e "  ${YELLOW}petacomm -r \"isteğin\"${NC}    → AI'ya sor"
echo -e "  ${YELLOW}petacomm login${NC}            → API key gir"
echo -e "  ${YELLOW}petacomm help${NC}             → Tüm komutlar"
echo ""
