# Source: https://www.cloudflare.com/ips-v4
/ip firewall address-list remove [find list="CLOUDFLARE" comment="Cloudflare IPv4"]
/ip firewall address-list
add list="CLOUDFLARE" address=103.21.244.0/22 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=103.22.200.0/22 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=103.31.4.0/22 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=104.16.0.0/13 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=104.24.0.0/14 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=108.162.192.0/18 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=131.0.72.0/22 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=141.101.64.0/18 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=162.158.0.0/15 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=172.64.0.0/13 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=173.245.48.0/20 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=188.114.96.0/20 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=190.93.240.0/20 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=197.234.240.0/22 comment="Cloudflare IPv4"
add list="CLOUDFLARE" address=198.41.128.0/17 comment="Cloudflare IPv4"
