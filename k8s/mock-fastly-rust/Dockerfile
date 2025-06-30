FROM openresty/openresty:alpine

COPY nginx.conf /usr/local/openresty/nginx/conf/nginx.conf
COPY config.hex /opt/config.hex

RUN chmod 644 /opt/config.hex

CMD ["/usr/local/openresty/bin/openresty", "-g", "daemon off;"]
