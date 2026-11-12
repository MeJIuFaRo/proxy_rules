# Installs script "proxy-rules-update" and a daily scheduler on MikroTik (RouterOS 7).
# The script downloads from the private GitHub repository and imports:
#   lists/vpn.rsc - /ip firewall address-list VPN (IPv4 ranges, built by GitHub Actions)
#   lists/dns.rsc - /ip dns static FWD -> forwarder VPN, address-list VPN (from dns/vpn.txt)
#
# Before importing, replace <GITHUB_TOKEN> with a fine-grained token:
# repository MeJIuFaRo/proxy_rules only, permission Contents: Read-only.
# Requires /ip dns forwarders entry named VPN; without it dns.rsc stops before any change.

/system script remove [find where name="proxy-rules-update"]
/system script add name=proxy-rules-update policy=ftp,read,write,policy,test source={
  :local token "<GITHUB_TOKEN>"
  :local base "https://api.github.com/repos/MeJIuFaRo/proxy_rules/contents/lists/"
  :local headers ("Authorization: Bearer " . $token . ",Accept: application/vnd.github.raw,User-Agent: mikrotik-proxy-rules")
  :foreach f in={"vpn.rsc";"dns.rsc"} do={
    :local file ("proxy_rules-" . $f)
    :do {
      /tool fetch url=($base . $f . "\?ref=main") http-header-field=$headers dst-path=$file output=file
      :delay 1s
      /import file-name=$file
      :log info ("proxy_rules: " . $f . " imported")
    } on-error={
      :log error ("proxy_rules: " . $f . " update failed, previous rules kept")
    }
    :do { /file remove [find where name=$file] } on-error={}
  }
}

/system scheduler remove [find where name="proxy-rules-update"]
/system scheduler add name=proxy-rules-update interval=1d start-time=07:00:00 \
  on-event="/system script run proxy-rules-update" policy=ftp,read,write,policy,test
