# Configuration Apache mod_auth_gssapi pour ForgeAI SSO

> **⚠️ MODÈLE À ADAPTER ET AUDITER** — Cette configuration est fournie à titre indicatif. Elle doit être revue, testée en environnement de staging, et validée par un administrateur système/sécurité avant toute mise en production.

## Prérequis sur le VPS

### 1. Paquets requis (Debian/Ubuntu)
```bash
apt-get update && apt-get install -y \
    apache2 \
    libapache2-mod-auth-gssapi \
    krb5-user \
    krb5-config
```

### 2. Kerberos client configuration (`/etc/krb5.conf`)
```ini
[libdefaults]
    default_realm = DESIGN-EDE.FR
    dns_lookup_realm = false
    dns_lookup_kdc = true
    ticket_lifetime = 24h
    renew_lifetime = 7d
    forwardable = true
    rdns = false
    default_ccache_name = KEYRING:persistent:%{uid}

[realms]
    DESIGN-EDE.FR = {
        kdc = 192.168.100.254
        admin_server = 192.168.100.254
        default_domain = design-ede.fr
    }

[domain_realm]
    .design-ede.fr = DESIGN-EDE.FR
    design-ede.fr = DESIGN-EDE.FR
```

### 3. Keytab déploiement
```bash
# Copier le keytab généré sur le DC
# ktpass -princ HTTP/forgeai.design-ede.fr@DESIGN-EDE.FR -mapuser svc_forgeai_http -crypto AES256-SHA1 -out forgeai.keytab

cp forgeai.keytab /etc/krb5.keytab
chown www-data:www-data /etc/krb5.keytab
chmod 640 /etc/krb5.keytab
```

### 4. Test keytab
```bash
kinit -k -t /etc/krb5.keytab HTTP/forgeai.design-ede.fr@DESIGN-EDE.FR
klist
```

## Configuration Apache (site ForgeAI)

### Fichier : `/etc/apache2/sites-available/forgeai.conf`

```apache
<VirtualHost *:443>
    ServerName forgeai.design-ede.fr
    
    # TLS Configuration
    SSLEngine on
    SSLCertificateFile /etc/ssl/certs/forgeai.design-ede.fr.crt
    SSLCertificateKeyFile /etc/ssl/private/forgeai.design-ede.fr.key
    SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1
    SSLCipherSuite HIGH:!aNULL:!MD5:!3DES
    
    # Security Headers
    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
    Header always set X-Content-Type-Options nosniff
    Header always set X-Frame-Options DENY
    Header always set Referrer-Policy strict-origin-when-cross-origin
    
    # Proxy Configuration
    ProxyPreserveHost On
    ProxyRequests Off
    
    # Forwarded headers for backend
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-Port "443"
    RequestHeader set X-Forwarded-Host "%{Host}s"
    
    # ============================================================
    # CRITICAL: Strip client-provided identity headers BEFORE auth
    # ============================================================
    RequestHeader unset X-Remote-User
    RequestHeader unset Remote-User
    RequestHeader unset X-Forwarded-User
    RequestHeader unset X-Forwarded-For
    
    # ============================================================
    # Kerberos/SPNEGO Authentication (mod_auth_gssapi)
    # ============================================================
    # Authentification SSO uniquement sur les endpoints SSO
    # (le reste de l'application reste accessible en login formulaire)
    <Location /auth/sso>
        AuthType GSSAPI
        AuthName "DESIGN-EDE.FR"
        GssapiCredStore keytab:/etc/krb5.keytab
        GssapiSSLonly On
        GssapiBasicAuth Off
        Require valid-user
        # expr=%{REMOTE_USER} lit r->user directement.
        # NB: GssapiLocalName reste absent -> gss_localname() echoue (ENOENT) sur
        # ce VPS; le realm "@DESIGN-EDE.FR" est retire cote backend (authenticate_sso).
        # NB: les formes %{REMOTE_USER}e / %{REMOTE_USER}s ressortent (null):
        # mod_auth_gssapi n'exporte jamais REMOTE_USER dans l'environnement.
        RequestHeader set X-Remote-User "expr=%{REMOTE_USER}"
    </Location>
    
    # Proxy to FastAPI
    ProxyPass / http://127.0.0.1:8000/
    ProxyPassReverse / http://127.0.0.1:8000/
    
    # WebSocket support (if needed)
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/(.*) ws://127.0.0.1:8000/$1 [P,L]
    
    # Logging
    ErrorLog ${APACHE_LOG_DIR}/forgeai-error.log
    CustomLog ${APACHE_LOG_DIR}/forgeai-access.log combined
    
    # Kerberos debug (remove in production)
    # LogLevel debug
    # GssapiLogLevel 5
</VirtualHost>

# HTTP to HTTPS redirect
<VirtualHost *:80>
    ServerName forgeai.design-ede.fr
    Redirect permanent / https://forgeai.design-ede.fr/
</VirtualHost>
```

