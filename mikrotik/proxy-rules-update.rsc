# Installs script "proxy-rules-update" with a daily scheduler and runs it once (RouterOS 7).
#
# Install on any MikroTik:
#   /tool fetch url="https://raw.githubusercontent.com/MeJIuFaRo/proxy_rules/main/mikrotik/proxy-rules-update.rsc" check-certificate=yes-without-crl dst-path=proxy-rules-update.rsc; /import file-name=proxy-rules-update.rsc
#
# The script downloads and imports:
#   lists/vpn.rsc - /ip firewall address-list VPN (IPv4 ranges, built by GitHub Actions)
#   lists/dns.rsc - /ip dns static FWD -> forwarder VPN, address-list VPN, DNS settings, adlists
#
# Downloads verify the TLS certificate: imported files run as router configuration,
# so a forged file must never be accepted. RouterOS 7.21+ trusts its built-in CAs
# for fetch by default; see README.md for older versions.

/system script remove [find where name="proxy-rules-update"]
/system script add name=proxy-rules-update policy=ftp,read,write,policy,test source={
  :local base "https://raw.githubusercontent.com/MeJIuFaRo/proxy_rules/main/lists/"
  :foreach f in={"vpn.rsc";"dns.rsc"} do={
    :local file ("proxy_rules-" . $f)
    :do {
      /tool fetch url=($base . $f) check-certificate=yes-without-crl dst-path=$file output=file
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

:log info "proxy_rules: installed, running first update"
/system script run proxy-rules-update
