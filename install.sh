#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# Kraken Trading Bot — Script d'installation automatisé
# Ubuntu 24.04 + Docker + Nginx + Let's Encrypt HTTPS
# ============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

INSTALL_DIR="/opt/kraken-bot"
REPO_URL="https://github.com/eme-data/bot-auto-trade.git"

info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ============================================================================
# 1. Vérifications
# ============================================================================
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     Kraken Trading Bot — Installation            ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

if [[ $EUID -ne 0 ]]; then
    error "Ce script doit être exécuté en tant que root (sudo ./install.sh)"
fi

if ! grep -qiE 'ubuntu|debian' /etc/os-release 2>/dev/null; then
    warn "Ce script est conçu pour Ubuntu/Debian. Poursuite quand même..."
fi

# ============================================================================
# 2. Installation des prérequis
# ============================================================================
info "Mise à jour du système..."
apt-get update -qq
apt-get upgrade -y -qq

info "Installation des paquets de base..."
apt-get install -y -qq ca-certificates curl gnupg git ufw snapd

# Docker Engine (repo officiel)
if ! command -v docker &>/dev/null; then
    info "Installation de Docker Engine..."
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    ok "Docker installé"
else
    ok "Docker déjà installé"
fi

# Certbot via snap
if ! command -v certbot &>/dev/null; then
    info "Installation de Certbot..."
    snap install --classic certbot 2>/dev/null || apt-get install -y -qq certbot
    ln -sf /snap/bin/certbot /usr/bin/certbot 2>/dev/null || true
    ok "Certbot installé"
else
    ok "Certbot déjà installé"
fi

# ============================================================================
# 3. Clone du dépôt
# ============================================================================
if [[ -d "$INSTALL_DIR" ]]; then
    info "Répertoire $INSTALL_DIR existe déjà, mise à jour..."
    cd "$INSTALL_DIR"
    git pull origin main 2>/dev/null || warn "git pull échoué, poursuite avec les fichiers existants"
else
    info "Clonage du dépôt..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ok "Dépôt cloné dans $INSTALL_DIR"
fi

# ============================================================================
# 4. Configuration interactive
# ============================================================================
echo ""
echo -e "${CYAN}── Configuration ──────────────────────────────────${NC}"
echo ""

read -rp "Nom de domaine (ex: bot.mondomaine.com): " DOMAIN
if [[ -z "$DOMAIN" ]]; then
    error "Le nom de domaine est obligatoire"
fi

read -rp "Email pour Let's Encrypt: " LE_EMAIL
if [[ -z "$LE_EMAIL" ]]; then
    error "L'email est obligatoire pour Let's Encrypt"
fi

read -rp "Clé API Kraken (laisser vide pour configurer plus tard via /admin): " KRAKEN_KEY
KRAKEN_KEY=${KRAKEN_KEY:-}

if [[ -n "$KRAKEN_KEY" ]]; then
    read -rsp "Secret API Kraken: " KRAKEN_SECRET
    echo ""
    if [[ -z "$KRAKEN_SECRET" ]]; then
        error "Le secret API Kraken est obligatoire si la clé est fournie"
    fi
else
    KRAKEN_SECRET=""
    warn "Clés API non configurées — vous pourrez les ajouter via l'interface /admin"
fi

read -rp "Identifiant dashboard [admin]: " DASH_USER
DASH_USER=${DASH_USER:-admin}

read -rsp "Mot de passe dashboard: " DASH_PASS
echo ""
if [[ -z "$DASH_PASS" ]]; then
    error "Le mot de passe dashboard est obligatoire"
fi

JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)

# Écriture du .env
cat > "$INSTALL_DIR/.env" <<ENVEOF
KRAKEN_API_KEY=${KRAKEN_KEY}
KRAKEN_API_SECRET=${KRAKEN_SECRET}

DASH_USER=${DASH_USER}
DASH_PASS=${DASH_PASS}
JWT_SECRET=${JWT_SECRET}
ENVEOF

chmod 600 "$INSTALL_DIR/.env"
ok "Fichier .env créé"

# ============================================================================
# 5. Préparation Nginx
# ============================================================================
info "Génération de la configuration Nginx..."
mkdir -p "$INSTALL_DIR/nginx"

