# Vultr hosts the DNS zone for var.domain. At the registrar, set the nameservers to ns1.vultr.com and ns2.vultr.com.
# The records follow the server's IP, so a replace_server run moves the domain along with it.
resource "vultr_dns_domain" "main" {
  count  = var.domain != "" ? 1 : 0
  domain = var.domain
  # no `ip`: Vultr would add its own default records (wildcard, MX) next to the ones below
}

# apex = the web app, www = alias, api = the Electron app's API base. All point at the same Caddy for now.
resource "vultr_dns_record" "a" {
  for_each = var.domain != "" ? toset(["", "www", "api"]) : toset([])
  domain   = vultr_dns_domain.main[0].id
  name     = each.value
  type     = "A"
  data     = vultr_instance.api.main_ip
  ttl      = 300
}
