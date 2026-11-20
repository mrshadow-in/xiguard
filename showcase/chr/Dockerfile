# Showcase only: a real MikroTik CHR (RouterOS) running under QEMU, plus the
# traffic simulator that feeds Xiguard NetFlow for the CHR's customer prefixes.
FROM alpine:3.22

ARG CHR_VERSION=7.20.4

RUN apk add --no-cache qemu-system-x86_64 python3 \
 && wget -q -O /tmp/chr.zip "https://download.mikrotik.com/routeros/${CHR_VERSION}/chr-${CHR_VERSION}.img.zip" \
 && mkdir /chr && unzip -q /tmp/chr.zip -d /chr \
 && mv "/chr/chr-${CHR_VERSION}.img" /chr/chr.img \
 && rm /tmp/chr.zip

COPY entrypoint.sh simulator.py /opt/

EXPOSE 8090
ENTRYPOINT ["sh", "/opt/entrypoint.sh"]
