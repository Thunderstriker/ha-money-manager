ARG BUILD_FROM
FROM $BUILD_FROM

ENV LANG=C.UTF-8

WORKDIR /opt/moneymanager

COPY app/requirements.txt /opt/moneymanager/requirements.txt
RUN \
    apk add --no-cache --virtual .build-deps build-base \
    && pip3 install --no-cache-dir -r /opt/moneymanager/requirements.txt \
    && apk del .build-deps

COPY app/ /opt/moneymanager/app/
COPY rootfs/ /

RUN chmod a+x /etc/services.d/moneymanager/run /etc/services.d/moneymanager/finish

LABEL \
    io.hass.name="Money Manager" \
    io.hass.description="Import, categorize and visualize your online banking transactions" \
    io.hass.type="addon"
