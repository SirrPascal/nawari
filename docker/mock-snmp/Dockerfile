FROM alpine:3.21

# Install net-snmp, net-snmp-tools, and iproute2 for virtual network interfaces
RUN apk add --no-cache \
    net-snmp \
    net-snmp-tools \
    iproute2 \
    bash \
    procps

# Create SNMP configuration directories
RUN mkdir -p /etc/snmp /var/lib/net-snmp

COPY snmpd.conf /etc/snmp/snmpd.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY inject_fault.sh /usr/local/bin/inject_fault.sh
COPY snmp_disk_pass.sh /usr/local/bin/snmp_disk_pass.sh

RUN chmod +x /usr/local/bin/entrypoint.sh /usr/local/bin/inject_fault.sh /usr/local/bin/snmp_disk_pass.sh

EXPOSE 161/udp

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

