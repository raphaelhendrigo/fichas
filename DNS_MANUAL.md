# DNS_MANUAL.md

Use este arquivo se o dominio ainda nao estiver no Cloudflare.
O objetivo e criar somente o subdominio de testes, sem tocar no dominio principal.

## Estrategia A (IP publico + port-forward)
Crie/atualize o registro (ex.: Locaweb):
- Tipo: A
- Nome: lab
- Conteudo: SEU_IP_PUBLICO
- TTL: 3600 (na Locaweb e fixo)

## Estrategia B (Cloudflare Tunnel)
Crie/atualize o registro (ex.: Locaweb):
- Tipo: CNAME
- Nome: lab
- Conteudo: <UUID>.cfargotunnel.com
- TTL: 3600 (na Locaweb e fixo)
- Proxy: habilitado (quando o provedor permitir)

Nao altere os registros do dominio raiz ou do `www`.