sed "s/\${DOMAIN}/${DOMAIN}/g" "$INSTALL_DIR/nginx/default.conf.template" \
    > "$INSTALL_DIR/nginx/default.conf"

ok "Config Nginx générée pour ${DOMAIN}"

# ============================================================================
# 6. Firewall
# ============================================================================
info "Configuration du firewall..."
ufw allow 22/tcp   >/dev/null 2>&1 || true
ufw allow 80/tcp   >/dev/null 2>&1 || true
ufw allow 443/tcp  >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true
ok "Ports 80 et 443 ouverts"

# ============================================================================
# 7. Obtention du certificat Let's Encrypt
# ============================================================================
info "Obtention du certificat SSL pour ${DOMAIN}..."

# Créer le répertoire webroot pour le challenge ACME
mkdir -p /var/www/certbot

# Lancer un serveur Nginx temporaire pour le challenge HTTP
docker run -d --name certbot-nginx \
    -p 80:80 \
    -v /var/www/certbot:/var/www/certbot:ro \
    nginx:alpine \
    sh -c "echo 'server { listen 80; location /.well-known/acme-challenge/ { root /var/www/certbot; } location / { return 444; } }' > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'" \
    2>/dev/null

# Attendre que Nginx démarre
sleep 3

# Obtenir le certificat
certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$LE_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    -d "$DOMAIN"

CERT_STATUS=$?

# Arrêter et supprimer le container temporaire
docker stop certbot-nginx >/dev/null 2>&1 || true
docker rm certbot-nginx >/dev/null 2>&1 || true

if [[ $CERT_STATUS -ne 0 ]]; then
    error "Échec de l'obtention du certificat. Vérifiez que le domaine ${DOMAIN} pointe vers cette machine."
fi

ok "Certificat SSL obtenu pour ${DOMAIN}"

# ============================================================================
# 8. Lancement
# ============================================================================
info "Construction et lancement des containers..."
cd "$INSTALL_DIR"

docker compose down 2>/dev/null || true
docker compose up -d --build

# Attendre que les services soient prêts
info "Attente du démarrage des services..."
sleep 10

if docker compose ps | grep -q "running"; then
    ok "Services démarrés"
else
    warn "Les services prennent plus de temps à démarrer, vérifiez avec: docker compose logs -f"
fi

# ============================================================================
# 9. Renouvellement automatique du certificat
# ============================================================================
info "Configuration du renouvellement automatique SSL..."

cat > /etc/cron.d/certbot-renew <<'CRONEOF'
# Renouvellement Let's Encrypt - 2x par jour
0 3,15 * * * root certbot renew --quiet --deploy-hook "docker compose -f /opt/kraken-bot/docker-compose.yml exec -T nginx nginx -s reload"
CRONEOF

chmod 644 /etc/cron.d/certbot-renew
ok "Renouvellement automatique configuré"

# ============================================================================
# 10. Résumé
# ============================================================================
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║         Installation terminée !                  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Dashboard:    ${CYAN}https://${DOMAIN}${NC}"
echo -e "  Utilisateur:  ${CYAN}${DASH_USER}${NC}"
echo -e "  Mode:         ${YELLOW}dry_run: true${NC} (modifier config/settings.yaml pour activer le trading réel)"
echo ""
echo -e "  ${CYAN}Commandes utiles :${NC}"
echo -e "    cd ${INSTALL_DIR}"
echo -e "    docker compose logs -f bot     # Logs du bot"
echo -e "    docker compose logs -f nginx   # Logs Nginx"
echo -e "    docker compose ps              # Statut des services"
echo -e "    docker compose restart         # Redémarrer"
echo -e "    docker compose down            # Arrêter"
echo -e "    docker compose up -d --build   # Reconstruire et relancer"
echo ""
echo -e "  ${CYAN}Configuration :${NC}"
echo -e "    ${INSTALL_DIR}/config/settings.yaml  # Paramètres bot/stratégies"
echo -e "    ${INSTALL_DIR}/.env                   # Clés API et credentials"
echo ""
echo -e "  ${CYAN}Certificat SSL :${NC}"
echo -e "    Renouvellement automatique configuré (cron)"
echo -e "    Test manuel: sudo certbot renew --dry-run"
echo ""