### Activation
```bash
a2enmod ssl proxy proxy_http proxy_wstunnel headers rewrite auth_gssapi
a2ensite forgeai
systemctl reload apache2
```

## Configuration ForgeAI (`.env` production)

```env
# Active Directory
AD_ENABLED=true
AD_SERVER=192.168.100.254
AD_PORT=636
AD_USE_SSL=true
AD_BASE_DN=DC=design-ede,DC=fr
AD_USER_DN=OU=Users,DC=design-ede,DC=fr
AD_BIND_USER=CN=svc_forgeai,OU=ServiceAccounts,DC=design-ede,DC=fr
AD_BIND_PASSWORD=******
AD_GROUP_SEARCH_BASE=OU=Groups,DC=design-ede,DC=fr
AD_GROUP_MAPPING='{"admin": "GG_FORGEAI_Admins", "user": "GG_FORGEAI_Users"}'

# SSO Kerberos
# En production, ces variables passent par docker-compose.override.yml
# (bloc environment: du service app) - un simple .env ne suffit pas.
AD_SSO_ENABLED=true
# IP du proxy Apache vue depuis le conteneur Docker (provoque: 172.19.0.1)
AD_SSO_TRUSTED_PROXY_IPS=["172.19.0.1"]
AD_SSO_HEADER_NAME=X-Remote-User
```

## Vérifications post-déploiement

### 1. Test Kerberos depuis le VPS
```bash
# Depuis le conteneur ou l'hôte
kinit -k -t /etc/krb5.keytab HTTP/forgeai.design-ede.fr@DESIGN-EDE.FR
curl -u : --negotiate https://forgeai.design-ede.fr/auth/me
```

### 2. Test navigateur (poste joint au domaine)
1. Ouvrir Edge → `https://forgeai.design-ede.fr`
2. Connexion automatique sans saisie de mot de passe
3. Vérifier cookies `access_token`, `refresh_token` présents

### 3. Test fallback formulaire
1. Désactiver `AD_SSO_ENABLED=false` dans `.env`
2. Redémarrer conteneur app
3. Connexion via formulaire `/auth/login` doit fonctionner

## Dépannage courant

| Problème | Cause probable | Solution |
|----------|----------------|----------|
| `401 Unauthorized` sur `/auth/sso` | `AD_SSO_ENABLED=false` | Vérifier `.env` et redémarrer |
| Edge n'envoie aucun ticket (pas de challenge consommé) | `forgeai.design-ede.fr` hors zone Intranet | Ajouter le domaine aux sites Intranet (Edge/Windows) |
| `403 Accès SSO non autorisé` | IP proxy pas dans `AD_SSO_TRUSTED_PROXY_IPS` | Ajouter IP conteneur Apache |
| `403 Token CSRF invalide` | Cookie CSRF manquant | Vérifier appel `/auth/sso/csrf-token` avant |
| `Utilisateur AD non autorisé` | Aucun mapping groupe actif | Vérifier `ADGroupMapping` en base |
| `KRB5 error` | Keytab invalide / SPN manquant | Régénérer keytab, vérifier `setspn -L` |

## Sécurité - Points de contrôle

- [ ] Keytab `640` owned by `www-data`
- [ ] Headers `X-Remote-User` **unset** avant auth
- [ ] Header `X-Remote-User` **set** seulement après `Require valid-user`
- [ ] Port 8000 **non exposé** sur Internet (firewall)
- [ ] `AD_SSO_TRUSTED_PROXY_IPS` correspond à l'IP réelle du proxy
- [ ] TLS 1.2+ uniquement, HSTS activé
- [ ] Audit logs SSO activés (`action="sso_login"`)

## Références

- [mod_auth_gssapi documentation](https://github.com/modauthgssapi/mod_auth_gssapi)
- [MIT Kerberos keytab](https://web.mit.edu/kerberos/krb5-latest/doc/admin/conf_files/krb5_keytab.html)
- [Apache RequestHeader directive](https://httpd.apache.org/docs/2.4/mod/mod_headers.html#requestheader)